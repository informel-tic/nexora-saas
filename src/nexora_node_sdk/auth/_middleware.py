"""HTTP middlewares: Bearer token auth, security headers, and CSRF protection.

Part of the nexora_node_sdk.auth package.  All symbols here are re-exported
from nexora_node_sdk.auth.__init__ for backward compatibility.
"""

from __future__ import annotations

import hmac
import secrets

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from ._owner_session import validate_owner_session
from ._rate_limit import _check_rate_limit, _record_auth_failure
from ._scopes import (
    _enforce_token_tenant_scope,
    _load_token_actor_roles,
    _load_token_tenant_scopes,
    build_tenant_scope_claim,
    resolve_actor_role_for_token,
)
from ._token import get_api_token

# ── Auth middleware ────────────────────────────────────────────────────


def resolve_surface(request) -> str:
    """Detect which surface the request targets based on Host header or explicit header.

    Returns one of: 'saas', 'console', 'public', or empty string when no
    subdomain is detected (single-domain / test / direct backend access).
    - saas.*     → owner console (passphrase auth)
    - console.*  → subscriber console (token auth)
    - www.*      → public site
    - (other)    → '' (no surface restriction applied)
    """
    # Explicit header (set by nginx) takes priority
    explicit = (request.headers.get("X-Nexora-Surface", "") or "").strip().lower()
    if explicit in ("saas", "console", "public"):
        return explicit

    host = (request.headers.get("Host", "") or "").split(":")[0].strip().lower()
    if host.startswith("saas."):
        return "saas"
    if host.startswith("console."):
        return "console"
    if host.startswith("www."):
        return "public"
    # No recognized subdomain → no surface restriction
    return ""

# Paths that don't require auth
_PUBLIC_PATHS = {
    "/api/health",
    "/health",
    "/api/public/offers",
    "/console",
    "/console/",
    "/owner-console",
    "/owner-console/",
    "/subscribe",
    "/admin",
    "/api/auth/owner-login",
    "/api/auth/owner-passphrase-status",
    "/api/plans",
}

# Static file prefixes — also allows public_site assets
_STATIC_PREFIXES = ("/console/", "/owner-console/", "/public_site/")


def _iter_known_tokens() -> list[str]:
    """Return all accepted API tokens (primary + optional scoped/role tokens)."""

    tokens: list[str] = []

    primary = get_api_token().strip()
    if primary:
        tokens.append(primary)

    for token in _load_token_tenant_scopes().keys():
        normalized = str(token).strip()
        if normalized and normalized not in tokens:
            tokens.append(normalized)

    for token in _load_token_actor_roles().keys():
        normalized = str(token).strip()
        if normalized and normalized not in tokens:
            tokens.append(normalized)

    return tokens


def _resolve_known_token(provided_token: str) -> str | None:
    normalized = provided_token.strip()
    if not normalized:
        return None
    for token in _iter_known_tokens():
        if secrets.compare_digest(normalized, token):
            return token
    return None


