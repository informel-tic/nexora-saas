"""Monitoring engine: continuous health surveillance with alerting.

This is the FREE-tier monitoring service that gives Nexora subscribers
something YunoHost alone cannot provide — continuous, automated monitoring
with proactive alerts instead of manual ``yunohost diagnosis`` CLI calls.
"""

from __future__ import annotations

import datetime
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertCategory(str, Enum):
    CERT = "certificate"
    SERVICE = "service"
    DISK = "disk"
    BACKUP = "backup"
    SECURITY = "security"
    HEALTH = "health"


@dataclass(slots=True)
class Alert:
    id: str
    severity: AlertSeverity
    category: AlertCategory
    title: str
    detail: str
    remediation: str
    timestamp: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "severity": self.severity.value,
            "category": self.category.value,
            "title": self.title,
            "detail": self.detail,
            "remediation": self.remediation,
            "timestamp": self.timestamp,
        }


# ── Certificate monitoring ────────────────────────────────────────────

_CERT_THRESHOLDS_DAYS = (30, 14, 7)


def check_certificates(inventory: dict[str, Any]) -> list[Alert]:
    """Analyze certificate inventory and generate alerts for expiring/expired certs."""
    certs = inventory.get("certs", {}).get("certificates", {}) if isinstance(inventory.get("certs"), dict) else {}
    alerts: list[Alert] = []
    for domain, data in certs.items():
        if not isinstance(data, dict):
            continue
        validity = data.get("validity")
        if not isinstance(validity, (int, float)):
            continue

        if validity <= 0:
            alerts.append(
                Alert(
                    id=f"cert-expired-{domain}",
                    severity=AlertSeverity.CRITICAL,
                    category=AlertCategory.CERT,
                    title=f"Certificat expiré: {domain}",
                    detail=f"Le certificat SSL pour {domain} est expiré (validity={validity}).",
                    remediation=f"Renouveler: yunohost domain cert install {domain} --force",
                )
            )
        elif validity <= 7:
            alerts.append(
                Alert(
                    id=f"cert-expiring-7d-{domain}",
                    severity=AlertSeverity.CRITICAL,
                    category=AlertCategory.CERT,
                    title=f"Certificat expire dans {validity}j: {domain}",
                    detail=f"Le certificat SSL pour {domain} expire dans {validity} jours.",
                    remediation=f"Vérifier le renouvellement LE: yunohost domain cert status {domain}",
                )
            )
        elif validity <= 14:
            alerts.append(
                Alert(
                    id=f"cert-expiring-14d-{domain}",
                    severity=AlertSeverity.WARNING,
                    category=AlertCategory.CERT,
                    title=f"Certificat expire dans {validity}j: {domain}",
                    detail=f"Le certificat SSL pour {domain} expire dans {validity} jours.",
                    remediation=f"Vérifier le renouvellement LE: yunohost domain cert status {domain}",
                )
            )
        elif validity <= 30:
            alerts.append(
                Alert(
                    id=f"cert-expiring-30d-{domain}",
                    severity=AlertSeverity.INFO,
                    category=AlertCategory.CERT,
                    title=f"Certificat expire dans {validity}j: {domain}",
                    detail=f"Le certificat pour {domain} expire bientôt — vérifier que Let's Encrypt est actif.",
                    remediation="Vérifier la config LE et le timer de renouvellement.",
                )
            )
    return alerts


# ── Service monitoring ────────────────────────────────────────────────

_CRITICAL_SERVICES = frozenset(
    {
        "nginx",
        "slapd",
        "postfix",
        "dovecot",
        "rspamd",
        "yunohost-api",
        "yunohost-firewall",
        "ssh",
        "dnsmasq",
        "mysql",
        "postgresql",
        "redis-server",
        "fail2ban",
    }
)


