"""REST ↔ MCP parity definitions for canonical Nexora surfaces.

Covers all major surface areas:
- Fleet lifecycle (enrollment, lifecycle actions, compatibility)
- Governance (scoring, risks, executive report)
- Mode management (current, switch, escalate, confirmations)
- Node actions (branding, backup, cert, restart)
- Security / Audit (posture, fail2ban, permissions, ports)
"""

from __future__ import annotations

from typing import Any

FLEET_LIFECYCLE_PARITY = {
    "surface": "fleet-lifecycle",
    "scope": ["fleet", "enrollment", "lifecycle", "compatibility"],
    "entries": [
        {
            "capability": "fleet.summary",
            "rest": ["GET /api/fleet", "GET /api/v1/fleet"],
            "mcp": ["ynh_fleet_status"],
        },
        {
            "capability": "fleet.topology",
            "rest": ["GET /api/fleet/topology"],
            "mcp": ["ynh_fleet_topology"],
        },
        {
            "capability": "fleet.compatibility",
            "rest": ["GET /api/fleet/compatibility"],
            "mcp": ["ynh_fleet_compatibility"],
        },
        {
            "capability": "fleet.lifecycle-overview",
            "rest": ["GET /api/fleet/lifecycle"],
            "mcp": ["ynh_fleet_lifecycle"],
        },
        {
            "capability": "fleet.enrollment-request",
            "rest": ["POST /api/fleet/enroll/request"],
            "mcp": ["ynh_fleet_enrollment_request"],
        },
        {
            "capability": "fleet.enrollment-attest",
            "rest": ["POST /api/fleet/enroll/attest"],
            "mcp": ["ynh_fleet_enrollment_attest"],
        },
        {
            "capability": "fleet.enrollment-register",
            "rest": ["POST /api/fleet/enroll/register"],
            "mcp": ["ynh_fleet_enrollment_register"],
        },
        {
            "capability": "fleet.lifecycle-action",
            "rest": [
                "POST /api/fleet/nodes/{node_id}/drain",
                "POST /api/fleet/nodes/{node_id}/cordon",
                "POST /api/fleet/nodes/{node_id}/uncordon",
                "POST /api/fleet/nodes/{node_id}/revoke",
                "POST /api/fleet/nodes/{node_id}/retire",
                "POST /api/fleet/nodes/{node_id}/rotate-credentials",
                "POST /api/fleet/nodes/{node_id}/re-enroll",
                "POST /api/fleet/nodes/{node_id}/delete",
            ],
            "mcp": ["ynh_fleet_lifecycle_action"],
        },
    ],
}


GOVERNANCE_PARITY = {
    "surface": "governance",
    "scope": ["scoring", "risks", "executive-report", "changelog"],
    "entries": [
        {
            "capability": "governance.all-scores",
            "rest": ["GET /api/scores"],
            "mcp": ["ynh_gov_all_scores"],
        },
        {
            "capability": "governance.security-score",
            "rest": ["GET /api/scores"],
            "mcp": ["ynh_gov_security_score"],
        },
        {
            "capability": "governance.pra-score",
            "rest": ["GET /api/scores"],
            "mcp": ["ynh_gov_pra_score"],
        },
        {
            "capability": "governance.health-score",
            "rest": ["GET /api/scores"],
            "mcp": ["ynh_gov_health_score"],
        },
        {
            "capability": "governance.compliance-score",
            "rest": ["GET /api/scores"],
            "mcp": ["ynh_gov_compliance_score"],
        },
        {
            "capability": "governance.executive-report",
            "rest": ["GET /api/governance/report"],
            "mcp": ["ynh_gov_executive_report"],
        },
        {
            "capability": "governance.risk-register",
            "rest": ["GET /api/governance/risks"],
            "mcp": ["ynh_gov_risk_register"],
        },
        {
            "capability": "governance.change-log",
            "rest": ["GET /api/governance/changelog"],
            "mcp": ["ynh_gov_change_log"],
        },
        {
            "capability": "governance.snapshot-diff",
            "rest": ["GET /api/governance/snapshot-diff"],
            "mcp": ["ynh_gov_snapshot_diff"],
        },
    ],
}