class TokenAuthMiddleware(BaseHTTPMiddleware):
    """Require Bearer token for API endpoints.

    WS4-T06 additions:
    - Rate-limits repeated auth failures per client IP
    - Returns generic error to avoid information leakage
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Allow public paths and static assets
        if path in _PUBLIC_PATHS or path == "/":
            return await call_next(request)
        for prefix in _STATIC_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"

        provided_token: str | None = None
        raw_tokens: list[str] = []

        # Check Bearer token
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            raw_tokens.append(auth_header[7:].strip())

        # Also accept X-Nexora-Token header
        token_header = request.headers.get("X-Nexora-Token", "").strip()
        if token_header:
            raw_tokens.append(token_header)

        for raw_token in raw_tokens:
            matched = _resolve_known_token(raw_token)
            if matched is not None:
                provided_token = matched
                break

        # Check for owner session token (passphrase-based auth)
        if provided_token is None:
            session_header = request.headers.get("X-Nexora-Session", "").strip()
            if session_header:
                session = validate_owner_session(session_header)
                if session is not None:
                    request.state.nexora_actor_role = session["role"]
                    request.state.nexora_owner_session = True
                    request.state.nexora_tenant_id = session["tenant_id"]
                    return await call_next(request)

        if provided_token is not None:
            trusted_actor_role = resolve_actor_role_for_token(provided_token)
            request.state.nexora_actor_role = trusted_actor_role
            requested_tenant = request.headers.get("X-Nexora-Tenant-Id")
            configured_scopes = _load_token_tenant_scopes()
            if configured_scopes and provided_token in configured_scopes and not requested_tenant:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Scoped token access requires X-Nexora-Tenant-Id header."},
                )
            if not _enforce_token_tenant_scope(provided_token, requested_tenant):
                return JSONResponse(
                    status_code=403,
                    content={"detail": (f"Token is not authorized for tenant scope '{requested_tenant}'.")},
                )
            if requested_tenant and configured_scopes:
                # Scoped tokens can bootstrap the claim through this endpoint.
                if path == "/api/auth/tenant-claim":
                    return await call_next(request)
                provided_claim = request.headers.get("X-Nexora-Tenant-Claim", "").strip()
                expected_claim = build_tenant_scope_claim(provided_token, requested_tenant)
                if not provided_claim or not hmac.compare_digest(provided_claim, expected_claim):
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Missing or invalid X-Nexora-Tenant-Claim for scoped tenant access."},
                    )
            return await call_next(request)

        if raw_tokens:
            _record_auth_failure(client_ip)
            if _check_rate_limit(client_ip):
                return JSONResponse(status_code=429, content={"detail": "Too many authentication attempts."})

        return JSONResponse(
            status_code=401,
            content={
                "detail": "Authentication required. Use 'Authorization: Bearer <token>' or 'X-Nexora-Token: <token>'."
            },
        )


# ── Security headers middleware ──────────────────────────────────────


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """WS4-T06: Inject security-hardening response headers on every response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response: Response = await call_next(request)
        path = request.url.path or "/"
        # Console UIs currently rely on inline onclick handlers in rendered templates.
        # Keep CSP strict elsewhere while allowing inline handlers only for console pages.
        script_src = "script-src 'self'; "
        if path.startswith(("/console/", "/owner-console/")):
            script_src = "script-src 'self' 'unsafe-inline'; "

        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            + script_src
            +
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        return response


# ── CSRF protection middleware ────────────────────────────────────────

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_CSRF_EXEMPT_PATHS = {
    "/api/auth/owner-login",
    "/api/auth/owner-logout",
    "/api/auth/owner-passphrase",
}


class CSRFProtectionMiddleware(BaseHTTPMiddleware):
    """Reject state-changing requests (POST/PUT/DELETE/PATCH) that don't
    come from the same origin.

    WS4-T06: Strengthened to always require X-Nexora-Action and validate
    both Origin and Referer when present.
    """

    async def dispatch(self, request: Request, call_next):
        if request.method in _SAFE_METHODS:
            return await call_next(request)

        if request.url.path in _CSRF_EXEMPT_PATHS:
            return await call_next(request)

        # Require X-Nexora-Action header on all mutating requests
        if not request.headers.get("X-Nexora-Action"):
            return JSONResponse(
                status_code=403,
                content={"detail": "Missing X-Nexora-Action header on mutating request."},
            )

        # Verify Origin or Referer (at least one must be present)
        origin = request.headers.get("Origin", "")
        referer = request.headers.get("Referer", "")
        host = request.headers.get("Host", "")

        if not origin and not referer:
            return JSONResponse(
                status_code=403,
                content={"detail": "Missing Origin/Referer on mutating request."},
            )

        if origin:
            origin_host = origin.replace("https://", "").replace("http://", "").split("/")[0]
            if origin_host != host:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Cross-origin request rejected."},
                )
        if referer:
            referer_host = referer.replace("https://", "").replace("http://", "").split("/")[0]
            if referer_host != host:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Cross-origin request rejected."},
                )

        return await call_next(request)
