"""SLA monitoring: uptime tracking, response time, compliance reporting."""

from __future__ import annotations
import json
import logging

import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SLA_TIERS = {
    "basic": {
        "uptime_target": 99.0,
        "response_time_ms": 5000,
        "backup_frequency": "weekly",
        "support": "community",
    },
    "standard": {
        "uptime_target": 99.5,
        "response_time_ms": 2000,
        "backup_frequency": "daily",
        "support": "email",
    },
    "professional": {
        "uptime_target": 99.9,
        "response_time_ms": 1000,
        "backup_frequency": "daily",
        "support": "priority",
    },
    "enterprise": {
        "uptime_target": 99.99,
        "response_time_ms": 500,
        "backup_frequency": "hourly",
        "support": "24/7",
    },
}


def generate_sla_policy(
    tier: str = "standard", *, custom_targets: dict | None = None
) -> dict[str, Any]:
    base = SLA_TIERS.get(tier, SLA_TIERS["standard"]).copy()
    if custom_targets:
        base.update(custom_targets)
    return {
        "tier": tier,
        "targets": base,
        "measurement_period": "monthly",
        "exclusions": [
            "Scheduled maintenance windows",
            "Force majeure",
            "Third-party DNS outages",
        ],
        "penalties": {
            "below_target": "Service credit proportional to downtime",
            "notification": "Within 1 hour of incident",
        },
        "reporting": {"frequency": "monthly", "format": "executive_report"},
        "timestamp": datetime.datetime.now().isoformat(),
    }


def compute_uptime(total_minutes: int, downtime_minutes: int) -> dict[str, Any]:
    if total_minutes <= 0:
        return {"error": "Invalid period"}
    uptime_pct = ((total_minutes - downtime_minutes) / total_minutes) * 100
    return {
        "total_minutes": total_minutes,
        "downtime_minutes": downtime_minutes,
        "uptime_minutes": total_minutes - downtime_minutes,
        "uptime_percent": round(uptime_pct, 4),
        "nines": f"{'%.1f' % (2 - (len(str(round(100 - uptime_pct, 4)).rstrip('0').rstrip('.')) - 2) if uptime_pct < 100 else 0)} nines"
        if uptime_pct < 100
        else "100%",
        "equivalent_downtime_per_month": f"{round(downtime_minutes * 30 / max(total_minutes, 1))} min/month",
    }


def generate_sla_report(
    inventory: dict[str, Any],
    *,
    tier: str = "standard",
    downtime_minutes: int = 0,
    period_days: int = 30,
) -> dict[str, Any]:
    policy = generate_sla_policy(tier)
    total_minutes = period_days * 24 * 60
    uptime = compute_uptime(total_minutes, downtime_minutes)
    target = policy["targets"]["uptime_target"]
    compliant = uptime["uptime_percent"] >= target

    services = (
        inventory.get("services", {})
        if isinstance(inventory.get("services"), dict)
        else {}
    )
    running = sum(
        1
        for v in services.values()
        if isinstance(v, dict) and v.get("status") == "running"
    )

    apps = (
        inventory.get("apps", {}).get("apps", [])
        if isinstance(inventory.get("apps"), dict)
        else []
    )
    backups = (
        inventory.get("backups", {}).get("archives", [])
        if isinstance(inventory.get("backups"), dict)
        else []
    )

    return {
        "period_days": period_days,
        "tier": tier,
        "uptime": uptime,
        "target_uptime": target,
        "compliant": compliant,
        "services": {"total": len(services), "running": running},
        "apps_count": len(apps),
        "backups_count": len(backups),
        "recommendations": []
        if compliant
        else [
            "Investigate downtime causes",
            "Consider failover setup",
            "Review monitoring alerting thresholds",
        ],
        "timestamp": datetime.datetime.now().isoformat(),
    }


def list_sla_tiers() -> list[dict[str, Any]]:
    return [{"tier": k, **v} for k, v in SLA_TIERS.items()]


# ── Uptime persistence ────────────────────────────────────────────────

_SLA_STATE_PATH = Path("/opt/nexora/var/sla-data.json")


def record_downtime(
    minutes: int, reason: str = "", state_path: str | None = None
) -> dict[str, Any]:
    """Record a downtime event for SLA tracking."""
    path = Path(state_path) if state_path else _SLA_STATE_PATH
    try:
        data = (
            json.loads(path.read_text())
            if path.exists()
            else {"events": [], "total_downtime_minutes": 0}
        )
    except Exception as exc:
        logger.warning(
            "failed to read SLA state; recreating payload",
            extra={"path": str(path), "error": str(exc)},
        )
        data = {"events": [], "total_downtime_minutes": 0}

    data["events"].append(
        {
            "minutes": minutes,
            "reason": reason,
            "timestamp": datetime.datetime.now().isoformat(),
        }
    )
    data["total_downtime_minutes"] = sum(e["minutes"] for e in data["events"])
    data["last_updated"] = datetime.datetime.now().isoformat()

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return {
        "recorded": True,
        "total_downtime_minutes": data["total_downtime_minutes"],
        "events_count": len(data["events"]),
    }


def get_sla_history(state_path: str | None = None) -> dict[str, Any]:
    """Get historical SLA data."""
    path = Path(state_path) if state_path else _SLA_STATE_PATH
    try:
        return (
            json.loads(path.read_text())
            if path.exists()
            else {"events": [], "total_downtime_minutes": 0}
        )
    except Exception as exc:
        logger.warning(
            "failed to read SLA history; returning empty payload",
            extra={"path": str(path), "error": str(exc)},
        )
        return {"events": [], "total_downtime_minutes": 0}


def compute_sla_from_history(
    period_days: int = 30, tier: str = "standard", state_path: str | None = None
) -> dict[str, Any]:
    """Compute SLA report from persisted downtime data."""
    data = get_sla_history(state_path)
    total_minutes = period_days * 24 * 60
    downtime = data.get("total_downtime_minutes", 0)
    uptime = compute_uptime(total_minutes, downtime)
    target = SLA_TIERS.get(tier, SLA_TIERS["standard"])["uptime_target"]
    return {
        "period_days": period_days,
        "tier": tier,
        "target_uptime": target,
        "uptime": uptime,
        "compliant": uptime["uptime_percent"] >= target,
        "events": data.get("events", [])[-10:],
        "timestamp": datetime.datetime.now().isoformat(),
    }


def compute_downtime_from_events(events: list[dict[str, Any]]) -> int:
    """Compute downtime minutes from start/end style events."""

    total = 0
    for event in events:
        total += int(event.get("minutes", 0) or 0)
    return total
