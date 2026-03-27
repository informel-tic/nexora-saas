"""Drift detection: compare desired state vs actual inventory to find configuration drift.

PRO-tier feature — YunoHost has no concept of desired state management.
Nexora tracks snapshots and detects when reality diverges from the recorded baseline.
"""

from __future__ import annotations

import datetime
from typing import Any


# ── Section-level diff helpers ────────────────────────────────────────


def _diff_lists(
    label: str, baseline: list[Any], current: list[Any]
) -> list[dict[str, Any]]:
    """Diff two lists and return added/removed items."""
    bl_set = set(str(i) for i in baseline)
    cur_set = set(str(i) for i in current)
    drifts: list[dict[str, Any]] = []
    for item in cur_set - bl_set:
        drifts.append({
            "section": label,
            "type": "added",
            "item": item,
            "severity": "info",
        })
    for item in bl_set - cur_set:
        drifts.append({
            "section": label,
            "type": "removed",
            "item": item,
            "severity": "warning",
        })
    return drifts


def _diff_dicts(
    label: str, baseline: dict[str, Any], current: dict[str, Any]
) -> list[dict[str, Any]]:
    """Diff two dicts and return added/removed/changed keys."""
    drifts: list[dict[str, Any]] = []
    all_keys = set(baseline.keys()) | set(current.keys())
    for key in sorted(all_keys):
        if key not in baseline:
            drifts.append({
                "section": label,
                "type": "added",
                "key": key,
                "current_value": _summarize(current[key]),
                "severity": "info",
            })
        elif key not in current:
            drifts.append({
                "section": label,
                "type": "removed",
                "key": key,
                "baseline_value": _summarize(baseline[key]),
                "severity": "warning",
            })
        elif baseline[key] != current[key]:
            drifts.append({
                "section": label,
                "type": "changed",
                "key": key,
                "baseline_value": _summarize(baseline[key]),
                "current_value": _summarize(current[key]),
                "severity": "warning",
            })
    return drifts


def _summarize(value: Any, max_len: int = 80) -> Any:
    """Produce a safe summary of a value for drift reports."""
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    s = str(value)
    return s[:max_len] + "…" if len(s) > max_len else s


# ── Section extractors ────────────────────────────────────────────────


def _extract_app_ids(inventory: dict[str, Any]) -> list[str]:
    apps = inventory.get("apps", {})
    if isinstance(apps, dict):
        app_list = apps.get("apps", [])
    else:
        app_list = []
    return sorted(
        a.get("id", a.get("name", str(a))) if isinstance(a, dict) else str(a)
        for a in app_list
    )


def _extract_domains(inventory: dict[str, Any]) -> list[str]:
    domains = inventory.get("domains", {})
    if isinstance(domains, dict):
        return sorted(domains.get("domains", []))
    return []


def _extract_services_status(inventory: dict[str, Any]) -> dict[str, str]:
    services = inventory.get("services", {})
    if not isinstance(services, dict):
        return {}
    return {
        svc: info.get("status", "unknown") if isinstance(info, dict) else "unknown"
        for svc, info in services.items()
    }


def _extract_permissions(inventory: dict[str, Any]) -> dict[str, Any]:
    perms = inventory.get("permissions", {})
    if isinstance(perms, dict) and "permissions" in perms:
        return perms["permissions"]
    return perms if isinstance(perms, dict) else {}


# ── Main drift detection ─────────────────────────────────────────────


