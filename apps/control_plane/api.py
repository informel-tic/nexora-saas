"""Control-plane FastAPI application wiring for Nexora."""

from __future__ import annotations

import os
import secrets

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.responses import Response

from nexora_node_sdk.auth import (
    _load_token_actor_roles,
    CSRFProtectionMiddleware,
    TokenAuthMiddleware,
    build_tenant_scope_claim,
    get_api_token,
    resolve_actor_role_for_token,
)
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
PUBLIC_SITE_DIR = REPO_ROOT / "apps" / "public_site"
PUBLIC_SITE_INDEX = PUBLIC_SITE_DIR / "index.html"
service = build_service(__file__, os.environ.get("NEXORA_STATE_PATH"))
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
    if normalized_trusted_role in {
        "operator",
        "admin",
        "architect",
    } and normalized_requested_role in {
        "operator",
        "admin",
        "architect",
    }:
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
                })
                node_record = transition_node_status(node_record, local.status or "healthy")
                state.setdefault("nodes", []).append(node_record)
                if local.node_id not in state.get("fleet", {}).get("managed_nodes", []):
                    state.setdefault("fleet", {}).setdefault("managed_nodes", []).append(local.node_id)
                service.state.save(state)
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
        trusted_role = (_resolve_trusted_actor_role_from_request(request) or "observer").strip().lower()
        tenant_record: dict[str, object] | None = None
        if x_nexora_tenant_id:
            state = service.state.load()
            tenant_record = next(
                (
                    tenant
                    for tenant in state.get("tenants", [])
                    if isinstance(tenant, dict) and tenant.get("tenant_id") == x_nexora_tenant_id
                ),
                None,
            )

        full_sections = [
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
        ]
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

        return {
            "actor_role": trusted_role,
            "tenant_id": x_nexora_tenant_id,
            "tenant": tenant_record,
            "allowed_sections": subscriber_sections if trusted_role == "subscriber" else full_sections,
            "subscriber_mode": trusted_role == "subscriber",
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

    def fleet_enroll_attest(request: EnrollmentAttestationRequest) -> dict[str, object]:
        return service.attest_enrollment(**request.model_dump())

    def fleet_enroll_register(request: EnrollmentRegisterRequest) -> dict[str, object]:
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


def register_subscription_routes(app: FastAPI) -> None:
    """Subscription management API — organizations, plans, subscriptions."""

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

    def list_plans_route() -> list[dict[str, object]]:
        return service.get_plans()

    def create_org(request: CreateOrgRequest) -> dict[str, object]:
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

    def create_sub(request: CreateSubscriptionRequest) -> dict[str, object]:
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

    def suspend_sub(subscription_id: str, request: SuspendSubscriptionRequest) -> dict[str, object]:
        return service.suspend_sub(subscription_id, reason=request.reason)

    def cancel_sub(subscription_id: str) -> dict[str, object]:
        return service.cancel_sub(subscription_id)

    def upgrade_sub(subscription_id: str, request: UpgradeSubscriptionRequest) -> dict[str, object]:
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

    class OnboardTenantRequest(BaseModel):
        tenant_id: str = Field(..., min_length=1)
        organization_id: str = Field(..., min_length=1)
        tier: str = "free"

    def list_tenants_route(
        organization_id: str | None = Query(None),
    ) -> list[dict[str, object]]:
        return service.list_tenants(organization_id=organization_id)

    def onboard_tenant_route(request: OnboardTenantRequest) -> dict[str, object]:
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

    def provision_node(request: ProvisionNodeRequest) -> dict[str, object]:
        return service.provision_node(
            node_id=request.node_id,
            node_url=request.node_url,
            hmac_secret=request.hmac_secret,
            api_token=request.api_token,
            tenant_id=request.tenant_id,
        )

    def deprovision_node(request: DeprovisionNodeRequest) -> dict[str, object]:
        return service.deprovision_node_features(
            node_id=request.node_id,
            node_url=request.node_url,
            hmac_secret=request.hmac_secret,
        )

    def heartbeat_node(request: HeartbeatNodeRequest) -> dict[str, object]:
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

    def root():
        if PUBLIC_SITE_INDEX.exists():
            return HTMLResponse(content=_load_public_landing_html())
        if (CONSOLE_DIR / "index.html").exists():
            return RedirectResponse(url="admin")
        return {"status": "ok", "hint": "Console not built yet"}

    def subscribe():
        """Redirect to the subscription onboarding flow."""
        return HTMLResponse(content=_load_subscription_landing_html())

    def admin_redirect():
        return RedirectResponse(url="console/")

    def console_redirect():
        return RedirectResponse(url="console/")

    app.add_api_route("/", root, methods=["GET"])
    app.add_api_route("/subscribe", subscribe, methods=["GET"])
    app.add_api_route("/admin", admin_redirect, methods=["GET"])
    app.add_api_route("/console", console_redirect, methods=["GET"])


app = build_application()


def main() -> None:
    host = os.environ.get("NEXORA_CONTROL_PLANE_HOST", "127.0.0.1")
    port = int(os.environ.get("NEXORA_CONTROL_PLANE_PORT", "38120"))
    uvicorn.run(app, host=host, port=port, reload=False)