MODE_MANAGEMENT_PARITY = {
    "surface": "mode-management",
    "scope": ["modes", "escalation", "confirmation", "admin-log"],
    "entries": [
        {
            "capability": "mode.current",
            "rest": ["GET /api/mode"],
            "mcp": ["ynh_mode_current"],
        },
        {
            "capability": "mode.list",
            "rest": ["GET /api/mode/list"],
            "mcp": ["ynh_mode_list"],
        },
        {
            "capability": "mode.switch",
            "rest": ["POST /api/mode/switch"],
            "mcp": ["ynh_mode_switch"],
        },
        {
            "capability": "mode.escalate",
            "rest": ["POST /api/mode/escalate"],
            "mcp": ["ynh_mode_escalate"],
        },
        {
            "capability": "mode.escalations",
            "rest": ["GET /api/mode/escalations"],
            "mcp": ["ynh_mode_list_escalations"],
        },
        {
            "capability": "mode.confirmations",
            "rest": ["GET /api/mode/confirmations"],
            "mcp": ["ynh_mode_pending_confirmations"],
        },
        {
            "capability": "mode.history",
            "rest": ["GET /api/admin/log"],
            "mcp": ["ynh_mode_history"],
        },
    ],
}


NODE_ACTIONS_PARITY = {
    "surface": "node-actions",
    "scope": ["branding", "backup", "cert", "service", "maintenance"],
    "entries": [
        {
            "capability": "node.apply-branding",
            "rest": [
                "POST /api/fleet/nodes/{node_id}/action",
                "POST /api/fleet/nodes/{node_id}/branding/apply",
            ],
            "mcp": ["ynh_op_apply_branding"],
            "node": ["POST /branding/apply"],
        },
        {
            "capability": "node.create-backup",
            "rest": ["POST /api/fleet/nodes/{node_id}/action"],
            "mcp": ["ynh_op_create_backup"],
        },
        {
            "capability": "node.backup-rotate",
            "rest": ["POST /api/fleet/nodes/{node_id}/action"],
            "mcp": ["ynh_op_backup_rotate"],
        },
        {
            "capability": "node.renew-cert",
            "rest": ["POST /api/fleet/nodes/{node_id}/action"],
            "mcp": ["ynh_op_renew_cert"],
        },
        {
            "capability": "node.restart-service",
            "rest": ["POST /api/fleet/nodes/{node_id}/action"],
            "mcp": ["ynh_op_restart_service"],
        },
        {
            "capability": "node.permissions-sync",
            "rest": [
                "POST /api/fleet/nodes/{node_id}/action",
                "POST /api/fleet/nodes/{node_id}/permissions/sync",
            ],
            "mcp": [],
            "node": ["POST /permissions/sync"],
        },
        {
            "capability": "node.inventory-refresh",
            "rest": [
                "POST /api/fleet/nodes/{node_id}/action",
                "POST /api/fleet/nodes/{node_id}/inventory/refresh",
            ],
            "mcp": [],
            "node": ["POST /inventory/refresh"],
        },
        {
            "capability": "node.healthcheck",
            "rest": [
                "POST /api/fleet/nodes/{node_id}/action",
                "POST /api/fleet/nodes/{node_id}/healthcheck/run",
            ],
            "mcp": [],
            "node": ["POST /healthcheck/run"],
        },
    ],
}