def detect_drift(
    baseline_inventory: dict[str, Any],
    current_inventory: dict[str, Any],
) -> dict[str, Any]:
    """Compare a baseline inventory snapshot against the current state.

    Returns a structured drift report with per-section analysis.
    """
    drifts: list[dict[str, Any]] = []

    # Apps drift
    bl_apps = _extract_app_ids(baseline_inventory)
    cur_apps = _extract_app_ids(current_inventory)
    drifts.extend(_diff_lists("apps", bl_apps, cur_apps))

    # Domains drift
    bl_domains = _extract_domains(baseline_inventory)
    cur_domains = _extract_domains(current_inventory)
    drifts.extend(_diff_lists("domains", bl_domains, cur_domains))

    # Services drift
    bl_services = _extract_services_status(baseline_inventory)
    cur_services = _extract_services_status(current_inventory)
    drifts.extend(_diff_dicts("services", bl_services, cur_services))

    # Permissions drift
    bl_perms = _extract_permissions(baseline_inventory)
    cur_perms = _extract_permissions(current_inventory)
    drifts.extend(_diff_dicts("permissions", bl_perms, cur_perms))

    # Classify severity
    critical_count = sum(1 for d in drifts if d.get("severity") == "critical")
    warning_count = sum(1 for d in drifts if d.get("severity") == "warning")

    if not drifts:
        status = "in_sync"
    elif critical_count > 0:
        status = "critical_drift"
    elif warning_count > 0:
        status = "drifted"
    else:
        status = "minor_drift"

    return {
        "status": status,
        "drift_count": len(drifts),
        "critical_count": critical_count,
        "warning_count": warning_count,
        "drifts": drifts,
        "sections_checked": ["apps", "domains", "services", "permissions"],
        "remediation": _remediation_suggestions(drifts),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def detect_drift_from_state(
    state: dict[str, Any],
    current_inventory: dict[str, Any],
) -> dict[str, Any]:
    """Detect drift using the most recent inventory snapshot from persisted state."""
    snapshots = state.get("inventory_snapshots", [])
    if not snapshots:
        return {
            "status": "no_baseline",
            "drift_count": 0,
            "message": "No inventory baseline found. Run inventory/refresh first to establish a baseline.",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

    latest = snapshots[-1]
    baseline = latest.get("inventory", {})
    result = detect_drift(baseline, current_inventory)
    result["baseline_timestamp"] = latest.get("timestamp")
    result["snapshots_available"] = len(snapshots)
    return result


# ── Trend tracking ────────────────────────────────────────────────────


def compute_drift_trend(
    state: dict[str, Any],
    current_inventory: dict[str, Any],
    *,
    max_comparisons: int = 10,
) -> dict[str, Any]:
    """Compute drift trend across historical snapshots.

    Shows whether drift is increasing, stable, or improving over time.
    """
    snapshots = state.get("inventory_snapshots", [])
    if len(snapshots) < 2:
        return {
            "trend": "insufficient_data",
            "message": "Need at least 2 snapshots for trend analysis.",
            "snapshots_available": len(snapshots),
        }

    recent = snapshots[-max_comparisons:]
    data_points: list[dict[str, Any]] = []

    for snapshot in recent:
        baseline = snapshot.get("inventory", {})
        result = detect_drift(baseline, current_inventory)
        data_points.append({
            "timestamp": snapshot.get("timestamp"),
            "drift_count": result["drift_count"],
            "status": result["status"],
        })

    counts = [dp["drift_count"] for dp in data_points]
    if len(counts) >= 2:
        if counts[-1] > counts[-2]:
            trend = "increasing"
        elif counts[-1] < counts[-2]:
            trend = "improving"
        else:
            trend = "stable"
    else:
        trend = "stable"

    return {
        "trend": trend,
        "data_points": data_points,
        "current_drift_count": counts[-1] if counts else 0,
        "snapshots_analyzed": len(data_points),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


# ── Remediation suggestions ──────────────────────────────────────────


def _remediation_suggestions(drifts: list[dict[str, Any]]) -> list[str]:
    suggestions: list[str] = []
    seen: set[str] = set()

    for d in drifts:
        section = d.get("section", "")
        dtype = d.get("type", "")
        key = f"{section}-{dtype}"
        if key in seen:
            continue
        seen.add(key)

        if section == "apps" and dtype == "removed":
            suggestions.append("Applications supprimées détectées — vérifier si c'est intentionnel ou restaurer depuis backup.")
        elif section == "apps" and dtype == "added":
            suggestions.append("Nouvelles applications détectées — mettre à jour le baseline avec inventory/refresh.")
        elif section == "services" and dtype == "changed":
            suggestions.append("État des services modifié — vérifier les services arrêtés avec systemctl status.")
        elif section == "permissions" and dtype == "changed":
            suggestions.append("Permissions modifiées — auditer avec yunohost user permission list.")
        elif section == "domains" and dtype == "removed":
            suggestions.append("Domaines supprimés — vérifier la configuration DNS et les certificats.")
        elif section == "domains" and dtype == "added":
            suggestions.append("Nouveaux domaines — configurer les certificats SSL et mettre à jour le baseline.")

    if not suggestions and drifts:
        suggestions.append("Exécuter inventory/refresh pour mettre à jour le baseline après validation des changements.")

    return suggestions
