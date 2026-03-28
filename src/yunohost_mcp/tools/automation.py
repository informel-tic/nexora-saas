"""MCP tools for automation, scheduled jobs and checklists."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP


def register_automation_tools(mcp: FastMCP, settings=None):

    @mcp.tool()
    async def ynh_auto_list_templates() -> str:
        """Liste tous les modèles d'automatisation disponibles."""
        from nexora_saas.automation import list_automation_templates

        return json.dumps(list_automation_templates(), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_auto_generate_plan(profile: str = "standard") -> str:
        """Génère un plan d'automatisation recommandé.
        Args:
            profile: Profil (minimal, standard, professional)
        """
        from nexora_saas.automation import generate_automation_plan

        return json.dumps(generate_automation_plan(profile), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_auto_generate_crontab(profile: str = "standard") -> str:
        """Génère un fichier crontab prêt à déployer.
        Args:
            profile: Profil (minimal, standard, professional)
        """
        from nexora_saas.automation import generate_automation_plan, generate_crontab

        plan = generate_automation_plan(profile)
        crontab = generate_crontab(plan["jobs"])
        return crontab

    @mcp.tool()
    async def ynh_auto_list_checklists() -> str:
        """Liste toutes les checklists disponibles."""
        from nexora_saas.automation import list_checklists

        return json.dumps(list_checklists(), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_auto_get_checklist(checklist_id: str) -> str:
        """Affiche une checklist spécifique.
        Args:
            checklist_id: ID de la checklist (pre_deployment, post_deployment, incident_response, monthly_review)
        """
        from nexora_saas.automation import get_checklist

        return json.dumps(get_checklist(checklist_id), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_auto_install_crontab(profile: str = "standard") -> str:
        """[OPERATOR] Installe le crontab d'automatisation dans /etc/cron.d/.
        Args:
            profile: Profil (minimal, standard, professional)
        """
        from nexora_saas.automation import install_crontab

        return json.dumps(install_crontab(profile), indent=2, ensure_ascii=False)
