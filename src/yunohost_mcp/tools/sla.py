"""MCP tools for SLA monitoring and reporting."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from yunohost_mcp.utils.runner import run_ynh_command


def register_sla_tools(mcp: FastMCP, settings=None):

    @mcp.tool()
    async def ynh_sla_list_tiers() -> str:
        """Liste les niveaux de SLA disponibles (basic, standard, professional, enterprise)."""
        from nexora_saas.sla import list_sla_tiers

        return json.dumps(list_sla_tiers(), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_sla_generate_policy(tier: str = "standard") -> str:
        """Génère une politique SLA complète.
        Args:
            tier: Niveau (basic, standard, professional, enterprise)
        """
        from nexora_saas.sla import generate_sla_policy

        return json.dumps(generate_sla_policy(tier), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_sla_report(tier: str = "standard", downtime_minutes: int = 0, period_days: int = 30) -> str:
        """Génère un rapport SLA avec calcul d'uptime.
        Args:
            tier: Niveau SLA cible
            downtime_minutes: Minutes de downtime observées
            period_days: Période en jours
        """
        from nexora_saas.sla import generate_sla_report

        inv = {}
        for key, cmd in [
            ("services", ["service", "status"]),
            ("apps", ["app", "list"]),
            ("backups", ["backup", "list"]),
        ]:
            r = await run_ynh_command(*cmd)
            inv[key] = r.data if r.success else {}
        return json.dumps(
            generate_sla_report(
                inv,
                tier=tier,
                downtime_minutes=downtime_minutes,
                period_days=period_days,
            ),
            indent=2,
            ensure_ascii=False,
        )

    @mcp.tool()
    async def ynh_sla_compute_uptime(total_minutes: int, downtime_minutes: int) -> str:
        """Calcule le pourcentage d'uptime et les métriques associées.
        Args:
            total_minutes: Minutes totales de la période
            downtime_minutes: Minutes de downtime
        """
        from nexora_saas.sla import compute_uptime

        return json.dumps(
            compute_uptime(total_minutes, downtime_minutes),
            indent=2,
            ensure_ascii=False,
        )

    @mcp.tool()
    async def ynh_sla_record_downtime(minutes: int, reason: str = "") -> str:
        """[OPERATOR] Enregistre un événement de downtime pour le suivi SLA.
        Args:
            minutes: Durée du downtime en minutes
            reason: Raison
        """
        from nexora_saas.sla import record_downtime

        return json.dumps(record_downtime(int(minutes), reason), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_sla_history() -> str:
        """Affiche l'historique des downtimes enregistrés."""
        from nexora_saas.sla import get_sla_history

        return json.dumps(get_sla_history(), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_sla_report_from_history(tier: str = "standard", period_days: int = 30) -> str:
        """Génère un rapport SLA à partir des données historiques persistées.
        Args:
            tier: Niveau SLA cible
            period_days: Période en jours
        """
        from nexora_saas.sla import compute_sla_from_history

        return json.dumps(
            compute_sla_from_history(int(period_days), tier),
            indent=2,
            ensure_ascii=False,
        )
