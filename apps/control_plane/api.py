"""Control-plane FastAPI application wiring for Nexora."""

from __future__ import annotations

import os
import secrets
import logging
from datetime import datetime, timezone

import uvicorn
from fastapi import Body, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.responses import Response

from nexora_node_sdk.auth import (
    _load_token_actor_roles,
    CSRFProtectionMiddleware,
    TokenAuthMiddleware,
    build_tenant_scope_claim,
    create_owner_session,
    get_api_token,
    has_passphrase_configured,
    owner_tenant_id as _owner_tenant_id_from_session,
    resolve_actor_role_for_token,
    revoke_owner_session,
    set_owner_passphrase,
    validate_owner_session,
    verify_passphrase,
)
from nexora_node_sdk.auth._middleware import resolve_surface
from nexora_node_sdk.logging_config import setup_logging
from nexora_node_sdk.models import (
    EnrollmentAttestationRequest,
    EnrollmentRegisterRequest,
    EnrollmentTokenRequest,
    LifecycleActionRequest,
)
from nexora_node_sdk.runtime_context import resolve_repo_root
from nexora_node_sdk.version import NEXORA_VERSION
from nexora_saas.runtime_context import build_service

REPO_ROOT = resolve_repo_root(__file__)
CONSOLE_DIR = REPO_ROOT / "apps" / "console"
OWNER_CONSOLE_DIR = REPO_ROOT / "apps" / "owner_console"
PUBLIC_SITE_DIR = REPO_ROOT / "apps" / "public_site"
PUBLIC_SITE_INDEX = PUBLIC_SITE_DIR / "index.html"
service = build_service(__file__, os.environ.get("NEXORA_STATE_PATH"))
logger = logging.getLogger("nexora.control_plane")
OPERATOR_ROLES = frozenset({"operator", "admin", "architect", "owner"})
OPERATOR_ONLY_ROUTES = frozenset(
    {
        "/api/persistence",
        "/api/interface-parity/fleet-lifecycle",
        "/api/docker/status",
        "/api/docker/containers",
        "/api/docker/templates",
        "/api/failover/strategies",
        "/api/storage/usage",
        "/api/storage/ynh-map",
        "/api/notifications/templates",
        "/api/sla/tiers",
        "/api/hooks/events",
        "/api/hooks/presets",
        "/api/automation/templates",
        "/api/automation/checklists",
        "/api/settings",
    }
)
SUBSCRIBER_DENIED_PREFIXES = (
    "/api/admin",
    "/api/mode",
    "/api/adoption/import",
    "/api/persistence",
    "/api/interface-parity",
    "/api/docker",
    "/api/failover",
    "/api/storage/ynh-map",
    "/api/notifications/templates",
    "/api/hooks",
    "/api/subscriptions",
    "/api/organizations",
    "/api/tenants",
    "/api/provisioning",
    "/api/settings",
)
SUBSCRIBER_ALLOWED_MUTATIONS = frozenset(
    {
        "/api/fleet/enroll/request",
        "/api/fleet/enroll/attest",
        "/api/fleet/enroll/register",
    }
)
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _load_public_landing_html() -> str:
    if PUBLIC_SITE_INDEX.exists():
        return PUBLIC_SITE_INDEX.read_text(encoding="utf-8")
    return """
<!doctype html>
<html lang="fr">
<head><meta charset="utf-8"/><title>Nexora SaaS</title></head>
<body>
<h1>Nexora SaaS</h1>
<p>Plateforme SaaS souveraine pour opérer vos noeuds YunoHost.</p>
<p><a href="subscribe">Souscrire</a></p>
</body>
</html>
""".strip()


def _load_subscription_landing_html() -> str:
    return """
<!doctype html>
<html lang="fr">
<head><meta charset="utf-8"/><title>Nexora — Souscription</title>
<style>
body{font-family:system-ui,sans-serif;max-width:800px;margin:2rem auto;padding:0 1rem;color:#1e293b}
h1{color:#4f46e5}
.plans{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1.5rem;margin:2rem 0}
.plan{border:2px solid #e2e8f0;border-radius:12px;padding:1.5rem;text-align:center}
.plan.pro{border-color:#4f46e5}
.plan h3{margin:0 0 .5rem}
.plan .price{font-size:2rem;font-weight:700;color:#4f46e5}
.plan ul{text-align:left;padding-left:1.2rem;font-size:.9rem}
.btn{display:inline-block;padding:.75rem 1.5rem;background:#4f46e5;color:#fff;border-radius:8px;text-decoration:none;margin-top:1rem}
.btn:hover{background:#4338ca}
</style>
</head>
<body>
<h1>Nexora SaaS — Souscription</h1>
<p>Plateforme souveraine pour orchestrer vos noeuds YunoHost.</p>
<div class="plans">
  <div class="plan">
    <h3>Starter</h3>
    <div class="price">Gratuit</div>
    <ul><li>5 noeuds</li><li>Monitoring basique</li><li>Backup local</li></ul>
    <a href="api/plans" class="btn">Commencer</a>
  </div>
  <div class="plan pro">
    <h3>Pro</h3>
    <div class="price">49€/mois</div>
    <ul><li>50 noeuds</li><li>Monitoring avancé</li><li>PRA</li><li>Automatisation</li></ul>
    <a href="api/plans" class="btn">Souscrire</a>
  </div>
  <div class="plan">
    <h3>Enterprise</h3>
    <div class="price">199€/mois</div>
    <ul><li>Illimité</li><li>Support 24/7</li><li>SLA garanti</li><li>Multi-région</li></ul>
    <a href="api/plans" class="btn">Contacter</a>
  </div>
</div>
<p><a href="/">← Retour à l'accueil</a></p>
</body>
</html>
""".strip()


def _enforce_operator_only_surface(
    trusted_actor_role: str | None,
    requested_actor_role: str | None,
) -> None:
    enforce = os.environ.get("NEXORA_OPERATOR_ONLY_ENFORCE", "1").strip().lower() not in {"0", "false", "no", "off"}
    if not enforce:
        return
    normalized_requested_role = (requested_actor_role or "").strip().lower()
    normalized_trusted_role = (trusted_actor_role or "").strip().lower()
    if normalized_requested_role and normalized_trusted_role and normalized_requested_role != normalized_trusted_role:
        raise HTTPException(
            status_code=403,
            detail="Operator-only route: requested actor role does not match trusted credentials",
        )
    if not normalized_requested_role:
        raise HTTPException(
            status_code=403,
            detail="Operator-only route: missing X-Nexora-Actor-Role header",
        )
    if normalized_trusted_role in OPERATOR_ROLES and normalized_requested_role in OPERATOR_ROLES:
        return
    raise HTTPException(
        status_code=403,
        detail="Operator-only route: authenticated credentials must be bound to operator/admin/architect role",
    )


def _is_operator_only_route(path: str) -> bool:
    normalized = path.rstrip("/") or "/"
    return normalized in OPERATOR_ONLY_ROUTES


def _is_subscriber_blocked(path: str, method: str) -> bool:
    normalized = path.rstrip("/") or "/"
    if normalized in OPERATOR_ONLY_ROUTES:
        return True
    if method not in SAFE_METHODS and normalized not in SUBSCRIBER_ALLOWED_MUTATIONS:
        return True
    for prefix in SUBSCRIBER_DENIED_PREFIXES:
        if normalized.startswith(prefix):
            return True
    return False


def _resolve_trusted_actor_role_from_request(request) -> str | None:
    state_role = getattr(request.state, "nexora_actor_role", None)
    if state_role:
        return str(state_role)

    auth_header = request.headers.get("Authorization", "")
    token = ""
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    if not token:
        token = request.headers.get("X-Nexora-Token", "").strip()
    if not token:
        return None

    for configured_token, role in _load_token_actor_roles().items():
        if secrets.compare_digest(token, configured_token):
            return role

    if secrets.compare_digest(token, get_api_token()):
        return resolve_actor_role_for_token(token)
    return None


def _is_operator_role(actor_role: str | None) -> bool:
    return (actor_role or "").strip().lower() in OPERATOR_ROLES


def _operator_tenant_id() -> str:
    value = os.environ.get("NEXORA_OPERATOR_TENANT_ID", "nexora-operator").strip()
    return value or "nexora-operator"


def _operator_org_id() -> str:
    value = os.environ.get("NEXORA_OPERATOR_ORG_ID", "org-nexora-operator").strip()
    return value or "org-nexora-operator"


def _ensure_operator_tenant_state() -> dict[str, object]:
    """Ensure the SaaS provider has a dedicated operator tenant and host node binding."""

    operator_tenant_id = _operator_tenant_id()
    operator_org_id = _operator_org_id()
    operator_org_name = os.environ.get("NEXORA_OPERATOR_ORG_NAME", "Nexora Operator").strip() or "Nexora Operator"
    operator_contact_email = os.environ.get("NEXORA_OPERATOR_CONTACT_EMAIL", "operator@nexora.local").strip() or "operator@nexora.local"
    operator_tier = os.environ.get("NEXORA_OPERATOR_TIER", "enterprise").strip().lower() or "enterprise"
    if operator_tier not in {"free", "pro", "enterprise"}:
        operator_tier = "enterprise"

    now_iso = datetime.now(timezone.utc).isoformat()
    state = service.state.load()
    changed = False

    organizations = state.setdefault("organizations", [])
    org_record = next(
        (
            org
            for org in organizations
            if isinstance(org, dict) and str(org.get("org_id", "")).strip() == operator_org_id
        ),
        None,
    )
    if org_record is None:
        organizations.append(
            {
                "org_id": operator_org_id,
                "name": operator_org_name,
                "contact_email": operator_contact_email,
                "billing_address": "",
                "created_at": now_iso,
                "status": "active",
            }
        )
        changed = True

    tenants = state.setdefault("tenants", [])
    tenant_record = next(
        (
            tenant
            for tenant in tenants
            if isinstance(tenant, dict) and str(tenant.get("tenant_id", "")).strip() == operator_tenant_id
        ),
        None,
    )
    if tenant_record is None:
        tenant_record = {
            "tenant_id": operator_tenant_id,
            "org_id": operator_org_id,
            "subscription_id": None,
            "tier": operator_tier,
            "label": operator_org_name,
            "created_at": now_iso,
            "status": "active",
        }
        tenants.append(tenant_record)
        changed = True
    else:
        if not tenant_record.get("org_id"):
            tenant_record["org_id"] = operator_org_id
            changed = True
        if not tenant_record.get("label"):
            tenant_record["label"] = operator_org_name
            changed = True

    local_node_id: str | None = None
    try:
        local_node_id = service.local_node_summary().node_id
    except Exception:
        local_node_id = None

    if local_node_id:
        for node in state.get("nodes", []):
            if not isinstance(node, dict) or str(node.get("node_id")) != str(local_node_id):
                continue
            if not node.get("tenant_id"):
                node["tenant_id"] = operator_tenant_id
                changed = True
            if not node.get("organization_id"):
                node["organization_id"] = operator_org_id
                changed = True
            break

    if changed:
        service.state.save(state)

    return {
        "tenant_id": operator_tenant_id,
        "organization_id": operator_org_id,
        "tenant": tenant_record,
        "changed": changed,
    }


def _resolve_runtime_mode() -> str:
    """Read runtime mode from the canonical mode manager state."""

    try:
        from nexora_saas.modes import get_mode_manager

        mode = str(get_mode_manager().get_mode_info().get("mode", "observer")).strip().lower()
        return mode or "observer"
    except Exception:
        state = service.state.load()
        return str(state.get("runtime_mode", "observer")).strip().lower() or "observer"