SECURITY_AUDIT_PARITY = {
    "surface": "security-audit",
    "scope": ["security", "fail2ban", "permissions", "ports", "logins"],
    "entries": [
        {
            "capability": "security.posture",
            "rest": ["GET /api/security/posture"],
            "mcp": ["ynh_security_audit"],
        },
        {
            "capability": "security.updates",
            "rest": ["GET /api/security/updates"],
            "mcp": ["ynh_security_check_updates"],
        },
        {
            "capability": "security.fail2ban-status",
            "rest": ["GET /api/security/fail2ban/status"],
            "mcp": ["ynh_security_fail2ban_status"],
        },
        {
            "capability": "security.fail2ban-ban",
            "rest": ["POST /api/security/fail2ban/ban"],
            "mcp": ["ynh_security_fail2ban_ban"],
        },
        {
            "capability": "security.fail2ban-unban",
            "rest": ["POST /api/security/fail2ban/unban"],
            "mcp": ["ynh_security_fail2ban_unban"],
        },
        {
            "capability": "security.open-ports",
            "rest": ["GET /api/security/open-ports"],
            "mcp": ["ynh_security_open_ports"],
        },
        {
            "capability": "security.permissions-audit",
            "rest": ["GET /api/security/permissions-audit"],
            "mcp": ["ynh_security_permissions_audit"],
        },
        {
            "capability": "security.recent-logins",
            "rest": ["GET /api/security/recent-logins"],
            "mcp": ["ynh_security_recent_logins"],
        },
    ],
}


ALL_PARITY_DEFINITIONS = [
    FLEET_LIFECYCLE_PARITY,
    GOVERNANCE_PARITY,
    MODE_MANAGEMENT_PARITY,
    NODE_ACTIONS_PARITY,
    SECURITY_AUDIT_PARITY,
]


def _build_parity_payload(definition: dict[str, Any]) -> dict[str, Any]:
    """Build a normalized parity payload from a parity definition."""
    entries = definition["entries"]
    gaps = [e for e in entries if e.get("gap")]
    return {
        "surface": definition["surface"],
        "scope": definition["scope"],
        "capabilities": entries,
        "summary": {
            "capability_count": len(entries),
            "rest_entry_count": sum(len(e.get("rest", [])) for e in entries),
            "mcp_entry_count": sum(len(e.get("mcp", [])) for e in entries),
            "gap_count": len(gaps),
        },
    }


def fleet_lifecycle_parity_payload() -> dict[str, Any]:
    """Return a normalized parity payload for fleet/lifecycle surfaces."""
    return _build_parity_payload(FLEET_LIFECYCLE_PARITY)


def governance_parity_payload() -> dict[str, Any]:
    """Return a normalized parity payload for governance surfaces."""
    return _build_parity_payload(GOVERNANCE_PARITY)


def mode_management_parity_payload() -> dict[str, Any]:
    """Return a normalized parity payload for mode management surfaces."""
    return _build_parity_payload(MODE_MANAGEMENT_PARITY)


def node_actions_parity_payload() -> dict[str, Any]:
    """Return a normalized parity payload for node action surfaces."""
    return _build_parity_payload(NODE_ACTIONS_PARITY)


def security_audit_parity_payload() -> dict[str, Any]:
    """Return a normalized parity payload for security/audit surfaces."""
    return _build_parity_payload(SECURITY_AUDIT_PARITY)


def full_parity_payload() -> dict[str, Any]:
    """Return combined parity payload for all surface areas."""
    surfaces = [_build_parity_payload(d) for d in ALL_PARITY_DEFINITIONS]
    total_caps = sum(s["summary"]["capability_count"] for s in surfaces)
    total_rest = sum(s["summary"]["rest_entry_count"] for s in surfaces)
    total_mcp = sum(s["summary"]["mcp_entry_count"] for s in surfaces)
    total_gaps = sum(s["summary"]["gap_count"] for s in surfaces)
    return {
        "surfaces": surfaces,
        "summary": {
            "surface_count": len(surfaces),
            "total_capabilities": total_caps,
            "total_rest_entries": total_rest,
            "total_mcp_entries": total_mcp,
            "total_gaps": total_gaps,
        },
    }
