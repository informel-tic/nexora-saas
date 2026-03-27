"""Tier-gated automation engine.

Bridges subscription tier → automation profile → job scheduling,
enforcing that subscribers only get the automation level their tier allows.
This module wraps the existing ``automation.py`` templates with tier-awareness,
execution tracking, and a subscriber-facing job status API.
"""

from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
from typing import Any

try:
    from nexora_core.automation import (
        AUTOMATION_TEMPLATES,
        generate_automation_plan,
        generate_crontab,
        list_automation_templates,
    )
    from nexora_core.models import TenantTier
    from nexora_core.subscriber_features import (
        get_automation_profile_for_tier,
        is_feature_available,
    )
except ImportError:
    AUTOMATION_TEMPLATES = {}
    generate_automation_plan = None  # type: ignore[assignment]
    generate_crontab = None  # type: ignore[assignment]
    list_automation_templates = None  # type: ignore[assignment]
    TenantTier = None  # type: ignore[assignment,misc]
    get_automation_profile_for_tier = None  # type: ignore[assignment]
    is_feature_available = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


# ── Tier → allowed templates mapping ──────────────────────────────────

_TIER_PROFILES = {
    TenantTier.FREE: "minimal",
    TenantTier.PRO: "standard",
    TenantTier.ENTERPRISE: "professional",
}

_PROFILE_TEMPLATES = {
    "minimal": {"daily_backup", "cert_renewal_check"},
    "standard": {
        "daily_backup",
        "daily_health_check",
        "weekly_security_audit",
        "weekly_pra_snapshot",
        "cert_renewal_check",
    },
    "professional": set(AUTOMATION_TEMPLATES.keys()),
}


def _resolve_tier(tier: TenantTier | str) -> TenantTier:
    if isinstance(tier, str):
        try:
            return TenantTier(tier)
        except ValueError:
            return TenantTier.FREE
    return tier


# ── Public API ────────────────────────────────────────────────────────


def get_allowed_templates(tier: TenantTier | str) -> list[dict[str, Any]]:
    """Return only the automation templates allowed for this tier."""
    tier = _resolve_tier(tier)
    profile = _TIER_PROFILES.get(tier, "minimal")
    allowed_ids = _PROFILE_TEMPLATES.get(profile, _PROFILE_TEMPLATES["minimal"])
    return [
        {"id": k, **v}
        for k, v in AUTOMATION_TEMPLATES.items()
        if k in allowed_ids
    ]


def get_blocked_templates(tier: TenantTier | str) -> list[dict[str, Any]]:
    """Return templates that require a higher tier, with upgrade hints."""
    tier = _resolve_tier(tier)
    profile = _TIER_PROFILES.get(tier, "minimal")
    allowed_ids = _PROFILE_TEMPLATES.get(profile, _PROFILE_TEMPLATES["minimal"])
    blocked = []
    for k, v in AUTOMATION_TEMPLATES.items():
        if k not in allowed_ids:
            required_tier = _minimum_tier_for_template(k)
            blocked.append({
                "id": k,
                **v,
                "required_tier": required_tier.value if required_tier else "unknown",
                "upgrade_hint": f"Upgrade to {required_tier.value} to unlock '{v['name']}'."
                if required_tier
                else "",
            })
    return blocked


def generate_tier_automation_plan(tier: TenantTier | str) -> dict[str, Any]:
    """Generate an automation plan gated by the subscriber's tier."""
    tier = _resolve_tier(tier)
    profile = get_automation_profile_for_tier(tier)
    plan = generate_automation_plan(profile)
    plan["tier"] = tier.value
    plan["allowed_template_count"] = len(
        _PROFILE_TEMPLATES.get(profile, _PROFILE_TEMPLATES["minimal"])
    )
    plan["total_template_count"] = len(AUTOMATION_TEMPLATES)

    # Add upgrade info if not on the highest tier
    if tier != TenantTier.ENTERPRISE:
        blocked = get_blocked_templates(tier)
        plan["blocked_templates"] = blocked
        plan["upgrade_unlocks"] = len(blocked)
    else:
        plan["blocked_templates"] = []
        plan["upgrade_unlocks"] = 0

    return plan


