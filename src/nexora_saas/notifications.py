"""Notification and alerting system: webhooks, email, templates."""

from __future__ import annotations

import datetime
import logging
from typing import Any

logger = logging.getLogger(__name__)

ALERT_LEVELS = {"critical": 0, "high": 1, "warning": 2, "info": 3}

NOTIFICATION_CHANNELS = {
    "webhook": {"description": "HTTP POST to a URL (Slack, Mattermost, n8n, etc.)"},
    "email": {"description": "Email via local Postfix/SMTP"},
    "ntfy": {"description": "Push notification via ntfy.sh"},
    "gotify": {"description": "Push notification via Gotify"},
}

# Pre-built alert templates
ALERT_TEMPLATES = {
    "service_down": {
        "title": "Service {service} arrêté",
        "body": "Le service {service} est arrêté sur {node_id} depuis {since}.",
        "level": "critical",
    },
    "disk_critical": {
        "title": "Disque critique sur {node_id}",
        "body": "Utilisation disque à {percent}% sur {mount}. Seuil: {threshold}%.",
        "level": "critical",
    },
    "cert_expiring": {
        "title": "Certificat {domain} expire bientôt",
        "body": "Le certificat SSL de {domain} expire dans {days} jours.",
        "level": "high" if "{days}" != "" else "warning",
    },
    "backup_missing": {
        "title": "Aucune sauvegarde récente",
        "body": "Le serveur {node_id} n'a pas de sauvegarde depuis {days} jours.",
        "level": "high",
    },
    "failover_triggered": {
        "title": "Failover déclenché pour {app_id}",
        "body": "L'application {app_id} a basculé de {primary} vers {secondary}.",
        "level": "critical",
    },
    "security_score_drop": {
        "title": "Score sécurité en baisse",
        "body": "Le score sécurité de {node_id} est passé de {old_score} à {new_score}.",
        "level": "warning",
    },
    "pra_ready": {
        "title": "Rapport PRA disponible",
        "body": "Le snapshot PRA du {date} est prêt. Score: {score}/100.",
        "level": "info",
    },
    "fleet_drift": {
        "title": "Dérive détectée entre nœuds",
        "body": "Dérive de {drift_count} élément(s) entre {ref_node} et {target_node}.",
        "level": "warning",
    },
}


def format_alert(template_id: str, **kwargs) -> dict[str, Any] | None:
    tpl = ALERT_TEMPLATES.get(template_id)
    if not tpl:
        return None
    return {
        "template": template_id,
        "title": tpl["title"].format(**kwargs),
        "body": tpl["body"].format(**kwargs),
        "level": tpl["level"],
        "timestamp": datetime.datetime.now().isoformat(),
    }


def generate_webhook_payload(alert: dict[str, Any], format: str = "slack") -> dict[str, Any]:
    """Format an alert for a specific webhook target."""
    if format == "slack":
        emoji = {"critical": "🔴", "high": "🟠", "warning": "🟡", "info": "🔵"}.get(alert.get("level", "info"), "ℹ️")
        return {
            "text": f"{emoji} *{alert['title']}*\n{alert['body']}",
            "username": "Nexora",
        }
    elif format == "mattermost":
        return {
            "text": f"#### {alert['title']}\n{alert['body']}",
            "username": "Nexora",
            "icon_url": "",
        }
    elif format == "ntfy":
        priority_map = {"critical": 5, "high": 4, "warning": 3, "info": 2}
        return {
            "topic": "nexora",
            "title": alert["title"],
            "message": alert["body"],
            "priority": priority_map.get(alert.get("level"), 3),
            "tags": [alert.get("level", "info")],
        }
    else:  # generic
        return alert


def generate_notification_config(channels: list[str] | None = None) -> dict[str, Any]:
    """Generate notification routing config."""
    channels = channels or ["webhook"]
    routing = {}
    for level in ALERT_LEVELS:
        routing[level] = channels if level in ("critical", "high") else channels[:1]

    return {
        "channels": {ch: NOTIFICATION_CHANNELS[ch] for ch in channels if ch in NOTIFICATION_CHANNELS},
        "routing": routing,
        "throttle_minutes": 15,
        "digest_mode": False,
        "quiet_hours": {"enabled": False, "start": "22:00", "end": "07:00"},
        "timestamp": datetime.datetime.now().isoformat(),
    }


def list_alert_templates() -> list[dict[str, Any]]:
    return [{"id": k, **v} for k, v in ALERT_TEMPLATES.items()]


# ── Actual sending ────────────────────────────────────────────────────


def send_webhook(url: str, payload: dict[str, Any], *, timeout: int = 10) -> dict[str, Any]:
    """Actually send a webhook HTTP POST."""
    import httpx

    try:
        resp = httpx.post(url, json=payload, timeout=timeout)
        return {
            "success": resp.status_code < 400,
            "status_code": resp.status_code,
            "url": url,
        }
    except Exception as e:
        return {"success": False, "error": str(e), "url": url}


def send_ntfy(
    topic: str,
    title: str,
    message: str,
    *,
    server: str = "https://ntfy.sh",
    priority: int = 3,
) -> dict[str, Any]:
    """Send a push notification via ntfy."""
    import httpx

    try:
        resp = httpx.post(
            f"{server}/{topic}",
            headers={"Title": title, "Priority": str(priority)},
            content=message,
            timeout=10,
        )
        return {
            "success": resp.status_code < 400,
            "status_code": resp.status_code,
            "topic": topic,
        }
    except Exception as e:
        return {"success": False, "error": str(e), "topic": topic}


def send_alert(
    template_id: str,
    channel: str,
    *,
    webhook_url: str = "",
    ntfy_topic: str = "",
    ntfy_server: str = "https://ntfy.sh",
    **kwargs,
) -> dict[str, Any]:
    """Format and send an alert through a channel."""
    alert = format_alert(template_id, **kwargs)
    if not alert:
        return {"success": False, "error": f"Unknown template: {template_id}"}

    if channel == "webhook" and webhook_url:
        payload = generate_webhook_payload(alert, "slack")
        return send_webhook(webhook_url, payload)
    elif channel == "ntfy" and ntfy_topic:
        return send_ntfy(
            ntfy_topic,
            alert["title"],
            alert["body"],
            server=ntfy_server,
            priority={"critical": 5, "high": 4, "warning": 3}.get(alert["level"], 2),
        )
    else:
        return {
            "success": False,
            "error": f"Channel '{channel}' not configured (need webhook_url or ntfy_topic)",
        }


def should_throttle_alert(history: list[dict[str, Any]], template_id: str, *, throttle_minutes: int = 15) -> bool:
    """Return whether an alert should be throttled based on recent history."""

    cutoff = datetime.datetime.now() - datetime.timedelta(minutes=throttle_minutes)
    for item in history:
        if item.get("template") != template_id:
            continue
        try:
            ts = datetime.datetime.fromisoformat(str(item.get("timestamp")))
        except Exception as exc:
            logger.warning("Skipping malformed alert history timestamp: %s", exc)
            continue
        if ts >= cutoff:
            return True
    return False


def record_alert_history(history: list[dict[str, Any]], alert: dict[str, Any]) -> dict[str, Any]:
    """Append an alert to local history."""

    history.append(alert)
    return alert
