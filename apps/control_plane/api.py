"""Control-plane FastAPI application wiring for Nexora."""

from __future__ import annotations

import os
import secrets

from fastapi import FastAPI, Query, Header, HTTPException
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
import uvicorn

from nexora_core.logging_config import setup_logging
from nexora_core.auth import (
    CSRFProtectionMiddleware,
    TokenAuthMiddleware,
    get_api_token,
    resolve_actor_role_for_token,
)
from nexora_core.api_models import (
    EnrollmentAttestationRequest,
    EnrollmentRegisterRequest,
    EnrollmentTokenRequest,
    LifecycleActionRequest,
)
from pydantic import BaseModel, Field
from nexora_core.runtime_context import build_service, resolve_repo_root
from nexora_core.version import NEXORA_VERSION

REPO_ROOT = resolve_repo_root(__file__)
CONSOLE_DIR = REPO_ROOT / "apps" / "console"
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
SUBSCRIBER_ALLOWED_API_ROUTES = frozenset(
    {
        "/api/health",
        "/api/v1/health",
        "/api/fleet/enroll/attest",
        "/api/fleet/enroll/register",
    }
)


def _deployment_scope() -> str:
    return os.environ.get("NEXORA_DEPLOYMENT_SCOPE", "operator").strip().lower()


def _enforce_deployment_scope(path: str) -> None:
    """Block control-plane surfaces that must not be exposed in subscriber deployments."""

    if _deployment_scope() != "subscriber":
        return
    normalized = path.rstrip("/") or "/"
    if normalized.startswith("/console"):
        raise HTTPException(
            status_code=403,
            detail="Subscriber deployment scope forbids control-plane console exposure",
        )
    if (
        normalized.startswith("/api")
        and normalized not in SUBSCRIBER_ALLOWED_API_ROUTES
    ):
        raise HTTPException(
            status_code=403,
            detail="Subscriber deployment scope forbids this control-plane API route",
        )


def _enforce_operator_only_surface(
    trusted_actor_role: str | None,
    requested_actor_role: str | None,
) -> None:
    enforce = os.environ.get(
        "NEXORA_OPERATOR_ONLY_ENFORCE", "1"
    ).strip().lower() not in {"0", "false", "no", "off"}
    if not enforce:
        return
    normalized_requested_role = (requested_actor_role or "").strip().lower()
    normalized_trusted_role = (trusted_actor_role or "").strip().lower()
    if (
        normalized_requested_role
        and normalized_trusted_role
        and normalized_requested_role != normalized_trusted_role
    ):
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


def _resolve_trusted_actor_role_from_request(request) -> str | None:
    auth_header = request.headers.get("Authorization", "")
    token = ""
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    if not token:
        token = request.headers.get("X-Nexora-Token", "").strip()
    if not token:
        return None
    if not secrets.compare_digest(token, get_api_token()):
        return None
    return resolve_actor_role_for_token(token)


class NodeActionRequest(BaseModel):
    action: str
    payload: dict[str, object] = Field(default_factory=dict)


class NodeActionPayloadRequest(BaseModel):
    payload: dict[str, object] = Field(default_factory=dict)
    dry_run: bool = False