def _enforce_deployment_scope(path: str) -> None:
    """Enforce deployment scope restrictions based on NEXORA_DEPLOYMENT_SCOPE.

    When the env var is set (e.g. 'production', 'staging'), restrict dangerous
    operations to prevent accidental cross-environment calls.
    """
    scope = os.environ.get("NEXORA_DEPLOYMENT_SCOPE", "").strip().lower()
    if not scope:
        return
    # In production scope, block certain destructive endpoints
    if scope == "production":
        destructive = {"/api/tenants/{tenant_id}/purge", "/api/mode/switch"}
        normalized = path.rstrip("/") or "/"
        # Check prefix-based patterns
        for pattern in destructive:
            if "{" in pattern:
                prefix = pattern.split("{")[0]
                if normalized.startswith(prefix):
                    raise HTTPException(
                        status_code=403,
                        detail=f"Destructive operation blocked in deployment scope '{scope}'",
                    )
            elif normalized == pattern:
                raise HTTPException(
                    status_code=403,
                    detail=f"Operation blocked in deployment scope '{scope}'",
                )


class NodeActionRequest(BaseModel):
    action: str
    payload: dict[str, object] = Field(default_factory=dict)


class NodeActionPayloadRequest(BaseModel):
    payload: dict[str, object] = Field(default_factory=dict)
    dry_run: bool = False


class CreateOrgRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    contact_email: str = Field(..., min_length=3, max_length=200)
    billing_address: str = ""


class CreateSubscriptionRequest(BaseModel):
    org_id: str = Field(..., min_length=1)
    plan_tier: str = Field(..., pattern="^(free|pro|enterprise)$")
    tenant_label: str = ""


class UpgradeSubscriptionRequest(BaseModel):
    new_tier: str = Field(..., pattern="^(free|pro|enterprise)$")


class SuspendSubscriptionRequest(BaseModel):
    reason: str = ""


class OnboardTenantRequest(BaseModel):
    tenant_id: str = Field(..., min_length=1)
    organization_id: str = Field(..., min_length=1)
    tier: str = "free"


class ProvisionNodeRequest(BaseModel):
    node_id: str = Field(..., min_length=1)
    node_url: str = Field(..., min_length=1)
    hmac_secret: str = Field(..., min_length=32)
    api_token: str = ""
    tenant_id: str | None = None


class DeprovisionNodeRequest(BaseModel):
    node_id: str = Field(..., min_length=1)
    node_url: str = Field(..., min_length=1)
    hmac_secret: str = ""


class HeartbeatNodeRequest(BaseModel):
    node_id: str = Field(..., min_length=1)
    node_url: str = Field(..., min_length=1)
    hmac_secret: str = Field(..., min_length=32)
    api_token: str = ""
    lease_seconds: int = 86400


def _enforce_tenant_node_access(node_id: str, tenant_id: str | None) -> dict[str, object]:
    state = service.state.load()
    node_record = next(
        (node for node in state.get("nodes", []) if isinstance(node, dict) and str(node.get("node_id")) == node_id),
        None,
    )
    if node_record is None:
        raise HTTPException(status_code=404, detail=f"Unknown node_id: {node_id}")
    if tenant_id and node_record.get("tenant_id") != tenant_id:
        raise HTTPException(
            status_code=403,
            detail=f"node_id '{node_id}' is not enrolled under tenant '{tenant_id}'",
        )
    return node_record


def build_application() -> FastAPI:
    setup_logging()
    app = FastAPI(
        title="Nexora Control Plane",
        version=NEXORA_VERSION,
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
    )
    app.add_middleware(TokenAuthMiddleware)
    app.add_middleware(CSRFProtectionMiddleware)

    @app.middleware("http")
    async def deployment_scope_middleware(request, call_next):
        try:
            _enforce_deployment_scope(request.url.path)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        return await call_next(request)

    @app.middleware("http")
    async def operator_only_surface_middleware(request, call_next):
        if _is_operator_only_route(request.url.path):
            try:
                _enforce_operator_only_surface(
                    _resolve_trusted_actor_role_from_request(request),
                    request.headers.get("X-Nexora-Actor-Role"),
                )
            except HTTPException as exc:
                return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        return await call_next(request)

    @app.middleware("http")
    async def subscriber_surface_middleware(request, call_next):
        trusted_role = (_resolve_trusted_actor_role_from_request(request) or "").strip().lower()
        if trusted_role == "subscriber" and _is_subscriber_blocked(request.url.path, request.method):
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "Subscriber profile is restricted to tenant-scoped monitoring and enrollment surfaces."
                },
            )
        return await call_next(request)

    @app.middleware("http")
    async def surface_isolation_middleware(request, call_next):
        """Enforce subdomain-based surface isolation.

        - saas.* surface: only owner sessions allowed (no subscriber tokens)
        - console.* surface: only subscriber/operator tokens allowed (no owner sessions)
        - public / www.*: only public endpoints
        - '' (no subdomain): no restriction (single-domain / test / direct)
        """
        surface = resolve_surface(request)
        request.state.nexora_surface = surface
        path = request.url.path

        # No recognized subdomain → no surface restriction
        if not surface:
            return await call_next(request)

        # Public surface: only allow public endpoints and static assets
        if surface == "public":
            public_allowed = {"/", "/subscribe", "/api/health", "/health", "/api/public/offers", "/api/plans"}
            if path in public_allowed or path.startswith("/public_site/"):
                return await call_next(request)
            # Allow API endpoints needed for subscription flow
            if path.startswith("/api/public/"):
                return await call_next(request)
            return JSONResponse(
                status_code=403,
                content={"detail": "This endpoint is not available on the public site."},
            )

        # SaaS owner surface: block subscriber token access
        if surface == "saas":
            trusted_role = (_resolve_trusted_actor_role_from_request(request) or "").strip().lower()
            is_owner_session = getattr(request.state, "nexora_owner_session", False)
            # Allow public auth endpoints and static assets
            if path in {"/", "/api/auth/owner-login", "/api/health", "/owner-console", "/owner-console/"} or path.startswith("/owner-console/"):
                return await call_next(request)
            # For API endpoints, require owner session
            if path.startswith("/api/") and not is_owner_session and trusted_role != "owner":
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Owner console requires owner authentication."},
                )

        # Console subscriber surface: block owner-only access
        if surface == "console":
            is_owner_session = getattr(request.state, "nexora_owner_session", False)
            if is_owner_session:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Owner sessions are not valid on the subscriber console."},
                )

        return await call_next(request)

    register_public_routes(app)
    register_health_routes(app)
    register_inventory_routes(app)
    register_fleet_routes(app)
    register_catalog_routes(app)
    register_governance_routes(app)
    register_modes_routes(app)
    register_operations_routes(app)
    register_auth_routes(app)
    register_subscription_routes(app)
    register_tenant_management_routes(app)
    register_provisioning_routes(app)
    register_console_routes(app)
    register_owner_auth_routes(app)
    register_docker_extended_routes(app)
    register_blueprint_deploy_routes(app)
    register_ynh_catalog_routes(app)
    register_ynh_service_mgmt_routes(app)
    register_failover_execution_routes(app)
    register_app_migration_routes(app)

    @app.on_event("startup")
    async def _register_host_node() -> None:
        """Auto-register the local host as the first fleet node on startup."""
        try:
            state = service.state.load()
            local = service.local_node_summary()
            nodes = state.get("nodes", [])
            host_exists = any(
                isinstance(n, dict) and n.get("node_id") == local.node_id
                for n in nodes
            )
            if not host_exists:
                from nexora_node_sdk.state import normalize_node_record, transition_node_status
                from datetime import datetime, timezone as _tz

                node_record = normalize_node_record({
                    "node_id": local.node_id,
                    "hostname": local.node_id,
                    "status": local.status,
                    "apps_count": local.apps_count,
                    "domains_count": local.domains_count,
                    "health_score": local.health_score,
                    "registered_at": datetime.now(_tz.utc).isoformat(),
                    "role": "host",
                    "tenant_id": _operator_tenant_id(),
                    "organization_id": _operator_org_id(),
                })
                node_record = transition_node_status(node_record, local.status or "healthy")
                state.setdefault("nodes", []).append(node_record)
                if local.node_id not in state.get("fleet", {}).get("managed_nodes", []):
                    state.setdefault("fleet", {}).setdefault("managed_nodes", []).append(local.node_id)
                service.state.save(state)
            _ensure_operator_tenant_state()
        except Exception as exc:
            logger.warning("Host self-registration skipped: %s", exc)

    return app


def register_public_routes(app: FastAPI) -> None:
    def public_offers() -> dict[str, object]:
        return {
            "platform": "Nexora SaaS",
            "positioning": "Surcouche SaaS souveraine pour masquer la complexite des noeuds YunoHost.",
            "offers": [
                {
                    "offer_id": "starter-subscriber",
                    "name": "Subscriber Starter",
                    "target": "PME ou freelance",
                    "max_nodes": 3,
                    "max_apps": 25,
                    "features": ["enrollment", "monitoring", "alerts", "backup snapshots"],
                },
                {
                    "offer_id": "pro-subscriber",
                    "name": "Subscriber Pro",
                    "target": "MSP ou equipe multi-sites",
                    "max_nodes": 15,
                    "max_apps": 120,
                    "features": ["multi-tenant", "fleet lifecycle", "automation", "PRA workflows"],
                },
                {
                    "offer_id": "operator-admin",
                    "name": "SaaS Operator Admin",
                    "target": "Operateur Nexora",
                    "max_nodes": "unlimited",
                    "max_apps": "unlimited",
                    "features": [
                        "operator-only governance",
                        "tenant management",
                        "infrastructure reinforcement",
                        "commercial onboarding",
                    ],
                },
            ],
            "enrollment_api": "/api/fleet/enroll/request",
        }

    app.add_api_route("/api/public/offers", public_offers, methods=["GET"])


