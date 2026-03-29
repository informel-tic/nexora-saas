"""Authentication and CSRF protection for Nexora API endpoints.

Includes per-node token management, CSRF protection middleware, and
WS4-T04 SecretStore for scoped secret isolation by node/service/operator.

Refactored in v2.1 from a 1038-line monolithic module into dedicated submodules:
  · _token        — Token I/O, rotation, session helpers
  · _scopes       — Tenant & actor scope resolution, role validators
  · _rate_limit   — Auth failure rate limiting (file-backed persistence)
  · _middleware   — HTTP middlewares (TokenAuth, SecurityHeaders, CSRF)
  · _secret_store — SecretStore class + VALID_SCOPES/SCOPE_PERMISSIONS

All symbols below are re-exported at this package level for full backward
compatibility with the 20+ import sites that use ``from nexora_node_sdk.auth import X``
or ``import nexora_node_sdk.auth as auth``.

Mutable globals used by tests live in the submodules:
  · auth._token._api_token          — cached API token (None when uncached)
  · auth._rate_limit._AUTH_FAILURES  — per-IP auth failure timestamps
"""

from __future__ import annotations

# ── Make submodules accessible as attributes (auth._token, etc.) ──────
from . import _middleware, _owner_session, _rate_limit, _scopes, _secret_store, _token  # noqa: F401

# ── HTTP middlewares ───────────────────────────────────────────────────
from ._middleware import (
    _PUBLIC_PATHS,
    _SAFE_METHODS,
    _STATIC_PREFIXES,
    CSRFProtectionMiddleware,
    SecurityHeadersMiddleware,
    TokenAuthMiddleware,
)

# ── Owner session ─────────────────────────────────────────────────────
from ._owner_session import (
    create_owner_session,
    has_passphrase_configured,
    owner_tenant_id,
    revoke_owner_session,
    set_owner_passphrase,
    validate_owner_session,
    verify_passphrase,
)

# ── Rate limiting ─────────────────────────────────────────────────────
from ._rate_limit import (
    _AUTH_FAILURES,
    _AUTH_WINDOW_SECONDS,
    _MAX_AUTH_FAILURES,
    _auth_runtime_file,
    _check_rate_limit,
    _record_auth_failure,
)

# ── Tenant scopes & actor roles ───────────────────────────────────────
from ._scopes import (
    NODE_TOKEN_SCOPES,
    _enforce_token_tenant_scope,
    _load_token_actor_roles,
    _load_token_tenant_scopes,
    build_tenant_scope_claim,
    issue_node_secret,
    resolve_actor_role_for_token,
    validate_actor_role,
    validate_operator_surface_role,
    validate_scope,
    validate_trusted_actor_role,
)

# ── SecretStore ───────────────────────────────────────────────────────
from ._secret_store import (
    SCOPE_PERMISSIONS,
    VALID_SCOPES,
    SecretStore,
)

# ── Token management ──────────────────────────────────────────────────
from ._token import (
    _DEFAULT_TOKEN_PATH_CANDIDATES,
    _load_or_generate_token,
    _maybe_auto_rotate_token,
    _read_token_meta,
    _resolve_primary_token_path,
    _token_meta_path,
    _token_path_candidates,
    _token_role_path_candidates,
    _token_scope_path_candidates,
    _write_token_meta,
    generate_session_token,
    get_api_token,
    rotate_api_token,
    validate_session_age,
)

__all__ = [
    # token
    "_DEFAULT_TOKEN_PATH_CANDIDATES",
    "_token_path_candidates",
    "_token_scope_path_candidates",
    "_token_role_path_candidates",
    "_load_or_generate_token",
    "_resolve_primary_token_path",
    "_token_meta_path",
    "_read_token_meta",
    "_write_token_meta",
    "rotate_api_token",
    "_maybe_auto_rotate_token",
    "get_api_token",
    "generate_session_token",
    "validate_session_age",
    # scopes
    "NODE_TOKEN_SCOPES",
    "_load_token_tenant_scopes",
    "_enforce_token_tenant_scope",
    "_load_token_actor_roles",
    "resolve_actor_role_for_token",
    "build_tenant_scope_claim",
    "validate_actor_role",
    "validate_operator_surface_role",
    "validate_trusted_actor_role",
    "validate_scope",
    "issue_node_secret",
    # rate_limit
    "_AUTH_FAILURES",
    "_MAX_AUTH_FAILURES",
    "_AUTH_WINDOW_SECONDS",
    "_auth_runtime_file",
    "_check_rate_limit",
    "_record_auth_failure",
    # middleware
    "_PUBLIC_PATHS",
    "_STATIC_PREFIXES",
    "_SAFE_METHODS",
    "TokenAuthMiddleware",
    "SecurityHeadersMiddleware",
    "CSRFProtectionMiddleware",
    # secret_store
    "VALID_SCOPES",
    "SCOPE_PERMISSIONS",
    "SecretStore",
    # owner_session
    "verify_passphrase",
    "set_owner_passphrase",
    "create_owner_session",
    "validate_owner_session",
    "revoke_owner_session",
    "has_passphrase_configured",
    "owner_tenant_id",
]
