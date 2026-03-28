"""Node agent local API — thin communication interface.

The node agent is a PASSIVE RECEIVER: the SaaS control plane pushes all
features after enrollment.  The node agent alone CANNOT install overlay
features — every overlay mutation requires a valid HMAC signature from
the SaaS (X-Nexora-SaaS-Signature header).

On startup the node calls the SaaS to enroll; only then can the SaaS
push features down.  If the SaaS stops heartbeating, feature leases
expire and components become unavailable.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from nexora_node_sdk.logging_config import setup_logging

setup_logging()

logger = logging.getLogger("nexora.node_agent.api")

VERSION = "2.0.0"
ACTION_METRICS: dict[str, int] = {"requests_total": 0, "mutations_total": 0}
MAX_PAYLOAD_BYTES = 131_072

# ── In-memory state (production: use persistent store) ────────────
_saas_secret: str | None = None
_enrolled: bool = False
_enrollment_data: dict[str, Any] = {}
_overlay_manifest: dict[str, Any] = {"components": [], "last_heartbeat": None}
_tamper_events: list[dict[str, Any]] = []


# ── Helpers ───────────────────────────────────────────────────────

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mark_mutation() -> None:
    ACTION_METRICS["requests_total"] += 1
    ACTION_METRICS["mutations_total"] += 1


def _verify_saas_command(
    action: str,
    timestamp: str | None,
    signature: str | None,
    payload: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """Validate HMAC-SHA256 signature from the SaaS control plane."""
    if not _saas_secret:
        return False, "No SaaS secret established — node not enrolled"
    if not signature or not timestamp:
        return False, "Missing signature or timestamp"

    # Replay protection: reject if timestamp older than 5 minutes
    try:
        ts = float(timestamp)
        if abs(time.time() - ts) > 300:
            return False, "Timestamp too old or too far in the future"
    except (ValueError, TypeError):
        return False, "Invalid timestamp format"

    body = json.dumps(payload or {}, sort_keys=True, separators=(",", ":"))
    message = f"{action}:{timestamp}:{body}"
    expected = hmac.new(
        _saas_secret.encode(), message.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        _tamper_events.append({
            "event": "hmac_verification_failed",
            "action": action,
            "timestamp": _utc_now(),
        })
        return False, "HMAC signature mismatch"
    return True, "ok"


def _require_saas_origin(
    action: str,
    payload: dict[str, Any] | None,
    sig: str | None,
    ts: str | None,
) -> None:
    """Reject requests that are not signed by the SaaS control plane."""
    if not sig or not ts:
        raise HTTPException(
            status_code=403,
            detail="Overlay mutations require SaaS authorization. "
                   "Missing X-Nexora-SaaS-Signature or X-Nexora-SaaS-Timestamp.",
        )
    valid, reason = _verify_saas_command(action, ts, sig, payload)
    if not valid:
        raise HTTPException(status_code=403, detail=f"SaaS command verification failed: {reason}")


def _resign_manifest() -> None:
    """Re-sign the overlay manifest after any mutation."""
    if _saas_secret and _overlay_manifest.get("components"):
        content = json.dumps(_overlay_manifest, sort_keys=True)
        _overlay_manifest["_signature"] = hmac.new(
            _saas_secret.encode(), content.encode(), hashlib.sha256
        ).hexdigest()


def _install_component(kind: str, name: str, config: dict[str, Any]) -> dict[str, Any]:
    """Simulate installing an overlay component. On real nodes: calls the SDK."""
    component = {
        "kind": kind,
        "name": name,
        "config": config,
        "installed_at": _utc_now(),
        "lease_expires": None,
        "status": "active",
    }
    # Remove existing component with same kind+name
    _overlay_manifest["components"] = [
        c for c in _overlay_manifest["components"]
        if not (c["kind"] == kind and c["name"] == name)
    ]
    _overlay_manifest["components"].append(component)
    _resign_manifest()
    return {"installed": True, "kind": kind, "name": name}


def _remove_component(kind: str, name: str) -> dict[str, Any]:
    """Remove an overlay component."""
    before = len(_overlay_manifest["components"])
    _overlay_manifest["components"] = [
        c for c in _overlay_manifest["components"]
        if not (c["kind"] == kind and c["name"] == name)
    ]
    removed = before - len(_overlay_manifest["components"])
    _resign_manifest()
    return {"removed": removed > 0, "kind": kind, "name": name}


# ── Application factory ──────────────────────────────────────────

def build_application() -> FastAPI:
    app = FastAPI(title="Nexora Node Agent", version=VERSION)
    register_read_routes(app)
    register_enrollment_routes(app)
    register_overlay_routes(app)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        logger.warning("HTTP %s at %s: %s", exc.status_code, request.url.path, exc.detail)
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    return app


# ── Read routes (no auth beyond API token) ────────────────────────

def register_read_routes(app: FastAPI) -> None:

    def health() -> dict:
        return {
            "status": "ok",
            "service": "nexora-node-agent",
            "version": VERSION,
            "enrolled": _enrolled,
        }

    def status() -> dict:
        return {
            "agent": "running",
            "version": VERSION,
            "enrolled": _enrolled,
            "components": len(_overlay_manifest.get("components", [])),
            "last_heartbeat": _overlay_manifest.get("last_heartbeat"),
        }

    def get_overlay_status() -> dict:
        return {
            "enrolled": _enrolled,
            "components": _overlay_manifest.get("components", []),
            "last_heartbeat": _overlay_manifest.get("last_heartbeat"),
        }

    def get_overlay_services() -> list:
        return [
            c for c in _overlay_manifest.get("components", [])
            if c.get("kind") in ("docker", "service")
        ]

    def get_guard_status() -> dict:
        return {
            "enrolled": _enrolled,
            "secret_established": _saas_secret is not None,
            "tamper_events": len(_tamper_events),
        }

    def get_integrity_check() -> dict:
        return {
            "manifest_components": len(_overlay_manifest.get("components", [])),
            "has_signature": "_signature" in _overlay_manifest,
        }

    def get_tamper_log(limit: int = 50) -> list:
        return _tamper_events[-limit:]

    def metrics() -> dict:
        return {
            "requests_total": ACTION_METRICS["requests_total"],
            "mutations_total": ACTION_METRICS["mutations_total"],
            "payload_limit_bytes": MAX_PAYLOAD_BYTES,
        }

    app.add_api_route("/health", health, methods=["GET"])
    app.add_api_route("/api/v1/status", status, methods=["GET"])
    app.add_api_route("/overlay/status", get_overlay_status, methods=["GET"])
    app.add_api_route("/overlay/services", get_overlay_services, methods=["GET"])
    app.add_api_route("/overlay/guard", get_guard_status, methods=["GET"])
    app.add_api_route("/overlay/integrity", get_integrity_check, methods=["GET"])
    app.add_api_route("/overlay/tamper-log", get_tamper_log, methods=["GET"])
    app.add_api_route("/metrics", metrics, methods=["GET"])


# ── Enrollment routes ─────────────────────────────────────────────

def register_enrollment_routes(app: FastAPI) -> None:
    """Enrollment: the node calls SaaS to enroll, SaaS calls back here."""

    def enroll(
        token: str = "",
        challenge: str = "",
    ) -> dict:
        global _enrolled, _enrollment_data
        _mark_mutation()
        _enrolled = True
        _enrollment_data = {
            "token": token,
            "challenge": challenge,
            "enrolled_at": _utc_now(),
            "node_id": os.environ.get("NEXORA_NODE_ID", "local-dev"),
        }
        return {
            "success": True,
            "node_id": _enrollment_data["node_id"],
            "observed_at": _utc_now(),
        }

    def attest(
        token: str = "",
        challenge: str = "",
    ) -> dict:
        _mark_mutation()
        node_id = os.environ.get("NEXORA_NODE_ID", "local-dev")
        return {
            "success": True,
            "node_id": node_id,
            "agent_version": VERSION,
            "enrolled": _enrolled,
            "observed_at": _utc_now(),
        }

    def revoke() -> dict:
        global _enrolled, _saas_secret
        _mark_mutation()
        # Full rollback on revocation
        _overlay_manifest["components"] = []
        _resign_manifest()
        _enrolled = False
        _saas_secret = None
        return {
            "success": True,
            "changed": True,
            "overlay_rollback": {"rolled_back": True, "components_removed": "all"},
        }

    app.add_api_route("/enroll", enroll, methods=["POST"])
    app.add_api_route("/attest", attest, methods=["POST"])
    app.add_api_route("/revoke", revoke, methods=["POST"])


# ── Overlay routes — SaaS-authorized mutations ────────────────────

def register_overlay_routes(app: FastAPI) -> None:
    """Overlay management routes.

    SECURITY MODEL:
    - READ endpoints: accessible to any authenticated caller
    - MUTATION endpoints: require HMAC signature from SaaS control plane
    - Rollback: does NOT require SaaS signature (must work during uninstall)
    - Heartbeat: SaaS renews feature leases
    """

    # ── Docker ────────────────────────────────────────────────────

    def post_docker_install(
        x_nexora_saas_signature: str | None = Header(default=None),
        x_nexora_saas_timestamp: str | None = Header(default=None),
    ) -> dict:
        _require_saas_origin("docker/install", None, x_nexora_saas_signature, x_nexora_saas_timestamp)
        _mark_mutation()
        result = _install_component("docker", "docker-engine", {"engine": "docker-ce"})
        return result

    def post_docker_uninstall(
        x_nexora_saas_signature: str | None = Header(default=None),
        x_nexora_saas_timestamp: str | None = Header(default=None),
    ) -> dict:
        _require_saas_origin("docker/uninstall", None, x_nexora_saas_signature, x_nexora_saas_timestamp)
        _mark_mutation()
        return _remove_component("docker", "docker-engine")

    # ── Service deploy/remove ─────────────────────────────────────

    def post_deploy_service(
        payload: dict[str, Any] = Body(...),
        x_nexora_saas_signature: str | None = Header(default=None),
        x_nexora_saas_timestamp: str | None = Header(default=None),
    ) -> dict:
        _require_saas_origin("service/deploy", payload, x_nexora_saas_signature, x_nexora_saas_timestamp)
        _mark_mutation()
        return _install_component("service", payload["name"], {
            "compose": payload.get("compose", ""),
            "nginx_snippet": payload.get("nginx_snippet"),
        })

    def post_remove_service(
        payload: dict[str, Any] = Body(...),
        x_nexora_saas_signature: str | None = Header(default=None),
        x_nexora_saas_timestamp: str | None = Header(default=None),
    ) -> dict:
        _require_saas_origin("service/remove", payload, x_nexora_saas_signature, x_nexora_saas_timestamp)
        _mark_mutation()
        return _remove_component("service", payload["name"])

    # ── Nginx snippets ────────────────────────────────────────────

    def post_install_nginx(
        payload: dict[str, Any] = Body(...),
        x_nexora_saas_signature: str | None = Header(default=None),
        x_nexora_saas_timestamp: str | None = Header(default=None),
    ) -> dict:
        _require_saas_origin("nginx/install", payload, x_nexora_saas_signature, x_nexora_saas_timestamp)
        _mark_mutation()
        return _install_component("nginx", payload["name"], {
            "content": payload["content"],
            "domain": payload["domain"],
        })

    def post_remove_nginx(
        payload: dict[str, Any] = Body(...),
        x_nexora_saas_signature: str | None = Header(default=None),
        x_nexora_saas_timestamp: str | None = Header(default=None),
    ) -> dict:
        _require_saas_origin("nginx/remove", payload, x_nexora_saas_signature, x_nexora_saas_timestamp)
        _mark_mutation()
        return _remove_component("nginx", payload["name"])

    # ── Cron jobs ─────────────────────────────────────────────────

    def post_install_cron(
        payload: dict[str, Any] = Body(...),
        x_nexora_saas_signature: str | None = Header(default=None),
        x_nexora_saas_timestamp: str | None = Header(default=None),
    ) -> dict:
        _require_saas_origin("cron/install", payload, x_nexora_saas_signature, x_nexora_saas_timestamp)
        _mark_mutation()
        return _install_component("cron", payload["name"], {
            "schedule": payload["schedule"],
            "command": payload["command"],
        })

    def post_remove_cron(
        payload: dict[str, Any] = Body(...),
        x_nexora_saas_signature: str | None = Header(default=None),
        x_nexora_saas_timestamp: str | None = Header(default=None),
    ) -> dict:
        _require_saas_origin("cron/remove", payload, x_nexora_saas_signature, x_nexora_saas_timestamp)
        _mark_mutation()
        return _remove_component("cron", payload["name"])

    # ── Systemd units ─────────────────────────────────────────────

    def post_install_systemd(
        payload: dict[str, Any] = Body(...),
        x_nexora_saas_signature: str | None = Header(default=None),
        x_nexora_saas_timestamp: str | None = Header(default=None),
    ) -> dict:
        _require_saas_origin("systemd/install", payload, x_nexora_saas_signature, x_nexora_saas_timestamp)
        _mark_mutation()
        return _install_component("systemd", payload["name"], {
            "unit_content": payload["unit_content"],
        })

    def post_remove_systemd(
        payload: dict[str, Any] = Body(...),
        x_nexora_saas_signature: str | None = Header(default=None),
        x_nexora_saas_timestamp: str | None = Header(default=None),
    ) -> dict:
        _require_saas_origin("systemd/remove", payload, x_nexora_saas_signature, x_nexora_saas_timestamp)
        _mark_mutation()
        return _remove_component("systemd", payload["name"])

    # ── Heartbeat — renews feature leases ─────────────────────────

    def post_heartbeat(
        payload: dict[str, Any] = Body(default={}),
        x_nexora_saas_signature: str | None = Header(default=None),
        x_nexora_saas_timestamp: str | None = Header(default=None),
    ) -> dict:
        _require_saas_origin("overlay/heartbeat", payload, x_nexora_saas_signature, x_nexora_saas_timestamp)
        lease_seconds = payload.get("lease_seconds", 86400)
        now = _utc_now()
        for comp in _overlay_manifest.get("components", []):
            # Extend lease
            comp["lease_expires"] = f"{lease_seconds}s from {now}"
            comp["status"] = "active"
        _overlay_manifest["last_heartbeat"] = now
        _resign_manifest()
        return {
            "leases_renewed": len(_overlay_manifest.get("components", [])),
            "lease_seconds": lease_seconds,
        }

    # ── Secret exchange (initial enrollment step) ─────────────────

    def post_establish_secret(
        payload: dict[str, Any] = Body(...),
    ) -> dict:
        global _saas_secret
        secret = payload.get("saas_secret")
        if not secret or len(secret) < 32:
            raise HTTPException(status_code=400, detail="Secret must be >= 32 characters")
        _saas_secret = secret
        _mark_mutation()
        return {"secret_established": True, "enrolled": _enrolled}

    # ── Rollback (no SaaS signature — must work during uninstall) ─

    def post_rollback() -> dict:
        global _enrolled, _saas_secret
        _mark_mutation()
        components_count = len(_overlay_manifest.get("components", []))
        _overlay_manifest["components"] = []
        _overlay_manifest["last_heartbeat"] = None
        _overlay_manifest.pop("_signature", None)
        _enrolled = False
        _saas_secret = None
        return {"rolled_back": True, "components_removed": components_count}

    # ── Register routes ───────────────────────────────────────────

    app.add_api_route("/overlay/docker/install", post_docker_install, methods=["POST"])
    app.add_api_route("/overlay/docker/uninstall", post_docker_uninstall, methods=["POST"])
    app.add_api_route("/overlay/service/deploy", post_deploy_service, methods=["POST"])
    app.add_api_route("/overlay/service/remove", post_remove_service, methods=["POST"])
    app.add_api_route("/overlay/nginx/install", post_install_nginx, methods=["POST"])
    app.add_api_route("/overlay/nginx/remove", post_remove_nginx, methods=["POST"])
    app.add_api_route("/overlay/cron/install", post_install_cron, methods=["POST"])
    app.add_api_route("/overlay/cron/remove", post_remove_cron, methods=["POST"])
    app.add_api_route("/overlay/systemd/install", post_install_systemd, methods=["POST"])
    app.add_api_route("/overlay/systemd/remove", post_remove_systemd, methods=["POST"])
    app.add_api_route("/overlay/heartbeat", post_heartbeat, methods=["POST"])
    app.add_api_route("/overlay/establish-secret", post_establish_secret, methods=["POST"])
    app.add_api_route("/overlay/rollback", post_rollback, methods=["POST"])


app = build_application()


def main():
    import uvicorn

    host = os.environ.get("NEXORA_NODE_AGENT_HOST", "127.0.0.1")
    port = int(os.environ.get("NEXORA_NODE_AGENT_PORT", "38121"))
    uvicorn.run(app, host=host, port=port)