def register_auth_routes(app: FastAPI) -> None:
    def tenant_claim(
        request: Request,
        tenant_id: str = Query(..., min_length=1),
    ) -> dict[str, str]:
        auth_header = request.headers.get("Authorization", "")
        provided_token = ""
        if auth_header.startswith("Bearer "):
            provided_token = auth_header[7:].strip()
        if not provided_token:
            provided_token = request.headers.get("X-Nexora-Token", "").strip()
        if not provided_token:
            raise HTTPException(status_code=401, detail="Authentication required")
        return {
            "tenant_id": tenant_id,
            "claim": build_tenant_scope_claim(provided_token, tenant_id),
        }

    def console_access_context(
        request: Request,
        x_nexora_tenant_id: str | None = Header(None),
    ) -> dict[str, object]:
        # Check for owner session first
        is_owner_session = getattr(request.state, "nexora_owner_session", False)
        if is_owner_session:
            owner_tid = getattr(request.state, "nexora_tenant_id", None) or _owner_tenant_id_from_session()
            trusted_role = "owner"
        else:
            trusted_role = (_resolve_trusted_actor_role_from_request(request) or "observer").strip().lower()
            owner_tid = None

        requested_tenant_id = (x_nexora_tenant_id or "").strip() or None
        surface = getattr(request.state, "nexora_surface", "console")

        # Determine if this is an operator-level role (SaaS provider)
        is_operator = _is_operator_role(trusted_role)
        operator_tenant_id = _operator_tenant_id()
        tenant_source = "header" if requested_tenant_id else "none"

        if is_operator or is_owner_session:
            _ensure_operator_tenant_state()

        effective_tenant_id = requested_tenant_id
        if is_owner_session and not effective_tenant_id:
            effective_tenant_id = owner_tid or operator_tenant_id
            tenant_source = "owner-default"
        elif is_operator and not effective_tenant_id:
            effective_tenant_id = operator_tenant_id
            tenant_source = "operator-default"

        state = service.state.load()
        tenant_record: dict[str, object] | None = None
        if effective_tenant_id:
            tenant_record = next(
                (
                    tenant
                    for tenant in state.get("tenants", [])
                    if isinstance(tenant, dict) and tenant.get("tenant_id") == effective_tenant_id
                ),
                None,
            )

        # Resolve the runtime operating mode (observer/operator/architect/admin)
        runtime_mode = _resolve_runtime_mode()

        # Section definitions by access level
        # Subscriber: monitoring & enrollment only
        subscriber_sections = [
            "dashboard",
            "scores",
            "apps",
            "services",
            "domains",
            "security",
            "pra",
            "fleet",
        ]
        observer_sections = [
            "dashboard",
            "scores",
            "apps",
            "services",
            "domains",
            "security",
            "pra",
            "fleet",
            "governance",
            "sla-tracking",
        ]
        # Operator: all infrastructure + governance
        operator_sections = [
            "dashboard",
            "scores",
            "apps",
            "services",
            "domains",
            "security",
            "pra",
            "fleet",
            "blueprints",
            "automation",
            "adoption",
            "modes",
            "docker",
            "storage",
            "notifications",
            "hooks",
            "governance",
            "sla-tracking",
            "subscription",
            "provisioning",
            "settings",
            "catalog",
            "failover",
            "migration",
        ]
        # Owner: full SaaS administration — everything including tenant management
        owner_sections = operator_sections + ["tenants"]

        # Cross-tenant stats for operator dashboard
        operator_stats: dict[str, object] | None = None
        if is_operator:
            tenants = [t for t in state.get("tenants", []) if isinstance(t, dict)]
            orgs = [o for o in state.get("organizations", []) if isinstance(o, dict)]
            subs = [s for s in state.get("subscriptions", []) if isinstance(s, dict)]
            nodes = [n for n in state.get("nodes", []) if isinstance(n, dict)]
            active_subs = [s for s in subs if s.get("status") == "active"]
            operator_stats = {
                "total_tenants": len(tenants),
                "total_organizations": len(orgs),
                "total_subscriptions": len(subs),
                "active_subscriptions": len(active_subs),
                "total_nodes": len(nodes),
                "healthy_nodes": len([n for n in nodes if n.get("status") in ("healthy", "registered")]),
            }

        if trusted_role == "subscriber":
            allowed_sections = subscriber_sections
        elif is_owner_session or trusted_role == "owner":
            allowed_sections = owner_sections
        elif is_operator:
            allowed_sections = operator_sections
        else:
            allowed_sections = observer_sections

        return {
            "actor_role": trusted_role,
            "runtime_mode": runtime_mode,
            "runtime_mode_is_operator": _is_operator_role(runtime_mode),
            "is_operator": is_operator,
            "is_owner": is_owner_session or trusted_role == "owner",
            "surface": surface,
            "operator_tenant_id": operator_tenant_id if (is_operator or is_owner_session) else None,
            "tenant_id": effective_tenant_id,
            "requested_tenant_id": requested_tenant_id,
            "tenant_source": tenant_source,
            "tenant": tenant_record,
            "allowed_sections": allowed_sections,
            "subscriber_mode": trusted_role == "subscriber",
            "operator_stats": operator_stats,
            "platform_version": NEXORA_VERSION,
        }

    app.add_api_route("/api/auth/tenant-claim", tenant_claim, methods=["GET"])
    app.add_api_route("/api/console/access-context", console_access_context, methods=["GET"])


def register_health_routes(app: FastAPI) -> None:
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "service": "nexora-control-plane",
            "version": NEXORA_VERSION,
            "compatibility": service.compatibility_report()["assessment"],
        }

    app.add_api_route("/api/health", health, methods=["GET"])
    app.add_api_route("/api/v1/health", health, methods=["GET"])


def register_inventory_routes(app: FastAPI) -> None:
    def dashboard(x_nexora_tenant_id: str | None = Header(None)) -> dict[str, object]:
        return service.dashboard(tenant_id=x_nexora_tenant_id).model_dump()

    def inventory_local() -> dict[str, object]:
        return service.local_inventory()

    def inventory_section(section: str) -> dict[str, object]:
        if section == "services":
            from nexora_node_sdk.yh_adapter import services_with_fallback
            return services_with_fallback()
        return service.inventory_slice(section)

    app.add_api_route("/api/dashboard", dashboard, methods=["GET"])
    app.add_api_route("/api/v1/dashboard", dashboard, methods=["GET"])
    app.add_api_route("/api/inventory/local", inventory_local, methods=["GET"])
    app.add_api_route("/api/inventory/{section}", inventory_section, methods=["GET"])


def register_fleet_routes(app: FastAPI) -> None:
    from nexora_node_sdk.node_actions import execute_node_action

    def fleet(x_nexora_tenant_id: str | None = Header(None)) -> dict[str, object]:
        return service.fleet_summary(tenant_id=x_nexora_tenant_id).model_dump()

    def fleet_topology(
        x_nexora_tenant_id: str | None = Header(None),
    ) -> dict[str, object]:
        from nexora_saas.fleet import generate_fleet_topology

        state = service.state.load()
        nodes_raw = state.get("nodes", [])
        if x_nexora_tenant_id:
            nodes_raw = [
                node for node in nodes_raw if isinstance(node, dict) and node.get("tenant_id") == x_nexora_tenant_id
            ]
        nodes = [{"node_id": n.get("node_id"), "inventory": {}, "status": n.get("status")} for n in nodes_raw]
        return generate_fleet_topology(nodes)

    def fleet_lifecycle(
        x_nexora_tenant_id: str | None = Header(None),
    ) -> dict[str, object]:
        return service.fleet_lifecycle(tenant_id=x_nexora_tenant_id)

    def fleet_compatibility() -> dict[str, object]:
        return service.compatibility_report()

    def fleet_enroll_request(
        request: EnrollmentTokenRequest, x_nexora_tenant_id: str | None = Header(None)
    ) -> dict[str, object]:
        return service.request_enrollment_token(
            requested_by=request.requested_by,
            mode=request.mode,
            ttl_minutes=request.ttl_minutes,
            node_id=request.node_id,
            tenant_id=x_nexora_tenant_id,
        )

    def fleet_enroll_attest(request: EnrollmentAttestationRequest = Body(...)) -> dict[str, object]:
        return service.attest_enrollment(**request.model_dump())

    def fleet_enroll_register(request: EnrollmentRegisterRequest = Body(...)) -> dict[str, object]:
        return service.register_enrolled_node(**request.model_dump())

    app.add_api_route("/api/fleet", fleet, methods=["GET"])
    app.add_api_route("/api/v1/fleet", fleet, methods=["GET"])
    app.add_api_route("/api/fleet/topology", fleet_topology, methods=["GET"])
    app.add_api_route("/api/fleet/lifecycle", fleet_lifecycle, methods=["GET"])
    app.add_api_route("/api/fleet/compatibility", fleet_compatibility, methods=["GET"])
    app.add_api_route("/api/fleet/enroll/request", fleet_enroll_request, methods=["POST"])
    app.add_api_route("/api/fleet/enroll/attest", fleet_enroll_attest, methods=["POST"])
    app.add_api_route("/api/fleet/enroll/register", fleet_enroll_register, methods=["POST"])

    lifecycle_actions = {
        "drain": "/api/fleet/nodes/{node_id}/drain",
        "cordon": "/api/fleet/nodes/{node_id}/cordon",
        "uncordon": "/api/fleet/nodes/{node_id}/uncordon",
        "revoke": "/api/fleet/nodes/{node_id}/revoke",
        "retire": "/api/fleet/nodes/{node_id}/retire",
        "rotate_credentials": "/api/fleet/nodes/{node_id}/rotate-credentials",
        "re_enroll": "/api/fleet/nodes/{node_id}/re-enroll",
        "delete": "/api/fleet/nodes/{node_id}/delete",
    }

    for action, path in lifecycle_actions.items():
        app.add_api_route(
            path,
            _build_lifecycle_route(action),
            methods=["POST"],
            name=f"fleet-{action}",
        )

    def _execute_fleet_node_action(
        node_id: str,
        *,
        action: str,
        payload: dict[str, object] | None,
        tenant_id: str | None,
        dry_run: bool = False,
    ) -> dict[str, object]:
        _enforce_tenant_node_access(node_id, tenant_id)
        normalized_payload = dict(payload or {})
        normalized_payload.setdefault("node_id", node_id)
        normalized_payload.setdefault("execution_scope", "fleet-node-action")
        result = execute_node_action(service, action, dry_run=dry_run, params=normalized_payload)
        result.setdefault("target_node_id", node_id)
        return result

    def fleet_node_action(
        node_id: str,
        request: NodeActionRequest,
        x_nexora_tenant_id: str | None = Header(None),
    ) -> dict[str, object]:
        return _execute_fleet_node_action(
            node_id,
            action=request.action,
            payload=request.payload,
            tenant_id=x_nexora_tenant_id,
            dry_run=False,
        )

    def _build_node_action_route(action_name: str):
        def route(
            node_id: str,
            request: NodeActionPayloadRequest,
            x_nexora_tenant_id: str | None = Header(None),
        ) -> dict[str, object]:
            return _execute_fleet_node_action(
                node_id,
                action=action_name,
                payload=request.payload,
                tenant_id=x_nexora_tenant_id,
                dry_run=request.dry_run,
            )

        return route

    app.add_api_route(
        "/api/fleet/nodes/{node_id}/action",
        fleet_node_action,
        methods=["POST"],
        name="fleet-node-action",
    )

    dedicated_actions = {
        "branding/apply": "/api/fleet/nodes/{node_id}/branding/apply",
        "inventory/refresh": "/api/fleet/nodes/{node_id}/inventory/refresh",
        "permissions/sync": "/api/fleet/nodes/{node_id}/permissions/sync",
        "pra/snapshot": "/api/fleet/nodes/{node_id}/pra/snapshot",
        "maintenance/enable": "/api/fleet/nodes/{node_id}/maintenance/enable",
        "maintenance/disable": "/api/fleet/nodes/{node_id}/maintenance/disable",
        "docker/compose/apply": "/api/fleet/nodes/{node_id}/docker/compose/apply",
        "healthcheck/run": "/api/fleet/nodes/{node_id}/healthcheck/run",
    }
    for action_name, route_path in dedicated_actions.items():
        app.add_api_route(
            route_path,
            _build_node_action_route(action_name),
            methods=["POST"],
            name=f"fleet-node-action-{action_name.replace('/', '-')}",
        )


def _build_lifecycle_route(action: str):
    def route(
        node_id: str,
        request: LifecycleActionRequest,
        x_nexora_tenant_id: str | None = Header(None),
    ) -> dict[str, object]:
        _enforce_tenant_node_access(node_id, x_nexora_tenant_id)
        return service.run_lifecycle_action(
            node_id=node_id,
            action=action,
            operator=request.operator,
            confirmation=request.confirmation,
        )

    return route


