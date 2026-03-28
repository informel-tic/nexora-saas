"""SaaS feature provisioning engine — pushes features down to enrolled nodes.

This is the CORE of the SaaS architecture:
- After a node enrolls, the SaaS decides which features to provision
- Features are determined by the tenant's subscription tier
- The SaaS builds HMAC-signed commands and dispatches them to nodes
- Nodes are PASSIVE — they only execute what the SaaS sends

Feature provisioning flow:
1. Node enrolls (calls SaaS enrollment API)
2. SaaS validates enrollment, assigns node to tenant
3. SaaS resolves the feature set for the tenant's tier
4. SaaS dispatches HMAC-signed commands to the node to install features
5. SaaS starts heartbeat loop to keep feature leases alive
6. If subscription is suspended/cancelled, SaaS stops heartbeating → features expire
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import Any

from .node_connector import (
    NodeConnector,
    build_cron_install_command,
    build_docker_install_command,
    build_establish_secret_command,
    build_heartbeat_command,
    build_nginx_install_command,
    build_rollback_command,
    build_service_deploy_command,
    build_systemd_install_command,
)
from .subscription import PlanTier, get_subscription_by_tenant

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Feature catalog — what each tier gets provisioned on nodes
# ---------------------------------------------------------------------------

TIER_FEATURE_SETS: dict[str, list[dict[str, Any]]] = {
    "free": [
        {
            "feature_id": "monitoring-basic",
            "name": "Basic Monitoring",
            "kind": "cron",
            "config": {
                "name": "nexora-health-check",
                "schedule": "*/15 * * * *",
                "command": "/opt/nexora/bin/health-report.sh",
            },
        },
        {
            "feature_id": "backup-local",
            "name": "Local Backup",
            "kind": "cron",
            "config": {
                "name": "nexora-backup-local",
                "schedule": "0 3 * * *",
                "command": "/opt/nexora/bin/backup-local.sh",
            },
        },
    ],
    "pro": [
        {
            "feature_id": "monitoring-advanced",
            "name": "Advanced Monitoring",
            "kind": "systemd",
            "config": {
                "name": "nexora-monitoring",
                "unit_content": (
                    "[Unit]\n"
                    "Description=Nexora Advanced Monitoring Agent\n"
                    "After=network.target\n\n"
                    "[Service]\n"
                    "Type=simple\n"
                    "ExecStart=/opt/nexora/bin/monitoring-agent\n"
                    "Restart=always\n"
                    "RestartSec=10\n\n"
                    "[Install]\n"
                    "WantedBy=multi-user.target\n"
                ),
            },
        },
        {
            "feature_id": "backup-local",
            "name": "Local Backup",
            "kind": "cron",
            "config": {
                "name": "nexora-backup-local",
                "schedule": "0 3 * * *",
                "command": "/opt/nexora/bin/backup-local.sh",
            },
        },
        {
            "feature_id": "pra-support",
            "name": "PRA Support",
            "kind": "cron",
            "config": {
                "name": "nexora-pra-snapshot",
                "schedule": "0 */6 * * *",
                "command": "/opt/nexora/bin/pra-snapshot.sh",
            },
        },
        {
            "feature_id": "fleet-lifecycle",
            "name": "Fleet Lifecycle Agent",
            "kind": "nginx",
            "config": {
                "name": "nexora-fleet-proxy",
                "content": (
                    "location /nexora-fleet/ {\n"
                    "    proxy_pass http://127.0.0.1:38121/;\n"
                    "    proxy_set_header Host $host;\n"
                    "    proxy_set_header X-Real-IP $remote_addr;\n"
                    "}\n"
                ),
                "domain": "__NODE_DOMAIN__",
            },
        },
        {
            "feature_id": "automation",
            "name": "Automation Engine",
            "kind": "cron",
            "config": {
                "name": "nexora-automation-runner",
                "schedule": "*/5 * * * *",
                "command": "/opt/nexora/bin/automation-runner.sh",
            },
        },
    ],
    "enterprise": [
        {
            "feature_id": "monitoring-advanced",
            "name": "Advanced Monitoring",
            "kind": "systemd",
            "config": {
                "name": "nexora-monitoring",
                "unit_content": (
                    "[Unit]\n"
                    "Description=Nexora Advanced Monitoring Agent\n"
                    "After=network.target\n\n"
                    "[Service]\n"
                    "Type=simple\n"
                    "ExecStart=/opt/nexora/bin/monitoring-agent\n"
                    "Restart=always\n"
                    "RestartSec=10\n\n"
                    "[Install]\n"
                    "WantedBy=multi-user.target\n"
                ),
            },
        },
        {
            "feature_id": "backup-local",
            "name": "Local Backup + Remote Sync",
            "kind": "cron",
            "config": {
                "name": "nexora-backup-full",
                "schedule": "0 2 * * *",
                "command": "/opt/nexora/bin/backup-full.sh --remote-sync",
            },
        },
        {
            "feature_id": "pra-support",
            "name": "PRA Full Suite",
            "kind": "cron",
            "config": {
                "name": "nexora-pra-snapshot",
                "schedule": "0 */4 * * *",
                "command": "/opt/nexora/bin/pra-snapshot.sh --full",
            },
        },
        {
            "feature_id": "fleet-lifecycle",
            "name": "Fleet Lifecycle Agent",
            "kind": "nginx",
            "config": {
                "name": "nexora-fleet-proxy",
                "content": (
                    "location /nexora-fleet/ {\n"
                    "    proxy_pass http://127.0.0.1:38121/;\n"
                    "    proxy_set_header Host $host;\n"
                    "    proxy_set_header X-Real-IP $remote_addr;\n"
                    "}\n"
                ),
                "domain": "__NODE_DOMAIN__",
            },
        },
        {
            "feature_id": "automation",
            "name": "Automation Engine",
            "kind": "cron",
            "config": {
                "name": "nexora-automation-runner",
                "schedule": "*/5 * * * *",
                "command": "/opt/nexora/bin/automation-runner.sh",
            },
        },
        {
            "feature_id": "sla-guarantee",
            "name": "SLA Guarantee Monitor",
            "kind": "systemd",
            "config": {
                "name": "nexora-sla-monitor",
                "unit_content": (
                    "[Unit]\n"
                    "Description=Nexora SLA Guarantee Monitor\n"
                    "After=network.target\n\n"
                    "[Service]\n"
                    "Type=simple\n"
                    "ExecStart=/opt/nexora/bin/sla-monitor\n"
                    "Restart=always\n"
                    "RestartSec=30\n\n"
                    "[Install]\n"
                    "WantedBy=multi-user.target\n"
                ),
            },
        },
        {
            "feature_id": "custom-branding",
            "name": "Custom Branding",
            "kind": "nginx",
            "config": {
                "name": "nexora-custom-branding",
                "content": (
                    "location /nexora-branding/ {\n"
                    "    alias /opt/nexora/branding/;\n"
                    "}\n"
                ),
                "domain": "__NODE_DOMAIN__",
            },
        },
    ],
}


def resolve_features_for_tier(tier: str) -> list[dict[str, Any]]:
    """Return the feature set for a given subscription tier."""
    return list(TIER_FEATURE_SETS.get(tier, TIER_FEATURE_SETS["free"]))


# ---------------------------------------------------------------------------
# Provisioning engine — builds the command sequence for a node
# ---------------------------------------------------------------------------

def provision_node_features(
    state: dict[str, Any],
    *,
    node_id: str,
    node_url: str,
    hmac_secret: str,
    api_token: str = "",
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """Build the full provisioning command sequence for an enrolled node.

    This is called by the SaaS after successful enrollment.
    Returns a list of HMAC-signed commands to dispatch to the node.
    """
    # Resolve the node's tenant and subscription
    if not tenant_id:
        node_record = next(
            (n for n in state.get("nodes", []) if n.get("node_id") == node_id),
            None,
        )
        if not node_record:
            return {"success": False, "error": f"Node '{node_id}' not found in state"}
        tenant_id = node_record.get("tenant_id")

    tier = "free"
    if tenant_id:
        sub = get_subscription_by_tenant(state, tenant_id)
        if sub:
            tier = sub.get("tier", "free")
        else:
            # Fallback to tenant record tier
            tenant = next(
                (t for t in state.get("tenants", []) if t.get("tenant_id") == tenant_id),
                None,
            )
            if tenant:
                tier = tenant.get("tier", "free")

    features = resolve_features_for_tier(tier)
    connector = NodeConnector(node_id, node_url, hmac_secret, api_token)

    commands: list[dict[str, Any]] = []

    # Step 1: Establish HMAC secret on the node
    commands.append(build_establish_secret_command(connector, hmac_secret))

    # Step 2: Build feature installation commands
    for feature in features:
        kind = feature["kind"]
        config = feature["config"]
        if kind == "cron":
            commands.append(build_cron_install_command(
                connector, config["name"], config["schedule"], config["command"]
            ))
        elif kind == "systemd":
            commands.append(build_systemd_install_command(
                connector, config["name"], config["unit_content"]
            ))
        elif kind == "nginx":
            commands.append(build_nginx_install_command(
                connector, config["name"], config["content"], config["domain"]
            ))
        elif kind == "docker":
            commands.append(build_docker_install_command(connector))
            if "compose" in config:
                commands.append(build_service_deploy_command(
                    connector, config["name"], config["compose"], config.get("nginx_snippet")
                ))

    # Step 3: Initial heartbeat to activate leases
    commands.append(build_heartbeat_command(connector, lease_seconds=86400))

    # Record provisioning event in state
    state.setdefault("provisioning_events", [])
    event = {
        "node_id": node_id,
        "tenant_id": tenant_id,
        "tier": tier,
        "features_count": len(features),
        "commands_count": len(commands),
        "provisioned_at": _utc_now(),
        "status": "pending_dispatch",
    }
    state["provisioning_events"].append(event)

    return {
        "success": True,
        "node_id": node_id,
        "tenant_id": tenant_id,
        "tier": tier,
        "features": [
            {"feature_id": f["feature_id"], "name": f["name"], "kind": f["kind"]}
            for f in features
        ],
        "commands": commands,
        "provisioning_event": event,
    }


def deprovision_node(
    state: dict[str, Any],
    *,
    node_id: str,
    node_url: str,
    hmac_secret: str = "",
) -> dict[str, Any]:
    """Build rollback command to remove all features from a node."""
    connector = NodeConnector(node_id, node_url, hmac_secret)
    command = build_rollback_command(connector)

    state.setdefault("provisioning_events", [])
    state["provisioning_events"].append({
        "node_id": node_id,
        "action": "deprovision",
        "deprovisioned_at": _utc_now(),
        "status": "pending_dispatch",
    })

    return {
        "success": True,
        "node_id": node_id,
        "commands": [command],
    }


def build_heartbeat_for_node(
    state: dict[str, Any],
    *,
    node_id: str,
    node_url: str,
    hmac_secret: str,
    api_token: str = "",
    lease_seconds: int = 86400,
) -> dict[str, Any]:
    """Build a heartbeat command for a specific enrolled node."""
    connector = NodeConnector(node_id, node_url, hmac_secret, api_token)
    command = build_heartbeat_command(connector, lease_seconds)
    return {"success": True, "node_id": node_id, "command": command}


def get_node_provisioning_status(
    state: dict[str, Any], node_id: str
) -> dict[str, Any]:
    """Get provisioning history for a node."""
    events = [
        e for e in state.get("provisioning_events", [])
        if e.get("node_id") == node_id
    ]
    return {
        "node_id": node_id,
        "events": events,
        "total_events": len(events),
        "last_event": events[-1] if events else None,
    }