def _enforce_tenant_node_access(
    node_id: str, tenant_id: str | None
) -> dict[str, object]:
    state = service.state.load()
    node_record = next(
        (
            node
            for node in state.get("nodes", [])
            if isinstance(node, dict) and str(node.get("node_id")) == node_id
        ),
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
            return JSONResponse(
                status_code=exc.status_code, content={"detail": exc.detail}
            )
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
                return JSONResponse(
                    status_code=exc.status_code, content={"detail": exc.detail}
                )
        return await call_next(request)

    register_health_routes(app)
    register_inventory_routes(app)
    register_fleet_routes(app)
    register_catalog_routes(app)
    register_governance_routes(app)
    register_modes_routes(app)
    register_operations_routes(app)
    register_console_routes(app)
    return app


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
    from nexora_core.node_actions import execute_node_action

    def fleet(x_nexora_tenant_id: str | None = Header(None)) -> dict[str, object]:
        return service.fleet_summary(tenant_id=x_nexora_tenant_id).model_dump()

    def fleet_topology(
        x_nexora_tenant_id: str | None = Header(None),
    ) -> dict[str, object]:
        from nexora_core.fleet import generate_fleet_topology

        state = service.state.load()
        nodes_raw = state.get("nodes", [])
        if x_nexora_tenant_id:
            nodes_raw = [
                node
                for node in nodes_raw
                if isinstance(node, dict)
                and node.get("tenant_id") == x_nexora_tenant_id
            ]
        nodes = [
            {"node_id": n.get("node_id"), "inventory": {}, "status": n.get("status")}
            for n in nodes_raw
        ]
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
    app.add_api_route(
        "/api/fleet/enroll/request", fleet_enroll_request, methods=["POST"]
    )
    app.add_api_route("/api/fleet/enroll/attest", fleet_enroll_attest, methods=["POST"])
    app.add_api_route(
        "/api/fleet/enroll/register", fleet_enroll_register, methods=["POST"]
    )

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
        result = execute_node_action(
            service, action, dry_run=dry_run, params=normalized_payload
        )
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
        from nexora_core.portal import list_available_palettes

        return list_available_palettes()

    def portal_sectors() -> list[dict[str, object]]:
        from nexora_core.portal import list_sector_themes

        return list_sector_themes()

    def capabilities() -> dict[str, object]:
        from nexora_core.capabilities import capability_catalog_payload

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
        from nexora_core.scoring import (
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
            "overall": int(
                (sec["score"] + pra["score"] + hlth["score"] + comp["score"]) / 4
            ),
        }
        if x_nexora_tenant_id:
            payload["tenant_id"] = x_nexora_tenant_id
        return payload

    def executive_report(
        x_nexora_tenant_id: str | None = Header(None),
    ) -> dict[str, object]:
        from nexora_core.governance import executive_report as _report

        inv = _governance_inventory(x_nexora_tenant_id)
        report = _report(inv, has_pra=True, has_monitoring=True)
        if x_nexora_tenant_id:
            report["tenant_id"] = x_nexora_tenant_id
        return report

    def risk_register(
        x_nexora_tenant_id: str | None = Header(None),
    ) -> dict[str, object]:
        from nexora_core.governance import risk_register as _risks

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
            perms_section = (
                tenant_inv.get("permissions", {})
                if isinstance(tenant_inv, dict)
                else {}
            )
            perms = (
                perms_section.get("permissions", {})
                if isinstance(perms_section, dict)
                else {}
            )
        else:
            perms = service.inventory_slice("permissions").get("permissions", {})
        public_apps = [
            name
            for name, perm in perms.items()
            if isinstance(perm, dict) and "visitors" in perm.get("allowed", [])
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
        from nexora_core.governance import change_log as _cl

        snapshots = service.state.load().get("inventory_snapshots", [])
        if x_nexora_tenant_id:
            # Note: snapshots would need to be tagged with tenant_id during creation.
            # For now, we filter if the snapshot has the field.
            snapshots = [
                s for s in snapshots if s.get("tenant_id") == x_nexora_tenant_id
            ]
        return _cl(snapshots)

    def snapshot_diff(
        x_nexora_tenant_id: str | None = Header(None),
    ) -> dict[str, object]:
        snapshots = service.state.load().get("inventory_snapshots", [])
        if x_nexora_tenant_id:
            snapshots = [
                s for s in snapshots if s.get("tenant_id") == x_nexora_tenant_id
            ]
        if len(snapshots) < 2:
            return {"diff": {}}
        from nexora_core.scoring import diff_snapshots

        return diff_snapshots(
            snapshots[-2].get("inventory", {}), snapshots[-1].get("inventory", {})
        )

    def security_updates(
        x_nexora_tenant_id: str | None = Header(None),
    ) -> dict[str, object]:
        # [STUB] A3: Returns hardcoded data. Real implementation requires calling
        # `yunohost tools update --apps --system` via YunoHost CLI on each node.
        payload: dict[str, object] = {
            "updates_available": False,
            "packages": [],
            "_stub": True,
            "_stub_note": "Real data requires YunoHost CLI integration on each node (NEXT-13).",
        }
        if x_nexora_tenant_id:
            payload["tenant_id"] = x_nexora_tenant_id
        return payload

    def fail2ban_status(
        x_nexora_tenant_id: str | None = Header(None),
    ) -> dict[str, object]:
        # [STUB] A3: Returns hardcoded data. Real implementation requires reading
        # fail2ban-client status via privileged node agent action.
        payload: dict[str, object] = {
            "active": True,
            "banned_ips": [],
            "_stub": True,
            "_stub_note": "Real data requires fail2ban-client integration via node agent (NEXT-13).",
        }
        if x_nexora_tenant_id:
            payload["tenant_id"] = x_nexora_tenant_id
        return payload

    def fail2ban_ban(
        ip: str = Query(...), x_nexora_tenant_id: str | None = Header(None)
    ) -> dict[str, object]:
        state = service.state.load()
        from nexora_core.security_audit import emit_security_event

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

    def fail2ban_unban(
        ip: str = Query(...), x_nexora_tenant_id: str | None = Header(None)
    ) -> dict[str, object]:
        state = service.state.load()
        from nexora_core.security_audit import emit_security_event

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
        # [STUB] A3: Returns hardcoded data. Real implementation requires calling
        # `yunohost firewall list` via node agent privileged action.
        payload: dict[str, object] = {
            "ports": [80, 443, 22],
            "_stub": True,
            "_stub_note": "Real data requires yunohost firewall list via node agent (NEXT-13).",
        }
        if x_nexora_tenant_id:
            payload["tenant_id"] = x_nexora_tenant_id
        return payload

    def permissions_audit(
        x_nexora_tenant_id: str | None = Header(None),
    ) -> dict[str, object]:
        # [STUB] A3: Returns hardcoded data. Real implementation requires calling
        # `yunohost user permission list` via node agent.
        payload: dict[str, object] = {
            "audit": "ok",
            "public_apps": [],
            "_stub": True,
            "_stub_note": "Real data requires yunohost user permission list via node agent (NEXT-13).",
        }
        if x_nexora_tenant_id:
            payload["tenant_id"] = x_nexora_tenant_id
        return payload

    def recent_logins(
        x_nexora_tenant_id: str | None = Header(None),
    ) -> dict[str, object]:
        # [STUB] A3: Returns hardcoded data. Real implementation requires parsing
        # auth.log or sssd audit logs via node agent.
        payload: dict[str, object] = {
            "logins": [],
            "_stub": True,
            "_stub_note": "Real data requires auth.log parsing via node agent (NEXT-13).",
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
    app.add_api_route(
        "/api/security/permissions-audit", permissions_audit, methods=["GET"]
    )
    app.add_api_route("/api/security/recent-logins", recent_logins, methods=["GET"])


def register_modes_routes(app: FastAPI) -> None:
    def get_mode() -> dict[str, object]:
        from nexora_core.modes import get_mode_manager

        return get_mode_manager().get_mode_info()

    def list_modes() -> list[dict[str, object]]:
        from nexora_core.modes import list_modes as _list

        return _list()

    def switch_mode(
        target: str = Query(...), reason: str = Query("")
    ) -> dict[str, object]:
        from nexora_core.modes import get_mode_manager

        return get_mode_manager().switch_mode(target, reason=reason, operator="api")

    def escalate_mode(
        target: str = Query(...),
        duration_minutes: int = Query(60),
        reason: str = Query(""),
    ) -> dict[str, object]:
        from nexora_core.modes import get_mode_manager

        manager = get_mode_manager()
        return manager.create_escalation_token(
            target,
            duration_seconds=min(duration_minutes, 480) * 60,
            reason=reason,
        )

    def list_escalations() -> list[dict[str, object]]:
        from nexora_core.modes import get_mode_manager

        return get_mode_manager().list_escalation_tokens()

    def pending_confirmations() -> list[dict[str, object]]:
        from nexora_core.modes import list_pending_confirmations

        return list_pending_confirmations()

    def admin_log(
        x_nexora_tenant_id: str | None = Header(None),
    ) -> list[dict[str, object]]:
        from nexora_core.admin_actions import get_admin_action_log

        log = get_admin_action_log(50)
        if x_nexora_tenant_id:
            log = [
                entry for entry in log if entry.get("tenant_id") == x_nexora_tenant_id
            ]
        return log

    app.add_api_route("/api/mode", get_mode, methods=["GET"])
    app.add_api_route("/api/mode/list", list_modes, methods=["GET"])
    app.add_api_route("/api/mode/switch", switch_mode, methods=["POST"])
    app.add_api_route("/api/mode/escalate", escalate_mode, methods=["POST"])
    app.add_api_route("/api/mode/escalations", list_escalations, methods=["GET"])
    app.add_api_route("/api/mode/confirmations", pending_confirmations, methods=["GET"])
    app.add_api_route("/api/admin/log", admin_log, methods=["GET"])


def register_operations_routes(app: FastAPI) -> None:
    def adoption_report(
        domain: str | None = Query(None), path: str | None = Query(None)
    ) -> dict[str, object]:
        return service.adoption_report(domain, path)

    def adoption_import(
        domain: str | None = Query(None), path: str | None = Query(None)
    ) -> dict[str, object]:
        return service.import_existing_state(domain, path)

    def docker_status() -> dict[str, object]:
        from nexora_core.docker import docker_info

        return docker_info()

    def docker_containers() -> list[dict[str, object]]:
        from nexora_core.docker import list_containers

        return list_containers(True)

    def docker_templates() -> list[dict[str, object]]:
        from nexora_core.docker import list_docker_templates

        return list_docker_templates()

    def failover_strategies() -> list[dict[str, object]]:
        from nexora_core.failover import list_health_check_strategies

        return list_health_check_strategies()

    def storage_usage() -> dict[str, object]:
        from nexora_core.storage import disk_usage_detailed

        return disk_usage_detailed()

    def storage_ynh_map() -> dict[str, object]:
        from nexora_core.storage import yunohost_storage_map

        return yunohost_storage_map()

    def notification_templates() -> list[dict[str, object]]:
        from nexora_core.notifications import list_alert_templates

        return list_alert_templates()

    def sla_tiers() -> list[dict[str, object]]:
        from nexora_core.sla import list_sla_tiers

        return list_sla_tiers()

    def hook_events() -> list[dict[str, object]]:
        from nexora_core.hooks import list_hook_events

        return list_hook_events()

    def hook_presets() -> list[dict[str, object]]:
        from nexora_core.hooks import list_hook_presets

        return list_hook_presets()

    def automation_templates() -> list[dict[str, object]]:
        from nexora_core.automation import list_automation_templates

        return list_automation_templates()

    def automation_checklists() -> list[dict[str, object]]:
        from nexora_core.automation import list_checklists

        return list_checklists()

    def tenant_quota_usage(
        x_nexora_tenant_id: str | None = Header(None),
    ) -> dict[str, object]:
        return service.tenant_usage_vs_quota(tenant_id=x_nexora_tenant_id)

    def persistence_status() -> dict[str, object]:
        return service.persistence_status()

    def interface_parity() -> dict[str, object]:
        from nexora_core.interface_parity import fleet_lifecycle_parity_payload

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
    app.add_api_route(
        "/api/interface-parity/fleet-lifecycle", interface_parity, methods=["GET"]
    )
    app.add_api_route("/api/persistence", persistence_status, methods=["GET"])
    app.add_api_route("/api/metrics", metrics, methods=["GET"])

    app.add_api_route("/api/docker/status", docker_status, methods=["GET"])
    app.add_api_route("/api/docker/containers", docker_containers, methods=["GET"])
    app.add_api_route("/api/docker/templates", docker_templates, methods=["GET"])
    app.add_api_route("/api/failover/strategies", failover_strategies, methods=["GET"])
    app.add_api_route("/api/storage/usage", storage_usage, methods=["GET"])
    app.add_api_route("/api/storage/ynh-map", storage_ynh_map, methods=["GET"])
    app.add_api_route(
        "/api/notifications/templates", notification_templates, methods=["GET"]
    )
    app.add_api_route("/api/sla/tiers", sla_tiers, methods=["GET"])
    app.add_api_route("/api/tenants/usage-quota", tenant_quota_usage, methods=["GET"])
    app.add_api_route("/api/hooks/events", hook_events, methods=["GET"])
    app.add_api_route("/api/hooks/presets", hook_presets, methods=["GET"])
    app.add_api_route(
        "/api/automation/templates", automation_templates, methods=["GET"]
    )
    app.add_api_route(
        "/api/automation/checklists", automation_checklists, methods=["GET"]
    )


def register_console_routes(app: FastAPI) -> None:
    if CONSOLE_DIR.exists():
        app.mount(
            "/console", StaticFiles(directory=CONSOLE_DIR, html=True), name="console"
        )

    def root():
        if (CONSOLE_DIR / "index.html").exists():
            return RedirectResponse(url="/console/")
        return {"status": "ok", "hint": "Console not built yet"}

    def console_redirect():
        return RedirectResponse(url="/console/")

    app.add_api_route("/", root, methods=["GET"])
    app.add_api_route("/console", console_redirect, methods=["GET"])


app = build_application()


def main() -> None:
    host = os.environ.get("NEXORA_CONTROL_PLANE_HOST", "127.0.0.1")
    port = int(os.environ.get("NEXORA_CONTROL_PLANE_PORT", "38120"))
    uvicorn.run(app, host=host, port=port, reload=False)
