"""MCP tools for notifications and alerting."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP


def register_notification_tools(mcp: FastMCP, settings=None):

    @mcp.tool()
    async def ynh_notify_list_templates() -> str:
        """Liste tous les modèles d'alertes disponibles."""
        from nexora_core.notifications import list_alert_templates

        return json.dumps(list_alert_templates(), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_notify_preview_alert(template_id: str) -> str:
        """Prévisualise une alerte avec des données d'exemple.
        Args:
            template_id: ID du template (service_down, disk_critical, cert_expiring, etc.)
        """
        from nexora_core.notifications import format_alert

        examples = {
            "service_down": {"service": "nginx", "node_id": "srv1", "since": "10 min"},
            "disk_critical": {
                "node_id": "srv1",
                "percent": "95",
                "mount": "/",
                "threshold": "85",
            },
            "cert_expiring": {"domain": "example.com", "days": "7"},
            "backup_missing": {"node_id": "srv1", "days": "3"},
            "failover_triggered": {
                "app_id": "nextcloud",
                "primary": "srv1",
                "secondary": "srv2",
            },
        }
        params = examples.get(template_id, {"node_id": "srv1"})
        alert = format_alert(template_id, **params)
        if not alert:
            return f"❌ Template '{template_id}' non trouvé."
        return json.dumps(alert, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_notify_generate_webhook(template_id: str, format: str = "slack") -> str:
        """Génère le payload webhook pour une alerte.
        Args:
            template_id: ID du template d'alerte
            format: Format cible (slack, mattermost, ntfy, generic)
        """
        from nexora_core.notifications import format_alert, generate_webhook_payload

        examples = {"service_down": {"service": "nginx", "node_id": "srv1", "since": "10 min"}}
        params = examples.get(template_id, {"node_id": "srv1"})
        alert = format_alert(template_id, **params)
        if not alert:
            return "❌ Template non trouvé."
        payload = generate_webhook_payload(alert, format)
        return json.dumps(payload, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_notify_generate_config(channels: str = "webhook") -> str:
        """Génère une configuration de notification (routing, throttle, quiet hours).
        Args:
            channels: Canaux séparés par virgules (webhook, email, ntfy, gotify)
        """
        from nexora_core.notifications import generate_notification_config

        ch_list = [c.strip() for c in channels.split(",")]
        return json.dumps(generate_notification_config(ch_list), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_notify_send_webhook(template_id: str, webhook_url: str) -> str:
        """[OPERATOR] Envoie une alerte via webhook (Slack, Mattermost, etc.).
        Args:
            template_id: ID du template d'alerte
            webhook_url: URL du webhook
        """
        from nexora_core.notifications import send_alert

        examples = {
            "service_down": {
                "service": "nginx",
                "node_id": "local",
                "since": "maintenant",
            }
        }
        params = examples.get(template_id, {"node_id": "local"})
        result = send_alert(template_id, "webhook", webhook_url=webhook_url, **params)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_notify_send_ntfy(template_id: str, topic: str, server: str = "https://ntfy.sh") -> str:
        """[OPERATOR] Envoie une notification push via ntfy.
        Args:
            template_id: ID du template d'alerte
            topic: Topic ntfy
            server: Serveur ntfy (défaut: ntfy.sh)
        """
        from nexora_core.notifications import send_alert

        examples = {
            "service_down": {
                "service": "nginx",
                "node_id": "local",
                "since": "maintenant",
            }
        }
        params = examples.get(template_id, {"node_id": "local"})
        result = send_alert(template_id, "ntfy", ntfy_topic=topic, ntfy_server=server, **params)
        return json.dumps(result, indent=2, ensure_ascii=False)