def check_services(inventory: dict[str, Any]) -> list[Alert]:
    """Check all services and alert on non-running critical/standard services."""
    services = inventory.get("services", {}) if isinstance(inventory.get("services"), dict) else {}
    alerts: list[Alert] = []
    for svc, info in services.items():
        if not isinstance(info, dict):
            continue
        status = info.get("status", "unknown")
        if status in ("running", "enabled"):
            continue
        is_critical = svc in _CRITICAL_SERVICES
        alerts.append(
            Alert(
                id=f"svc-down-{svc}",
                severity=AlertSeverity.CRITICAL if is_critical else AlertSeverity.WARNING,
                category=AlertCategory.SERVICE,
                title=f"Service {'critique ' if is_critical else ''}arrêté: {svc}",
                detail=f"Le service {svc} est en état '{status}'.",
                remediation=f"Redémarrer: systemctl restart {svc}",
            )
        )
    return alerts


# ── Backup freshness monitoring ───────────────────────────────────────


def check_backup_freshness(inventory: dict[str, Any], *, max_age_days: int = 7) -> list[Alert]:
    """Alert if no recent backup exists within the configured window."""
    backups = inventory.get("backups", {}).get("archives", []) if isinstance(inventory.get("backups"), dict) else []
    alerts: list[Alert] = []
    if not backups:
        alerts.append(
            Alert(
                id="backup-none",
                severity=AlertSeverity.CRITICAL,
                category=AlertCategory.BACKUP,
                title="Aucune sauvegarde détectée",
                detail="Aucune archive de sauvegarde YunoHost n'a été trouvée.",
                remediation="Créer une sauvegarde: yunohost backup create",
            )
        )
        return alerts

    now = datetime.datetime.now(datetime.timezone.utc)
    newest_age_days: float | None = None
    for archive in backups:
        if isinstance(archive, dict):
            ts = archive.get("created_at") or archive.get("timestamp")
            if ts:
                try:
                    created = datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                    age = (now - created).total_seconds() / 86400
                    if newest_age_days is None or age < newest_age_days:
                        newest_age_days = age
                except (ValueError, TypeError):
                    pass

    if newest_age_days is not None and newest_age_days > max_age_days:
        alerts.append(
            Alert(
                id="backup-stale",
                severity=AlertSeverity.WARNING,
                category=AlertCategory.BACKUP,
                title=f"Sauvegarde obsolète ({int(newest_age_days)}j)",
                detail=f"La sauvegarde la plus récente date de {int(newest_age_days)} jours (seuil: {max_age_days}j).",
                remediation="Créer une sauvegarde fraîche: yunohost backup create",
            )
        )

    return alerts


# ── Disk space monitoring ─────────────────────────────────────────────


def check_disk_space(inventory: dict[str, Any], *, threshold_pct: int = 85) -> list[Alert]:
    """Alert on disk usage above threshold based on diagnosis data."""
    diagnosis = inventory.get("diagnosis", {}) if isinstance(inventory.get("diagnosis"), dict) else {}
    alerts: list[Alert] = []
    # YunoHost diagnosis may include disk stats under various keys
    items = diagnosis.get("items", []) if isinstance(diagnosis.get("items"), list) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("category") != "diskusage":
            continue
        for detail in item.get("details", []):
            if not isinstance(detail, dict):
                continue
            usage_pct = detail.get("usage_percent")
            mount = detail.get("mountpoint", "/")
            if isinstance(usage_pct, (int, float)) and usage_pct >= threshold_pct:
                sev = AlertSeverity.CRITICAL if usage_pct >= 95 else AlertSeverity.WARNING
                alerts.append(
                    Alert(
                        id=f"disk-full-{mount.replace('/', '_')}",
                        severity=sev,
                        category=AlertCategory.DISK,
                        title=f"Disque {mount} à {int(usage_pct)}%",
                        detail=f"L'espace disque sur {mount} est à {int(usage_pct)}% (seuil: {threshold_pct}%).",
                        remediation="Libérer de l'espace: supprimer vieux backups, purger logs, ou augmenter le disque.",
                    )
                )
    return alerts


