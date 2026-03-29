"""SaaS-side connector for communicating with enrolled nodes.

The SaaS control plane uses this module to push features DOWN to nodes
after enrollment. All mutations to a node require HMAC-signed requests.

Architecture:
- Node is a PASSIVE RECEIVER — it cannot install features on its own
- SaaS pushes features via HMAC-signed HTTP commands
- Node validates the HMAC signature before executing any mutation
- Heartbeats renew feature leases — if SaaS stops heartbeating, features expire
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compute_hmac_signature(
    secret: str,
    action: str,
    timestamp: str,
    payload: dict[str, Any] | None = None,
) -> str:
    """Compute HMAC-SHA256 signature for a SaaS command to a node.

    The signature covers: action + timestamp + sorted JSON payload.
    """
    body = json.dumps(payload or {}, sort_keys=True, separators=(",", ":"))
    message = f"{action}:{timestamp}:{body}"
    return hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


class NodeConnector:
    """Manages the SaaS-to-node communication channel.

    Each enrolled node has:
    - A base URL (the node agent endpoint)
    - A shared HMAC secret (established during enrollment)
    - An API token for authentication

    The connector signs all mutation requests with HMAC so the node
    can verify they come from the legitimate SaaS control plane.
    """

    def __init__(
        self,
        node_id: str,
        base_url: str,
        hmac_secret: str,
        api_token: str = "",
    ):
        self.node_id = node_id
        self.base_url = base_url.rstrip("/")
        self.hmac_secret = hmac_secret
        self.api_token = api_token

    def _build_signed_headers(
        self,
        action: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        """Build HTTP headers with HMAC signature for a SaaS command."""
        timestamp = _utc_now()
        signature = _compute_hmac_signature(
            self.hmac_secret, action, timestamp, payload
        )
        headers = {
            "Content-Type": "application/json",
            "X-Nexora-SaaS-Signature": signature,
            "X-Nexora-SaaS-Timestamp": timestamp,
        }
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    def build_command(
        self,
        action: str,
        endpoint: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build a signed command ready to be sent to the node.

        Returns the full HTTP request specification (URL, headers, body)
        that can be dispatched by the provisioning engine.
        """
        headers = self._build_signed_headers(action, payload)
        return {
            "node_id": self.node_id,
            "method": "POST",
            "url": f"{self.base_url}{endpoint}",
            "headers": headers,
            "body": payload,
            "action": action,
            "timestamp": headers["X-Nexora-SaaS-Timestamp"],
        }


# ---------------------------------------------------------------------------
# Command builders for each overlay mutation
# ---------------------------------------------------------------------------

def build_establish_secret_command(connector: NodeConnector, secret: str) -> dict[str, Any]:
    """Build command to establish the HMAC shared secret on a node."""
    return connector.build_command(
        "establish-secret",
        "/overlay/establish-secret",
        {"saas_secret": secret},
    )


def build_heartbeat_command(
    connector: NodeConnector, lease_seconds: int = 86400
) -> dict[str, Any]:
    """Build heartbeat command to renew feature leases on a node."""
    return connector.build_command(
        "overlay/heartbeat",
        "/overlay/heartbeat",
        {"lease_seconds": lease_seconds},
    )


def build_docker_install_command(connector: NodeConnector) -> dict[str, Any]:
    return connector.build_command("docker/install", "/overlay/docker/install")


def build_service_deploy_command(
    connector: NodeConnector,
    name: str,
    compose_content: str,
    nginx_snippet: str | None = None,
) -> dict[str, Any]:
    payload = {"name": name, "compose": compose_content}
    if nginx_snippet:
        payload["nginx_snippet"] = nginx_snippet
    return connector.build_command("service/deploy", "/overlay/service/deploy", payload)


def build_nginx_install_command(
    connector: NodeConnector, name: str, content: str, domain: str
) -> dict[str, Any]:
    return connector.build_command(
        "nginx/install",
        "/overlay/nginx/install",
        {"name": name, "content": content, "domain": domain},
    )


def build_cron_install_command(
    connector: NodeConnector, name: str, schedule: str, command: str
) -> dict[str, Any]:
    return connector.build_command(
        "cron/install",
        "/overlay/cron/install",
        {"name": name, "schedule": schedule, "command": command},
    )


def build_systemd_install_command(
    connector: NodeConnector, name: str, unit_content: str
) -> dict[str, Any]:
    return connector.build_command(
        "systemd/install",
        "/overlay/systemd/install",
        {"name": name, "unit_content": unit_content},
    )


def build_rollback_command(connector: NodeConnector) -> dict[str, Any]:
    """Rollback does NOT require HMAC (must work during uninstall)."""
    return {
        "node_id": connector.node_id,
        "method": "POST",
        "url": f"{connector.base_url}/overlay/rollback",
        "headers": {"Content-Type": "application/json"},
        "body": None,
        "action": "overlay/rollback",
        "timestamp": _utc_now(),
    }