def register_catalog_routes(app: FastAPI) -> None:
    def blueprints() -> list[dict[str, object]]:
        return [bp.model_dump() for bp in service.list_blueprints()]

    def blueprint_detail(slug: str) -> dict[str, object]:
        bp = next((b for b in service.list_blueprints() if b.slug == slug), None)
        if not bp:
            return {"error": f"Blueprint '{slug}' not found"}
        return bp.model_dump()

    def branding(slug: str | None = None) -> dict[str, object]:
        return service.branding_profile(slug)

    def identity() -> dict[str, object]:
        return service.identity()

    def portal_palettes() -> list[dict[str, object]]:
        from nexora_saas.portal import list_available_palettes

        return list_available_palettes()

    def portal_sectors() -> list[dict[str, object]]:
        from nexora_saas.portal import list_sector_themes

        return list_sector_themes()

    def capabilities() -> dict[str, object]:
        from nexora_node_sdk.capabilities import capability_catalog_payload

        return capability_catalog_payload()

    app.add_api_route("/api/blueprints", blueprints, methods=["GET"])
    app.add_api_route("/api/blueprints/{slug}", blueprint_detail, methods=["GET"])
    app.add_api_route("/api/branding", branding, methods=["GET"])
    app.add_api_route("/api/identity", identity, methods=["GET"])
    app.add_api_route("/api/capabilities", capabilities, methods=["GET"])
    app.add_api_route("/api/portal/palettes", portal_palettes, methods=["GET"])
    app.add_api_route("/api/portal/sectors", portal_sectors, methods=["GET"])


def register_governance_routes(app: FastAPI) -> None:
    def _governance_inventory(tenant_id: str | None) -> dict[str, object]:
        if not tenant_id:
            return service.local_inventory()
        snapshots = service.state.load().get("inventory_snapshots", [])
        for snapshot in reversed(snapshots):
            if not isinstance(snapshot, dict):
                continue
            if snapshot.get("tenant_id") != tenant_id:
                continue
            inventory = snapshot.get("inventory")
            if isinstance(inventory, dict):
                return inventory
        return {}

    def all_scores(x_nexora_tenant_id: str | None = Header(None)) -> dict[str, object]:
        from nexora_node_sdk.scoring import (
            compute_compliance_score,
            compute_health_score,
            compute_pra_score,
            compute_security_score,
        )

        inv = _governance_inventory(x_nexora_tenant_id)
        sec = compute_security_score(inv)
        pra = compute_pra_score(inv)
        hlth = compute_health_score(inv)
        comp = compute_compliance_score(inv, has_pra=True, has_monitoring=True)
        payload = {
            "security": {"score": sec["score"], "grade": sec["grade"]},
            "pra": {"score": pra["score"], "grade": pra["grade"]},
            "health": {"score": hlth["score"], "grade": hlth["grade"]},
            "compliance": {"score": comp["score"], "level": comp["maturity_level"]},
            "overall": int((sec["score"] + pra["score"] + hlth["score"] + comp["score"]) / 4),
        }
        if x_nexora_tenant_id:
            payload["tenant_id"] = x_nexora_tenant_id
        return payload

    def executive_report(
        x_nexora_tenant_id: str | None = Header(None),
    ) -> dict[str, object]:
        from nexora_node_sdk.governance import executive_report as _report

        inv = _governance_inventory(x_nexora_tenant_id)
        report = _report(inv, has_pra=True, has_monitoring=True)
        if x_nexora_tenant_id:
            report["tenant_id"] = x_nexora_tenant_id
        return report

    def risk_register(
        x_nexora_tenant_id: str | None = Header(None),
    ) -> dict[str, object]:
        from nexora_node_sdk.governance import risk_register as _risks

        inv = _governance_inventory(x_nexora_tenant_id)
        payload = _risks(inv)
        if x_nexora_tenant_id:
            payload["tenant_id"] = x_nexora_tenant_id
        return payload

    def security_posture(
        x_nexora_tenant_id: str | None = Header(None),
    ) -> dict[str, object]:
        dash = service.dashboard(tenant_id=x_nexora_tenant_id).model_dump()
        if x_nexora_tenant_id:
            tenant_inv = _governance_inventory(x_nexora_tenant_id)
            perms_section = tenant_inv.get("permissions", {}) if isinstance(tenant_inv, dict) else {}
            perms = perms_section.get("permissions", {}) if isinstance(perms_section, dict) else {}
        else:
            perms = service.inventory_slice("permissions").get("permissions", {})
        public_apps = [
            name for name, perm in perms.items() if isinstance(perm, dict) and "visitors" in perm.get("allowed", [])
        ]
        payload = {
            "security_score": dash["node"]["security_score"],
            "alerts": dash["alerts"],
            "permissions_risk_count": len(public_apps),
            "public_permissions": public_apps,
        }
        if x_nexora_tenant_id:
            payload["tenant_id"] = x_nexora_tenant_id
        return payload

    def pra(x_nexora_tenant_id: str | None = Header(None)) -> dict[str, object]:
        dash = service.dashboard(tenant_id=x_nexora_tenant_id).model_dump()
        payload = {
            "pra_score": dash["node"]["pra_score"],
            "backups_count": dash["node"]["backups_count"],
            "runbooks": ["inventory", "rebuild", "restore", "dns-cutover"],
        }
        if x_nexora_tenant_id:
            payload["tenant_id"] = x_nexora_tenant_id
        return payload

    def change_log(x_nexora_tenant_id: str | None = Header(None)) -> dict[str, object]:
        from nexora_node_sdk.governance import change_log as _cl

        snapshots = service.state.load().get("inventory_snapshots", [])
        if x_nexora_tenant_id:
            # Note: snapshots would need to be tagged with tenant_id during creation.
            # For now, we filter if the snapshot has the field.
            snapshots = [s for s in snapshots if s.get("tenant_id") == x_nexora_tenant_id]
        return _cl(snapshots)

    def snapshot_diff(
        x_nexora_tenant_id: str | None = Header(None),
    ) -> dict[str, object]:
        snapshots = service.state.load().get("inventory_snapshots", [])
        if x_nexora_tenant_id:
            snapshots = [s for s in snapshots if s.get("tenant_id") == x_nexora_tenant_id]
        if len(snapshots) < 2:
            return {"diff": {}}
        from nexora_node_sdk.scoring import diff_snapshots

        return diff_snapshots(snapshots[-2].get("inventory", {}), snapshots[-1].get("inventory", {}))

    def security_updates(
        x_nexora_tenant_id: str | None = Header(None),
    ) -> dict[str, object]:
        state = service.state.load()
        # Derive update info from inventory snapshots
        snapshots = state.get("inventory_snapshots", [])
        if x_nexora_tenant_id:
            snapshots = [s for s in snapshots if s.get("tenant_id") == x_nexora_tenant_id]
        latest_inv = snapshots[-1].get("inventory", {}) if snapshots else {}
        system_info = latest_inv.get("system", {})
        packages: list[dict[str, object]] = []
        for pkg_name, pkg_info in (system_info.get("packages", {}) or {}).items():
            if isinstance(pkg_info, dict) and pkg_info.get("update_available"):
                packages.append({"name": pkg_name, "current": pkg_info.get("version", ""), "available": pkg_info.get("update_version", "")})
        payload: dict[str, object] = {
            "updates_available": len(packages) > 0,
            "packages": packages,
            "last_check": snapshots[-1].get("timestamp") if snapshots else None,
        }
        if x_nexora_tenant_id:
            payload["tenant_id"] = x_nexora_tenant_id
        return payload

    def fail2ban_status(
        x_nexora_tenant_id: str | None = Header(None),
    ) -> dict[str, object]:
        state = service.state.load()
        # Derive fail2ban info from security audit events
        audit = state.get("security_audit", [])
        if isinstance(audit, dict):
            audit = audit.get("events", [])
        ban_events = [e for e in audit if isinstance(e, dict) and e.get("action") in ("fail2ban_ban", "fail2ban_unban")]
        if x_nexora_tenant_id:
            ban_events = [e for e in ban_events if e.get("tenant_id") == x_nexora_tenant_id]
        # Track currently banned IPs (ban adds, unban removes)
        banned: set[str] = set()
        for evt in ban_events:
            ip = (evt.get("details") or {}).get("ip", "")
            if evt.get("action") == "fail2ban_ban" and ip:
                banned.add(ip)
            elif evt.get("action") == "fail2ban_unban" and ip:
                banned.discard(ip)
        payload: dict[str, object] = {
            "active": True,
            "banned_ips": sorted(banned),
            "total_ban_events": len([e for e in ban_events if e.get("action") == "fail2ban_ban"]),
        }
        if x_nexora_tenant_id:
            payload["tenant_id"] = x_nexora_tenant_id
        return payload

    def fail2ban_ban(ip: str = Query(...), x_nexora_tenant_id: str | None = Header(None)) -> dict[str, object]:
        state = service.state.load()
        from nexora_node_sdk.security_audit import emit_security_event

        emit_security_event(
            state,
            "auth",
            "fail2ban_ban",
            severity="warning",
            tenant_id=x_nexora_tenant_id,
            ip=ip,
        )
        service.state.save(state)
        payload: dict[str, object] = {"success": True, "banned": ip}
        if x_nexora_tenant_id:
            payload["tenant_id"] = x_nexora_tenant_id
        return payload

    def fail2ban_unban(ip: str = Query(...), x_nexora_tenant_id: str | None = Header(None)) -> dict[str, object]:
        state = service.state.load()
        from nexora_node_sdk.security_audit import emit_security_event

        emit_security_event(
            state,
            "auth",
            "fail2ban_unban",
            severity="info",
            tenant_id=x_nexora_tenant_id,
            ip=ip,
        )
        service.state.save(state)
        payload: dict[str, object] = {"success": True, "unbanned": ip}
        if x_nexora_tenant_id:
            payload["tenant_id"] = x_nexora_tenant_id
        return payload

    def open_ports(x_nexora_tenant_id: str | None = Header(None)) -> dict[str, object]:
        state = service.state.load()
        # Derive open ports from latest inventory snapshot
        snapshots = state.get("inventory_snapshots", [])
        if x_nexora_tenant_id:
            snapshots = [s for s in snapshots if s.get("tenant_id") == x_nexora_tenant_id]
        latest_inv = snapshots[-1].get("inventory", {}) if snapshots else {}
        firewall = latest_inv.get("firewall", {})
        ports = firewall.get("ports", [22, 80, 443]) if firewall else [22, 80, 443]
        payload: dict[str, object] = {
            "ports": ports,
            "source": "inventory" if firewall else "default",
        }
        if x_nexora_tenant_id:
            payload["tenant_id"] = x_nexora_tenant_id
        return payload

    def permissions_audit(
        x_nexora_tenant_id: str | None = Header(None),
    ) -> dict[str, object]:
        state = service.state.load()
        # Derive permissions from security posture
        from nexora_node_sdk.security_audit import filter_security_events
        audit = state.get("security_audit", [])
        if isinstance(audit, dict):
            audit = audit.get("events", [])
        auth_events = filter_security_events(audit, category="auth")
        if x_nexora_tenant_id:
            auth_events = [e for e in auth_events if e.get("tenant_id") == x_nexora_tenant_id]
        # Check posture for public permissions
        posture = security_posture(x_nexora_tenant_id=x_nexora_tenant_id)
        public_apps = posture.get("public_permissions", [])
        payload: dict[str, object] = {
            "audit": "warning" if public_apps else "ok",
            "public_apps": public_apps,
            "auth_events_count": len(auth_events),
            "permissions_risk_count": posture.get("permissions_risk_count", 0),
        }
        if x_nexora_tenant_id:
            payload["tenant_id"] = x_nexora_tenant_id
        return payload

    def recent_logins(
        x_nexora_tenant_id: str | None = Header(None),
    ) -> dict[str, object]:
        state = service.state.load()
        # Derive login events from security audit
        from nexora_node_sdk.security_audit import filter_security_events
        audit = state.get("security_audit", [])
        if isinstance(audit, dict):
            audit = audit.get("events", [])
        login_events = filter_security_events(audit, category="auth")
        if x_nexora_tenant_id:
            login_events = [e for e in login_events if e.get("tenant_id") == x_nexora_tenant_id]
        # Return last 50 auth events as login entries
        recent = login_events[-50:] if login_events else []
        logins = []
        for evt in recent:
            logins.append({
                "timestamp": evt.get("timestamp", ""),
                "action": evt.get("action", ""),
                "severity": evt.get("severity", "info"),
                "details": evt.get("details", {}),
            })
        payload: dict[str, object] = {
            "logins": logins,
            "total_auth_events": len(login_events),
        }
        if x_nexora_tenant_id:
            payload["tenant_id"] = x_nexora_tenant_id
        return payload

    app.add_api_route("/api/scores", all_scores, methods=["GET"])
    app.add_api_route("/api/governance/report", executive_report, methods=["GET"])
    app.add_api_route("/api/governance/risks", risk_register, methods=["GET"])
    app.add_api_route("/api/security/posture", security_posture, methods=["GET"])
    app.add_api_route("/api/pra", pra, methods=["GET"])
    app.add_api_route("/api/governance/changelog", change_log, methods=["GET"])
    app.add_api_route("/api/governance/snapshot-diff", snapshot_diff, methods=["GET"])
    app.add_api_route("/api/security/updates", security_updates, methods=["GET"])
    app.add_api_route("/api/security/fail2ban/status", fail2ban_status, methods=["GET"])
    app.add_api_route("/api/security/fail2ban/ban", fail2ban_ban, methods=["POST"])
    app.add_api_route("/api/security/fail2ban/unban", fail2ban_unban, methods=["POST"])
    app.add_api_route("/api/security/open-ports", open_ports, methods=["GET"])
    app.add_api_route("/api/security/permissions-audit", permissions_audit, methods=["GET"])
    app.add_api_route("/api/security/recent-logins", recent_logins, methods=["GET"])