def generate_tier_crontab(
    tier: TenantTier | str, user: str = "nexora"
) -> dict[str, Any]:
    """Generate the crontab content for a tier, with metadata."""
    tier = _resolve_tier(tier)
    plan = generate_tier_automation_plan(tier)
    content = generate_crontab(plan["jobs"], user)
    return {
        "tier": tier.value,
        "profile": plan["profile"],
        "content": content,
        "job_count": plan["job_count"],
        "blocked_count": plan.get("upgrade_unlocks", 0),
    }


def is_template_allowed(template_id: str, tier: TenantTier | str) -> bool:
    """Check if a specific template is allowed for the given tier."""
    tier = _resolve_tier(tier)
    profile = _TIER_PROFILES.get(tier, "minimal")
    allowed = _PROFILE_TEMPLATES.get(profile, _PROFILE_TEMPLATES["minimal"])
    return template_id in allowed


# ── Job execution tracking ────────────────────────────────────────────


def record_job_execution(
    template_id: str,
    *,
    success: bool,
    tier: TenantTier | str,
    duration_s: float = 0,
    error: str = "",
    state_path: str | None = None,
) -> dict[str, Any]:
    """Record a job execution result for tracking and reporting."""
    tier = _resolve_tier(tier)
    path = Path(state_path) if state_path else Path("/opt/nexora/var/automation-history.json")
    try:
        data = json.loads(path.read_text()) if path.exists() else {"executions": []}
    except Exception:
        data = {"executions": []}

    entry = {
        "template_id": template_id,
        "tier": tier.value,
        "success": success,
        "duration_s": duration_s,
        "error": error,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    data["executions"].append(entry)
    # Keep last 500 entries
    data["executions"] = data["executions"][-500:]
    data["last_execution"] = entry["timestamp"]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    return {
        "recorded": True,
        "template_id": template_id,
        "executions_total": len(data["executions"]),
    }


def get_job_history(
    *, tier: TenantTier | str | None = None, state_path: str | None = None
) -> dict[str, Any]:
    """Get automation job execution history, optionally filtered by tier."""
    path = Path(state_path) if state_path else Path("/opt/nexora/var/automation-history.json")
    try:
        data = json.loads(path.read_text()) if path.exists() else {"executions": []}
    except Exception:
        data = {"executions": []}

    executions = data.get("executions", [])
    if tier is not None:
        tier = _resolve_tier(tier)
        executions = [e for e in executions if e.get("tier") == tier.value]

    success_count = sum(1 for e in executions if e.get("success"))
    failure_count = len(executions) - success_count

    return {
        "total_executions": len(executions),
        "success_count": success_count,
        "failure_count": failure_count,
        "success_rate": round(success_count / len(executions) * 100, 1) if executions else 0,
        "last_execution": data.get("last_execution"),
        "recent": executions[-20:],
    }


def get_automation_status(tier: TenantTier | str) -> dict[str, Any]:
    """Full automation status for the subscriber dashboard."""
    tier = _resolve_tier(tier)
    plan = generate_tier_automation_plan(tier)
    history = get_job_history(tier=tier)

    return {
        "tier": tier.value,
        "profile": plan["profile"],
        "active_jobs": plan["job_count"],
        "total_available": plan.get("total_template_count", len(AUTOMATION_TEMPLATES)),
        "blocked_count": plan.get("upgrade_unlocks", 0),
        "execution_history": {
            "total": history["total_executions"],
            "success_rate": history["success_rate"],
            "last_run": history["last_execution"],
        },
        "jobs": [
            {
                "id": j["id"],
                "name": j["name"],
                "schedule": j["schedule"],
                "risk": j.get("risk", "low"),
            }
            for j in plan["jobs"]
        ],
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


# ── Private helpers ───────────────────────────────────────────────────


def _minimum_tier_for_template(template_id: str) -> TenantTier | None:
    """Find the minimum tier that includes this template."""
    for tier in (TenantTier.FREE, TenantTier.PRO, TenantTier.ENTERPRISE):
        profile = _TIER_PROFILES.get(tier, "minimal")
        if template_id in _PROFILE_TEMPLATES.get(profile, set()):
            return tier
    return None