# ── Security posture checks ──────────────────────────────────────────


def check_security_posture(inventory: dict[str, Any]) -> list[Alert]:
    """Generate alerts for security issues found in inventory."""
    alerts: list[Alert] = []

    # Public permissions
    permissions = (
        inventory.get("permissions", {}).get("permissions", {})
        if isinstance(inventory.get("permissions"), dict)
        else {}
    )
    public_perms = [
        name for name, perm in permissions.items() if isinstance(perm, dict) and "visitors" in perm.get("allowed", [])
    ]
    if len(public_perms) > 3:
        alerts.append(
            Alert(
                id="security-many-public-perms",
                severity=AlertSeverity.WARNING,
                category=AlertCategory.SECURITY,
                title=f"{len(public_perms)} permissions publiques détectées",
                detail=f"Permissions ouvertes aux visiteurs: {', '.join(public_perms[:5])}{'...' if len(public_perms) > 5 else ''}",
                remediation="Auditer les permissions: yunohost user permission list --full",
            )
        )

    return alerts


# ── Aggregate monitoring run ──────────────────────────────────────────


def run_monitoring_check(
    inventory: dict[str, Any],
    *,
    max_backup_age_days: int = 7,
    disk_threshold_pct: int = 85,
) -> dict[str, Any]:
    """Run all monitoring checks and return a consolidated report.

    This is the primary entry point — the FREE-tier monitoring service
    that differentiates Nexora from raw YunoHost.
    """
    cert_alerts = check_certificates(inventory)
    svc_alerts = check_services(inventory)
    backup_alerts = check_backup_freshness(inventory, max_age_days=max_backup_age_days)
    disk_alerts = check_disk_space(inventory, threshold_pct=disk_threshold_pct)
    security_alerts = check_security_posture(inventory)

    all_alerts = cert_alerts + svc_alerts + backup_alerts + disk_alerts + security_alerts
    all_dicts = [a.to_dict() for a in all_alerts]

    critical_count = sum(1 for a in all_alerts if a.severity == AlertSeverity.CRITICAL)
    warning_count = sum(1 for a in all_alerts if a.severity == AlertSeverity.WARNING)

    if critical_count > 0:
        overall = "critical"
    elif warning_count > 0:
        overall = "warning"
    else:
        overall = "healthy"

    return {
        "status": overall,
        "alert_count": len(all_alerts),
        "critical_count": critical_count,
        "warning_count": warning_count,
        "info_count": len(all_alerts) - critical_count - warning_count,
        "alerts": all_dicts,
        "checks_performed": [
            "certificates",
            "services",
            "backup_freshness",
            "disk_space",
            "security_posture",
        ],
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


# ── Alert persistence (optional) ─────────────────────────────────────

_ALERT_STATE_PATH = Path("/opt/nexora/var/monitoring-alerts.json")


def persist_alerts(report: dict[str, Any], *, state_path: str | None = None) -> dict[str, Any]:
    """Persist monitoring alerts to disk for historical tracking."""
    path = Path(state_path) if state_path else _ALERT_STATE_PATH
    try:
        existing = json.loads(path.read_text()) if path.exists() else {"history": []}
    except Exception:
        existing = {"history": []}

    entry = {
        "timestamp": report.get("timestamp", datetime.datetime.now(datetime.timezone.utc).isoformat()),
        "status": report.get("status"),
        "alert_count": report.get("alert_count", 0),
        "critical_count": report.get("critical_count", 0),
        "alerts": report.get("alerts", []),
    }
    existing["history"].append(entry)
    # Keep last 1000 entries
    existing["history"] = existing["history"][-1000:]
    existing["last_check"] = entry["timestamp"]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(existing, indent=2, ensure_ascii=False))
    return {"persisted": True, "history_count": len(existing["history"])}