def register_modes_routes(app: FastAPI) -> None:
    def get_mode() -> dict[str, object]:
        from nexora_saas.modes import get_mode_manager

        return get_mode_manager().get_mode_info()

    def list_modes() -> list[dict[str, object]]:
        from nexora_saas.modes import list_modes as _list

        return _list()

    def switch_mode(target: str = Query(...), reason: str = Query("")) -> dict[str, object]:
        from nexora_saas.modes import get_mode_manager

        return get_mode_manager().switch_mode(target, reason=reason, operator="api")

    def escalate_mode(
        target: str = Query(...),
        duration_minutes: int = Query(60),
        reason: str = Query(""),
    ) -> dict[str, object]:
        from nexora_saas.modes import get_mode_manager

        manager = get_mode_manager()
        return manager.create_escalation_token(
            target,
            duration_seconds=min(duration_minutes, 480) * 60,
            reason=reason,
        )

    def list_escalations() -> list[dict[str, object]]:
        from nexora_saas.modes import get_mode_manager

        return get_mode_manager().list_escalation_tokens()

    def pending_confirmations() -> list[dict[str, object]]:
        from nexora_saas.modes import list_pending_confirmations

        return list_pending_confirmations()

    def admin_log(
        x_nexora_tenant_id: str | None = Header(None),
    ) -> list[dict[str, object]]:
        from nexora_saas.admin_actions import get_admin_action_log

        log = get_admin_action_log(50)
        if x_nexora_tenant_id:
            log = [entry for entry in log if entry.get("tenant_id") == x_nexora_tenant_id]
        return log

    app.add_api_route("/api/mode", get_mode, methods=["GET"])
    app.add_api_route("/api/mode/list", list_modes, methods=["GET"])
    app.add_api_route("/api/mode/switch", switch_mode, methods=["POST"])
    app.add_api_route("/api/mode/escalate", escalate_mode, methods=["POST"])
    app.add_api_route("/api/mode/escalations", list_escalations, methods=["GET"])
    app.add_api_route("/api/mode/confirmations", pending_confirmations, methods=["GET"])
    app.add_api_route("/api/admin/log", admin_log, methods=["GET"])


def register_operations_routes(app: FastAPI) -> None:
    def adoption_report(domain: str | None = Query(None), path: str | None = Query(None)) -> dict[str, object]:
        return service.adoption_report(domain, path)

    def adoption_import(domain: str | None = Query(None), path: str | None = Query(None)) -> dict[str, object]:
        return service.import_existing_state(domain, path)

    def docker_status() -> dict[str, object]:
        from nexora_node_sdk.docker import docker_info

        return docker_info()

    def docker_containers() -> list[dict[str, object]]:
        from nexora_node_sdk.docker import list_containers

        return list_containers(True)

    def docker_templates() -> list[dict[str, object]]:
        from nexora_node_sdk.docker import list_docker_templates

        return list_docker_templates()

    def failover_strategies() -> list[dict[str, object]]:
        from nexora_saas.failover import list_health_check_strategies

        return list_health_check_strategies()

    def storage_usage() -> dict[str, object]:
        from nexora_node_sdk.storage import disk_usage_detailed

        return disk_usage_detailed()

    def storage_ynh_map() -> dict[str, object]:
        from nexora_node_sdk.storage import yunohost_storage_map

        return yunohost_storage_map()

    def notification_templates() -> list[dict[str, object]]:
        from nexora_saas.notifications import list_alert_templates

        return list_alert_templates()

    def sla_tiers() -> list[dict[str, object]]:
        from nexora_saas.sla import list_sla_tiers

        return list_sla_tiers()

    def hook_events() -> list[dict[str, object]]:
        from nexora_node_sdk.hooks import list_hook_events

        return list_hook_events()

    def hook_presets() -> list[dict[str, object]]:
        from nexora_node_sdk.hooks import list_hook_presets

        return list_hook_presets()

    def automation_templates() -> list[dict[str, object]]:
        from nexora_saas.automation import list_automation_templates

        return list_automation_templates()

    def automation_checklists() -> list[dict[str, object]]:
        from nexora_saas.automation import list_checklists

        return list_checklists()

    def settings_overview(
        request: Request,
        x_nexora_tenant_id: str | None = Header(None),
    ) -> dict[str, object]:
        trusted_role = (_resolve_trusted_actor_role_from_request(request) or "observer").strip().lower()
        is_operator = _is_operator_role(trusted_role)
        effective_tenant_id = (x_nexora_tenant_id or "").strip() or None
        if is_operator and not effective_tenant_id:
            effective_tenant_id = _operator_tenant_id()

        state = service.state.load()
        tenant_record = None
        if effective_tenant_id:
            tenant_record = next(
                (
                    tenant
                    for tenant in state.get("tenants", [])
                    if isinstance(tenant, dict) and tenant.get("tenant_id") == effective_tenant_id
                ),
                None,
            )

        return {
            "profile": {
                "actor_role": trusted_role,
                "runtime_mode": _resolve_runtime_mode(),
                "is_operator": is_operator,
            },
            "operator": {
                "tenant_id": _operator_tenant_id() if is_operator else None,
                "organization_id": _operator_org_id() if is_operator else None,
            },
            "tenant": tenant_record,
            "tenant_id": effective_tenant_id,
            "state": {
                "tenants_count": len([t for t in state.get("tenants", []) if isinstance(t, dict)]),
                "organizations_count": len([o for o in state.get("organizations", []) if isinstance(o, dict)]),
                "subscriptions_count": len([s for s in state.get("subscriptions", []) if isinstance(s, dict)]),
                "nodes_count": len([n for n in state.get("nodes", []) if isinstance(n, dict)]),
            },
            "security": {
                "operator_only_enforce": os.environ.get("NEXORA_OPERATOR_ONLY_ENFORCE", "1").strip().lower()
                not in {"0", "false", "no", "off"},
                "deployment_scope": os.environ.get("NEXORA_DEPLOYMENT_SCOPE", ""),
                "token_scope_file_configured": bool(os.environ.get("NEXORA_API_TOKEN_SCOPE_FILE", "").strip()),
                "token_role_file_configured": bool(os.environ.get("NEXORA_API_TOKEN_ROLE_FILE", "").strip()),
            },
            "version": NEXORA_VERSION,
        }

    def tenant_quota_usage(
        x_nexora_tenant_id: str | None = Header(None),
    ) -> dict[str, object]:
        return service.tenant_usage_vs_quota(tenant_id=x_nexora_tenant_id)

    def persistence_status() -> dict[str, object]:
        return service.persistence_status()

    def interface_parity() -> dict[str, object]:
        from nexora_saas.interface_parity import fleet_lifecycle_parity_payload

        return fleet_lifecycle_parity_payload()

    def metrics() -> Response:
        """Prometheus-compatible metrics endpoint (text/plain format)."""
        import time as _time

        from starlette.responses import Response as _Response

        # Collect state snapshot
        try:
            state = service.state.load()
        except Exception:
            state = {}

        nodes = state.get("nodes", [])
        status_counts: dict[str, int] = {}
        for n in nodes:
            s = n.get("status", "unknown") if isinstance(n, dict) else "unknown"
            status_counts[s] = status_counts.get(s, 0) + 1

        healthy = status_counts.get("healthy", 0)
        degraded = status_counts.get("degraded", 0)
        draining = status_counts.get("draining", 0)
        retired = status_counts.get("retired", 0)
        revoked = status_counts.get("revoked", 0)
        total = len(nodes)

        tenants = set()
        for n in nodes:
            if isinstance(n, dict) and n.get("tenant_id"):
                tenants.add(n["tenant_id"])

        inv_snapshots = len(state.get("inventory_snapshots", []))
        sec_audit = state.get("security_audit", {})
        sec_events = (
            len(sec_audit.get("events", []))
            if isinstance(sec_audit, dict)
            else (len(sec_audit) if isinstance(sec_audit, list) else 0)
        )

        ts_ms = int(_time.time() * 1000)
        lines = [
            "# HELP nexora_nodes_total Total enrolled nodes",
            "# TYPE nexora_nodes_total gauge",
            f"nexora_nodes_total {total} {ts_ms}",
            "# HELP nexora_nodes_by_status Node count per status",
            "# TYPE nexora_nodes_by_status gauge",
            f'nexora_nodes_by_status{{status="healthy"}} {healthy} {ts_ms}',
            f'nexora_nodes_by_status{{status="degraded"}} {degraded} {ts_ms}',
            f'nexora_nodes_by_status{{status="draining"}} {draining} {ts_ms}',
            f'nexora_nodes_by_status{{status="retired"}} {retired} {ts_ms}',
            f'nexora_nodes_by_status{{status="revoked"}} {revoked} {ts_ms}',
            "# HELP nexora_tenants_active_count Active tenant count",
            "# TYPE nexora_tenants_active_count gauge",
            f"nexora_tenants_active_count {len(tenants)} {ts_ms}",
            "# HELP nexora_inventory_snapshots_total Stored inventory snapshots",
            "# TYPE nexora_inventory_snapshots_total gauge",
            f"nexora_inventory_snapshots_total {inv_snapshots} {ts_ms}",
            "# HELP nexora_security_events_total Security audit event count",
            "# TYPE nexora_security_events_total gauge",
            f"nexora_security_events_total {sec_events} {ts_ms}",
        ]
        return _Response(
            content="\n".join(lines) + "\n",
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    app.add_api_route("/api/adoption/report", adoption_report, methods=["GET"])
    app.add_api_route("/api/adoption/import", adoption_import, methods=["POST"])
    app.add_api_route("/api/interface-parity/fleet-lifecycle", interface_parity, methods=["GET"])
    app.add_api_route("/api/persistence", persistence_status, methods=["GET"])
    app.add_api_route("/api/metrics", metrics, methods=["GET"])

    app.add_api_route("/api/docker/status", docker_status, methods=["GET"])
    app.add_api_route("/api/docker/containers", docker_containers, methods=["GET"])
    app.add_api_route("/api/docker/templates", docker_templates, methods=["GET"])
    app.add_api_route("/api/failover/strategies", failover_strategies, methods=["GET"])
    app.add_api_route("/api/storage/usage", storage_usage, methods=["GET"])
    app.add_api_route("/api/storage/ynh-map", storage_ynh_map, methods=["GET"])
    app.add_api_route("/api/notifications/templates", notification_templates, methods=["GET"])
    app.add_api_route("/api/sla/tiers", sla_tiers, methods=["GET"])
    app.add_api_route("/api/tenants/usage-quota", tenant_quota_usage, methods=["GET"])
    app.add_api_route("/api/hooks/events", hook_events, methods=["GET"])
    app.add_api_route("/api/hooks/presets", hook_presets, methods=["GET"])
    app.add_api_route("/api/automation/templates", automation_templates, methods=["GET"])
    app.add_api_route("/api/automation/checklists", automation_checklists, methods=["GET"])
    app.add_api_route("/api/settings", settings_overview, methods=["GET"])


def register_subscription_routes(app: FastAPI) -> None:
    """Subscription management API — organizations, plans, subscriptions."""

    def list_plans_route() -> list[dict[str, object]]:
        return service.get_plans()

    def create_org(request: CreateOrgRequest = Body(...)) -> dict[str, object]:
        return service.create_org(
            name=request.name,
            contact_email=request.contact_email,
            billing_address=request.billing_address,
        )

    def list_orgs() -> list[dict[str, object]]:
        return service.list_orgs()

    def get_org(org_id: str) -> dict[str, object]:
        org = service.get_org(org_id)
        if not org:
            raise HTTPException(status_code=404, detail=f"Organization '{org_id}' not found")
        return org

    def create_sub(request: CreateSubscriptionRequest = Body(...)) -> dict[str, object]:
        return service.subscribe(
            org_id=request.org_id,
            plan_tier=request.plan_tier,
            tenant_label=request.tenant_label,
        )

    def list_subs(org_id: str | None = Query(None)) -> list[dict[str, object]]:
        return service.list_subs(org_id=org_id)

    def get_sub(subscription_id: str) -> dict[str, object]:
        sub = service.get_sub(subscription_id)
        if not sub:
            raise HTTPException(status_code=404, detail="Subscription not found")
        return sub

    def suspend_sub(subscription_id: str, request: SuspendSubscriptionRequest = Body(...)) -> dict[str, object]:
        return service.suspend_sub(subscription_id, reason=request.reason)

    def cancel_sub(subscription_id: str) -> dict[str, object]:
        return service.cancel_sub(subscription_id)

    def upgrade_sub(subscription_id: str, request: UpgradeSubscriptionRequest = Body(...)) -> dict[str, object]:
        return service.upgrade_sub(subscription_id, request.new_tier)

    # Public-facing plan catalog
    app.add_api_route("/api/plans", list_plans_route, methods=["GET"])
    app.add_api_route("/api/v1/plans", list_plans_route, methods=["GET"])

    # Organization CRUD
    app.add_api_route("/api/organizations", create_org, methods=["POST"])
    app.add_api_route("/api/organizations", list_orgs, methods=["GET"], name="list-orgs")
    app.add_api_route("/api/organizations/{org_id}", get_org, methods=["GET"])

    # Subscription lifecycle
    app.add_api_route("/api/subscriptions", create_sub, methods=["POST"])
    app.add_api_route("/api/subscriptions", list_subs, methods=["GET"], name="list-subs")
    app.add_api_route("/api/subscriptions/{subscription_id}", get_sub, methods=["GET"])
    app.add_api_route("/api/subscriptions/{subscription_id}/suspend", suspend_sub, methods=["POST"])
    app.add_api_route("/api/subscriptions/{subscription_id}/cancel", cancel_sub, methods=["POST"])
    app.add_api_route("/api/subscriptions/{subscription_id}/upgrade", upgrade_sub, methods=["POST"])


def register_tenant_management_routes(app: FastAPI) -> None:
    """Tenant management API — CRUD, onboarding, purging."""

    def list_tenants_route(
        organization_id: str | None = Query(None),
    ) -> list[dict[str, object]]:
        return service.list_tenants(organization_id=organization_id)

    def onboard_tenant_route(request: OnboardTenantRequest = Body(...)) -> dict[str, object]:
        return service.onboard_tenant(
            request.tenant_id,
            request.organization_id,
            tier=request.tier,
        )

    def purge_tenant_route(tenant_id: str) -> dict[str, object]:
        return service.purge_tenant_data(tenant_id)

    def tenant_usage_route(
        x_nexora_tenant_id: str | None = Header(None),
    ) -> dict[str, object]:
        return service.tenant_usage_vs_quota(tenant_id=x_nexora_tenant_id)

    app.add_api_route("/api/tenants", list_tenants_route, methods=["GET"])
    app.add_api_route("/api/v1/tenants", list_tenants_route, methods=["GET"], name="list-tenants-v1")
    app.add_api_route("/api/tenants/onboard", onboard_tenant_route, methods=["POST"])
    app.add_api_route("/api/tenants/{tenant_id}/purge", purge_tenant_route, methods=["POST"])
    app.add_api_route("/api/tenants/usage-quota", tenant_usage_route, methods=["GET"])


def register_provisioning_routes(app: FastAPI) -> None:
    """Feature provisioning API — SaaS pushes features down to enrolled nodes."""

    def provision_node(request: ProvisionNodeRequest = Body(...)) -> dict[str, object]:
        return service.provision_node(
            node_id=request.node_id,
            node_url=request.node_url,
            hmac_secret=request.hmac_secret,
            api_token=request.api_token,
            tenant_id=request.tenant_id,
        )

    def deprovision_node(request: DeprovisionNodeRequest = Body(...)) -> dict[str, object]:
        return service.deprovision_node_features(
            node_id=request.node_id,
            node_url=request.node_url,
            hmac_secret=request.hmac_secret,
        )

    def heartbeat_node(request: HeartbeatNodeRequest = Body(...)) -> dict[str, object]:
        return service.heartbeat_node(
            node_id=request.node_id,
            node_url=request.node_url,
            hmac_secret=request.hmac_secret,
            api_token=request.api_token,
            lease_seconds=request.lease_seconds,
        )

    def node_provisioning_status(node_id: str) -> dict[str, object]:
        return service.node_provisioning_status(node_id)

    def node_features(node_id: str) -> dict[str, object]:
        return service.resolve_node_features(node_id)

    app.add_api_route("/api/provisioning/provision", provision_node, methods=["POST"])
    app.add_api_route("/api/provisioning/deprovision", deprovision_node, methods=["POST"])
    app.add_api_route("/api/provisioning/heartbeat", heartbeat_node, methods=["POST"])
    app.add_api_route("/api/provisioning/nodes/{node_id}/status", node_provisioning_status, methods=["GET"])
    app.add_api_route("/api/provisioning/nodes/{node_id}/features", node_features, methods=["GET"])


def register_console_routes(app: FastAPI) -> None:
    if CONSOLE_DIR.exists():
        app.mount("/console", StaticFiles(directory=CONSOLE_DIR, html=True), name="console")
    if OWNER_CONSOLE_DIR.exists():
        app.mount("/owner-console", StaticFiles(directory=OWNER_CONSOLE_DIR, html=True), name="owner-console")
    if PUBLIC_SITE_DIR.exists():
        app.mount("/public_site", StaticFiles(directory=PUBLIC_SITE_DIR, html=True), name="public_site")

    def root(request: Request):
        """Route root based on subdomain surface."""
        surface = resolve_surface(request)
        if surface == "saas":
            # Owner console
            if OWNER_CONSOLE_DIR.exists() and (OWNER_CONSOLE_DIR / "index.html").exists():
                return RedirectResponse(url="/owner-console/")
            return {"status": "ok", "surface": "saas", "hint": "Owner console not built yet"}
        if surface == "console":
            # Subscriber console
            if (CONSOLE_DIR / "index.html").exists():
                return RedirectResponse(url="/console/")
            return {"status": "ok", "surface": "console", "hint": "Subscriber console not built yet"}
        # Public site (www.* or bare domain)
        if PUBLIC_SITE_INDEX.exists():
            return HTMLResponse(content=_load_public_landing_html())
        return {"status": "ok", "surface": "public", "hint": "Public site not built yet"}

    def subscribe():
        """Subscription landing page."""
        return HTMLResponse(content=_load_subscription_landing_html())

    def admin_redirect(request: Request):
        surface = resolve_surface(request)
        if surface == "saas":
            return RedirectResponse(url="/owner-console/")
        return RedirectResponse(url="/console/")

    def console_redirect():
        return RedirectResponse(url="/console/")

    app.add_api_route("/", root, methods=["GET"])
    app.add_api_route("/subscribe", subscribe, methods=["GET"])
    app.add_api_route("/admin", admin_redirect, methods=["GET"])
    app.add_api_route("/console", console_redirect, methods=["GET"])


class OwnerLoginRequest(BaseModel):
    passphrase: str = Field(..., min_length=1)


class SetPassphraseRequest(BaseModel):
    passphrase: str = Field(..., min_length=8)


def register_owner_auth_routes(app: FastAPI) -> None:
    """Owner authentication endpoints (passphrase-based, separate from token auth)."""

    def owner_login(body: OwnerLoginRequest) -> dict[str, object]:
        if not has_passphrase_configured():
            raise HTTPException(
                status_code=503,
                detail="Owner passphrase not configured. Run setup first.",
            )
        if not verify_passphrase(body.passphrase):
            raise HTTPException(status_code=401, detail="Invalid passphrase.")
        session = create_owner_session()
        return {
            "session_token": session["session_token"],
            "tenant_id": session["tenant_id"],
            "role": session["role"],
            "expires_at": session["expires_at"],
        }

    def owner_logout(request: Request) -> dict[str, bool]:
        session_token = request.headers.get("X-Nexora-Session", "").strip()
        revoked = revoke_owner_session(session_token) if session_token else False
        return {"revoked": revoked}

    def owner_session_status(request: Request) -> dict[str, object]:
        session_token = request.headers.get("X-Nexora-Session", "").strip()
        session = validate_owner_session(session_token) if session_token else None
        if session is None:
            raise HTTPException(status_code=401, detail="No valid owner session.")
        return {
            "valid": True,
            "tenant_id": session["tenant_id"],
            "role": session["role"],
            "expires_at": session["expires_at"],
        }

    def owner_set_passphrase(request: Request, body: SetPassphraseRequest) -> dict[str, object]:
        """Set or update the owner passphrase. Only callable from saas surface or first-time setup."""
        # Allow if no passphrase configured yet (first-time setup)
        if has_passphrase_configured():
            # Require existing owner session
            session_token = request.headers.get("X-Nexora-Session", "").strip()
            session = validate_owner_session(session_token) if session_token else None
            if session is None:
                raise HTTPException(
                    status_code=403,
                    detail="Must be authenticated as owner to change passphrase.",
                )
        result = set_owner_passphrase(body.passphrase)
        return {"updated": result.get("stored", False), "path": result.get("path", "")}

    def owner_passphrase_status() -> dict[str, bool]:
        return {"configured": has_passphrase_configured()}

    app.add_api_route("/api/auth/owner-login", owner_login, methods=["POST"])
    app.add_api_route("/api/auth/owner-logout", owner_logout, methods=["POST"])
    app.add_api_route("/api/auth/owner-session", owner_session_status, methods=["GET"])
    app.add_api_route("/api/auth/owner-passphrase", owner_set_passphrase, methods=["POST"])
    app.add_api_route("/api/auth/owner-passphrase-status", owner_passphrase_status, methods=["GET"])


# ── Request models for new routes ─────────────────────────────────────────


class DockerDeployRequest(BaseModel):
    image: str = Field(..., min_length=1, description="Docker image name[:tag]")
    name: str = Field(..., min_length=1, description="Container name")
    ports: list[str] = Field(default_factory=list, description="Port bindings e.g. ['8080:80']")
    env: dict[str, str] = Field(default_factory=dict)
    volumes: list[str] = Field(default_factory=list)
    restart: str = "unless-stopped"
    network: str = ""
    labels: dict[str, str] = Field(default_factory=dict)


class DockerTemplateDeployRequest(BaseModel):
    template_name: str = Field(..., min_length=1)
    overrides: dict[str, object] = Field(default_factory=dict)


class DockerComposeApplyRequest(BaseModel):
    content: str = Field(..., min_length=1, description="Docker Compose YAML content")
    path: str = ""
    project_name: str = ""


class DockerComposeDownRequest(BaseModel):
    path: str = ""
    project_name: str = ""
    remove_volumes: bool = False


class DockerConfigSaveRequest(BaseModel):
    config: dict[str, object] = Field(default_factory=dict)


class BlueprintDeployRequest(BaseModel):
    slug: str = Field(..., min_length=1)
    target_node_id: str = ""
    domain: str = ""
    parameters: dict[str, object] = Field(default_factory=dict)
    dry_run: bool = False


class YnhInstallAppRequest(BaseModel):
    app_id: str = Field(..., min_length=1)
    domain: str = Field(..., min_length=1)
    path: str = "/"
    label: str = ""
    args: dict[str, str] = Field(default_factory=dict)


class YnhRemoveAppRequest(BaseModel):
    app_id: str = Field(..., min_length=1)
    purge: bool = False


class FailoverConfigureRequest(BaseModel):
    app_id: str = Field(..., min_length=1)
    domain: str = Field(..., min_length=1)
    primary_host: str = Field(..., min_length=1)
    secondary_host: str = Field(..., min_length=1)
    primary_node_id: str = "primary"
    secondary_node_id: str = "secondary"
    health_strategy: str = "combined"


class FailoverExecuteRequest(BaseModel):
    app_id: str = Field(..., min_length=1)
    target_node: str = "secondary"
    reason: str = "manual"


class MigrationCreateRequest(BaseModel):
    app_id: str = Field(..., min_length=1)
    source_node_id: str = Field(..., min_length=1)
    target_node_id: str = Field(..., min_length=1)
    target_domain: str = ""
    target_ssh_host: str = ""
    options: dict[str, object] = Field(default_factory=dict)


# ── Extended Docker routes ─────────────────────────────────────────────────


def register_docker_extended_routes(app: FastAPI) -> None:
    """Full Docker lifecycle: Hub search, deploy, start/stop/restart, logs, compose, images, config."""

    def docker_hub_search(q: str = Query("", alias="q"), limit: int = Query(10)) -> list[dict[str, object]]:
        from nexora_node_sdk.docker import docker_hub_search as _hub_search
        return _hub_search(q, limit=limit)

    def docker_hub_tags(image: str, limit: int = Query(20)) -> list[dict[str, object]]:
        from nexora_node_sdk.docker import docker_hub_tags as _hub_tags
        return _hub_tags(image, limit=limit)

    def docker_deploy(body: DockerDeployRequest) -> dict[str, object]:
        from nexora_node_sdk.docker import docker_run
        result = docker_run(
            image=body.image,
            name=body.name,
            ports=body.ports,
            env=body.env,
            volumes=body.volumes,
            restart=body.restart,
            network=body.network,
            labels=body.labels,
        )
        return result

    def docker_template_deploy(body: DockerTemplateDeployRequest) -> dict[str, object]:
        from nexora_node_sdk.docker import deploy_from_template
        return deploy_from_template(body.template_name, overrides=body.overrides)

    def docker_container_start(name: str) -> dict[str, object]:
        from nexora_node_sdk.docker import docker_start
        return docker_start(name)

    def docker_container_stop(name: str) -> dict[str, object]:
        from nexora_node_sdk.docker import docker_stop
        return docker_stop(name)

    def docker_container_restart(name: str) -> dict[str, object]:
        from nexora_node_sdk.docker import docker_restart
        return docker_restart(name)

    def docker_container_remove(name: str, force: bool = Query(False)) -> dict[str, object]:
        from nexora_node_sdk.docker import docker_remove
        return docker_remove(name, force=force)

    def docker_container_logs(name: str, lines: int = Query(100)) -> dict[str, object]:
        from nexora_node_sdk.docker import container_logs
        return {"container": name, "logs": container_logs(name, lines=lines)}

    def docker_container_inspect(name: str) -> dict[str, object]:
        from nexora_node_sdk.docker import docker_inspect
        return docker_inspect(name)

    def docker_container_stats_single(name: str) -> dict[str, object]:
        from nexora_node_sdk.docker import container_stats
        stats = container_stats()
        # Find the specific container in stats
        if isinstance(stats, list):
            for s in stats:
                if isinstance(s, dict) and s.get("name", "").lstrip("/") == name.lstrip("/"):
                    return s
        return {"container": name, "error": "Stats not available"}

    def docker_compose_status() -> list[dict[str, object]]:
        from nexora_node_sdk.docker import list_compose_stacks
        return list_compose_stacks()

    def docker_compose_apply(body: DockerComposeApplyRequest) -> dict[str, object]:
        from nexora_node_sdk.docker import apply_compose
        return apply_compose(body.content, path=body.path or None, project_name=body.project_name or None)

    def docker_compose_down(body: DockerComposeDownRequest) -> dict[str, object]:
        from nexora_node_sdk.docker import destroy_compose
        return destroy_compose(path=body.path or None, remove_volumes=body.remove_volumes)

    def docker_images_list() -> list[dict[str, object]]:
        from nexora_node_sdk.docker import docker_images
        return docker_images()

    def docker_volumes_list() -> list[dict[str, object]]:
        from nexora_node_sdk.docker import docker_volume_list
        return docker_volume_list()

    def docker_networks_list() -> list[dict[str, object]]:
        from nexora_node_sdk.docker import docker_network_list
        return docker_network_list()

    def docker_config_get() -> dict[str, object]:
        from nexora_node_sdk.docker import get_docker_config
        return get_docker_config()

    def docker_config_save(body: DockerConfigSaveRequest) -> dict[str, object]:
        from nexora_node_sdk.docker import save_docker_config
        return save_docker_config(body.config)

    def docker_system_prune_dry() -> dict[str, object]:
        from nexora_node_sdk.docker import docker_system_prune
        return docker_system_prune(dry_run=True)

    def docker_system_prune_exec() -> dict[str, object]:
        from nexora_node_sdk.docker import docker_system_prune
        return docker_system_prune(dry_run=False)

    app.add_api_route("/api/docker/hub/search", docker_hub_search, methods=["GET"])
    app.add_api_route("/api/docker/hub/tags/{image:path}", docker_hub_tags, methods=["GET"])
    app.add_api_route("/api/docker/deploy", docker_deploy, methods=["POST"])
    app.add_api_route("/api/docker/templates/deploy", docker_template_deploy, methods=["POST"])
    app.add_api_route("/api/docker/containers/{name}/start", docker_container_start, methods=["POST"])
    app.add_api_route("/api/docker/containers/{name}/stop", docker_container_stop, methods=["POST"])
    app.add_api_route("/api/docker/containers/{name}/restart", docker_container_restart, methods=["POST"])
    app.add_api_route("/api/docker/containers/{name}/remove", docker_container_remove, methods=["DELETE"])
    app.add_api_route("/api/docker/containers/{name}/logs", docker_container_logs, methods=["GET"])
    app.add_api_route("/api/docker/containers/{name}/inspect", docker_container_inspect, methods=["GET"])
    app.add_api_route("/api/docker/containers/{name}/stats", docker_container_stats_single, methods=["GET"])
    app.add_api_route("/api/docker/compose/status", docker_compose_status, methods=["GET"])
    app.add_api_route("/api/docker/compose/apply", docker_compose_apply, methods=["POST"])
    app.add_api_route("/api/docker/compose/down", docker_compose_down, methods=["POST"])
    app.add_api_route("/api/docker/images", docker_images_list, methods=["GET"])
    app.add_api_route("/api/docker/volumes", docker_volumes_list, methods=["GET"])
    app.add_api_route("/api/docker/networks", docker_networks_list, methods=["GET"])
    app.add_api_route("/api/docker/config", docker_config_get, methods=["GET"])
    app.add_api_route("/api/docker/config", docker_config_save, methods=["PUT"])
    app.add_api_route("/api/docker/system/prune/dry", docker_system_prune_dry, methods=["GET"])
    app.add_api_route("/api/docker/system/prune", docker_system_prune_exec, methods=["POST"])


# ── Blueprint deployment routes ────────────────────────────────────────────


def register_blueprint_deploy_routes(app: FastAPI) -> None:
    """Blueprint deployment: deploy blueprint to node, get parameters form."""

    def blueprint_parameters(slug: str) -> dict[str, object]:
        """Return the parameters schema for a blueprint deployment form."""
        bp = next((b for b in service.list_blueprints() if b.slug == slug), None)
        if not bp:
            raise HTTPException(status_code=404, detail=f"Blueprint '{slug}' not found")
        raw = bp.model_dump()
        # Extract parameter definitions from blueprint data
        params: list[dict[str, object]] = raw.get("parameters", [])
        if not params:
            # Build default parameters from blueprint fields
            params = [
                {"name": "domain", "label": "Domain", "type": "text", "required": True,
                 "placeholder": "example.com", "description": "Target domain for the deployment"},
                {"name": "admin_email", "label": "Admin Email", "type": "email", "required": True,
                 "placeholder": "admin@example.com"},
                {"name": "target_node", "label": "Target Node", "type": "node_selector", "required": False,
                 "description": "Node to deploy to (leave empty for local)"},
            ]
            # Add app-specific params
            for app_item in raw.get("apps", []):
                if isinstance(app_item, dict):
                    params.append({
                        "name": f"{app_item.get('id', 'app')}_enabled",
                        "label": f"Install {app_item.get('id', 'app')}",
                        "type": "bool",
                        "default": True,
                    })
        return {
            "slug": slug,
            "name": raw.get("name", slug),
            "description": raw.get("description", ""),
            "parameters": params,
        }

    def blueprint_deploy(slug: str, body: BlueprintDeployRequest = Body(...)) -> dict[str, object]:
        """Deploy a blueprint — install configured apps via YunoHost."""
        bp = next((b for b in service.list_blueprints() if b.slug == slug), None)
        if not bp:
            raise HTTPException(status_code=404, detail=f"Blueprint '{slug}' not found")
        raw = bp.model_dump()
        domain = body.parameters.get("domain", body.domain) or ""
        dry_run = body.dry_run

        results: list[dict[str, object]] = []
        apps_to_install = raw.get("apps", [])

        if dry_run:
            return {
                "dry_run": True,
                "slug": slug,
                "domain": domain,
                "apps_planned": [
                    a.get("id") if isinstance(a, dict) else a
                    for a in apps_to_install
                ],
                "parameters": body.parameters,
                "message": "Dry run — no changes made",
            }

        from nexora_node_sdk.yh_adapter import ynh_install_app

        for app_item in apps_to_install:
            if isinstance(app_item, str):
                app_id = app_item
                app_path = "/"
            elif isinstance(app_item, dict):
                app_id = app_item.get("id", "")
                app_path = app_item.get("path", "/")
                # Check if the user explicitly disabled this app
                enabled = body.parameters.get(f"{app_id}_enabled", True)
                if not enabled:
                    results.append({"app_id": app_id, "status": "skipped", "reason": "disabled by parameter"})
                    continue
            else:
                continue

            if not app_id or not domain:
                results.append({"app_id": app_id, "status": "skipped", "reason": "missing domain"})
                continue

            install_result = ynh_install_app(
                app_id=app_id,
                domain=domain,
                path=app_path,
                label=str(body.parameters.get(f"{app_id}_label", "")),
                args={k: str(v) for k, v in body.parameters.items() if k.startswith(f"{app_id}_") and k != f"{app_id}_enabled"},
            )
            results.append({"app_id": app_id, **install_result})

        success_count = sum(1 for r in results if r.get("success"))
        return {
            "slug": slug,
            "domain": domain,
            "deployed": success_count,
            "total": len(results),
            "results": results,
        }

    app.add_api_route("/api/blueprints/{slug}/parameters", blueprint_parameters, methods=["GET"])
    app.add_api_route("/api/blueprints/{slug}/deploy", blueprint_deploy, methods=["POST"])


# ── YunoHost app catalog routes ────────────────────────────────────────────


def register_ynh_catalog_routes(app: FastAPI) -> None:
    """YunoHost application catalog: browse, install, upgrade, remove."""

    def ynh_catalog(
        category: str | None = Query(None),
        q: str | None = Query(None),
    ) -> list[dict[str, object]]:
        from nexora_node_sdk.yh_adapter import ynh_app_catalog_filtered
        return ynh_app_catalog_filtered(category=category, query=q)

    def ynh_catalog_app(app_id: str) -> dict[str, object]:
        from nexora_node_sdk.yh_adapter import ynh_app_info
        return ynh_app_info(app_id)

    def ynh_installed_apps() -> dict[str, object]:
        from nexora_node_sdk.yh_adapter import ynh_apps
        return ynh_apps()

    def ynh_install(body: YnhInstallAppRequest) -> dict[str, object]:
        from nexora_node_sdk.yh_adapter import ynh_install_app
        return ynh_install_app(
            app_id=body.app_id,
            domain=body.domain,
            path=body.path,
            label=body.label or None,
            args=body.args,
        )

    def ynh_upgrade(app_id: str) -> dict[str, object]:
        from nexora_node_sdk.yh_adapter import ynh_upgrade_app
        return ynh_upgrade_app(app_id)

    def ynh_remove(body: YnhRemoveAppRequest) -> dict[str, object]:
        from nexora_node_sdk.yh_adapter import ynh_remove_app
        return ynh_remove_app(body.app_id, purge=body.purge)

    app.add_api_route("/api/ynh/catalog", ynh_catalog, methods=["GET"])
    app.add_api_route("/api/ynh/catalog/{app_id}", ynh_catalog_app, methods=["GET"])
    app.add_api_route("/api/ynh/apps", ynh_installed_apps, methods=["GET"])
    app.add_api_route("/api/ynh/apps/install", ynh_install, methods=["POST"])
    app.add_api_route("/api/ynh/apps/{app_id}/upgrade", ynh_upgrade, methods=["POST"])
    app.add_api_route("/api/ynh/apps/remove", ynh_remove, methods=["POST"])


# ── YunoHost service management routes ───────────────────────────────────


def register_ynh_service_mgmt_routes(app: FastAPI) -> None:
    """YunoHost service management with systemctl fallback."""

    def services_list() -> dict[str, object]:
        from nexora_node_sdk.yh_adapter import services_with_fallback
        return services_with_fallback()

    def service_action_route(service_name: str, action: str) -> dict[str, object]:
        from nexora_node_sdk.yh_adapter import ynh_service_action
        return ynh_service_action(service_name, action)

    def service_start(service_name: str) -> dict[str, object]:
        from nexora_node_sdk.yh_adapter import ynh_service_action
        return ynh_service_action(service_name, "start")

    def service_stop(service_name: str) -> dict[str, object]:
        from nexora_node_sdk.yh_adapter import ynh_service_action
        return ynh_service_action(service_name, "stop")

    def service_restart(service_name: str) -> dict[str, object]:
        from nexora_node_sdk.yh_adapter import ynh_service_action
        return ynh_service_action(service_name, "restart")

    def service_logs(service_name: str, lines: int = Query(100)) -> dict[str, object]:
        from nexora_node_sdk.yh_adapter import ynh_service_logs
        return {"service": service_name, "logs": ynh_service_logs(service_name, lines=lines)}

    # Override existing inventory services endpoint with fallback version
    app.add_api_route("/api/inventory/services", services_list, methods=["GET"])
    app.add_api_route("/api/services/{service_name}/start", service_start, methods=["POST"])
    app.add_api_route("/api/services/{service_name}/stop", service_stop, methods=["POST"])
    app.add_api_route("/api/services/{service_name}/restart", service_restart, methods=["POST"])
    app.add_api_route("/api/services/{service_name}/logs", service_logs, methods=["GET"])


# ── Failover execution routes ─────────────────────────────────────────────


def register_failover_execution_routes(app: FastAPI) -> None:
    """Failover: configure pairs, execute, status, maintenance."""

    def failover_status() -> dict[str, object]:
        from nexora_saas.failover import get_failover_status
        return get_failover_status()

    def failover_pairs_list() -> list[dict[str, object]]:
        from nexora_saas.failover import get_failover_pairs
        return get_failover_pairs()

    def failover_configure(body: FailoverConfigureRequest) -> dict[str, object]:
        from nexora_saas.failover import configure_failover_pair, generate_health_check_config
        pair = {
            "app_id": body.app_id,
            "domain": body.domain,
            "primary": {"node_id": body.primary_node_id, "host": body.primary_host, "port": 443},
            "secondary": {"node_id": body.secondary_node_id, "host": body.secondary_host, "port": 443},
            "health_check": generate_health_check_config(body.app_id, body.health_strategy),
            "mode": "active_passive",
        }
        return configure_failover_pair(pair)

    def failover_execute(body: FailoverExecuteRequest) -> dict[str, object]:
        from nexora_saas.failover import execute_failover
        return execute_failover(body.app_id, target_node=body.target_node, reason=body.reason)

    def failover_failback(app_id: str) -> dict[str, object]:
        from nexora_saas.failover import execute_failback
        return execute_failback(app_id)

    def failover_maintenance_enable(domain: str) -> dict[str, object]:
        from nexora_saas.failover import apply_maintenance_mode
        return apply_maintenance_mode(domain)

    def failover_maintenance_disable(domain: str) -> dict[str, object]:
        from nexora_saas.failover import remove_maintenance_mode
        return remove_maintenance_mode(domain)

    def failover_nginx_apply(body: FailoverConfigureRequest) -> dict[str, object]:
        from nexora_saas.failover import apply_failover_nginx
        return apply_failover_nginx(
            body.app_id,
            primary_host=body.primary_host,
            secondary_host=body.secondary_host,
            domain=body.domain,
        )

    app.add_api_route("/api/failover/status", failover_status, methods=["GET"])
    app.add_api_route("/api/failover/pairs", failover_pairs_list, methods=["GET"])
    app.add_api_route("/api/failover/configure", failover_configure, methods=["POST"])
    app.add_api_route("/api/failover/execute", failover_execute, methods=["POST"])
    app.add_api_route("/api/failover/apps/{app_id}/failback", failover_failback, methods=["POST"])
    app.add_api_route("/api/failover/maintenance/{domain}/enable", failover_maintenance_enable, methods=["POST"])
    app.add_api_route("/api/failover/maintenance/{domain}/disable", failover_maintenance_disable, methods=["POST"])
    app.add_api_route("/api/failover/nginx/apply", failover_nginx_apply, methods=["POST"])


# ── App migration routes ──────────────────────────────────────────────────


def register_app_migration_routes(app: FastAPI) -> None:
    """App migration: create job, execute, status."""

    def migratable_apps() -> list[dict[str, object]]:
        from nexora_saas.app_migration import list_migratable_apps
        return list_migratable_apps()

    def migration_jobs_list() -> list[dict[str, object]]:
        from nexora_saas.app_migration import list_migration_jobs
        return list_migration_jobs()

    def migration_create(body: MigrationCreateRequest) -> dict[str, object]:
        from nexora_saas.app_migration import create_migration_job
        return create_migration_job(
            app_id=body.app_id,
            source_node_id=body.source_node_id,
            target_node_id=body.target_node_id,
            target_domain=body.target_domain or None,
            options=body.options,
        )

    def migration_execute(job_id: str, body: dict[str, object] = Body(default_factory=dict)) -> dict[str, object]:
        from nexora_saas.app_migration import execute_migration
        target_ssh = body.get("target_ssh_host", "") if isinstance(body, dict) else ""
        return execute_migration(job_id, target_ssh_host=target_ssh or None)

    def migration_status(job_id: str) -> dict[str, object]:
        from nexora_saas.app_migration import get_migration_status
        result = get_migration_status(job_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Migration job '{job_id}' not found")
        return result

    app.add_api_route("/api/fleet/apps/migratable", migratable_apps, methods=["GET"])
    app.add_api_route("/api/fleet/apps/migration", migration_jobs_list, methods=["GET"])
    app.add_api_route("/api/fleet/apps/migrate", migration_create, methods=["POST"])
    app.add_api_route("/api/fleet/apps/migration/{job_id}/execute", migration_execute, methods=["POST"])
    app.add_api_route("/api/fleet/apps/migration/{job_id}/status", migration_status, methods=["GET"])


app = build_application()


def main() -> None:
    host = os.environ.get("NEXORA_CONTROL_PLANE_HOST", "127.0.0.1")
    port = int(os.environ.get("NEXORA_CONTROL_PLANE_PORT", "38120"))
    uvicorn.run(app, host=host, port=port, reload=False)
