"""MCP tools for migration between deployment types."""

from __future__ import annotations

import json
from mcp.server.fastmcp import FastMCP


def register_migration_tools(mcp: FastMCP, settings=None):

    @mcp.tool()
    async def ynh_migrate_docker_to_ynh(image: str, app_name: str) -> str:
        """Génère une checklist de migration Docker → package YunoHost.
        Args:
            image: Image Docker source (ex: ghcr.io/org/app:latest)
            app_name: Nom du futur package YNH
        """
        from nexora_core.migration import docker_to_ynh_checklist

        return json.dumps(
            docker_to_ynh_checklist(image, app_name), indent=2, ensure_ascii=False
        )

    @mcp.tool()
    async def ynh_migrate_ynh_to_docker(app_id: str) -> str:
        """Génère un Dockerfile squelette à partir d'une app YunoHost.
        Args:
            app_id: Identifiant de l'app YunoHost
        """
        from nexora_core.migration import ynh_to_docker_export
        from yunohost_mcp.utils.runner import run_ynh_command

        r = await run_ynh_command("app", "info", app_id)
        info = r.data if r.success and isinstance(r.data, dict) else {"id": app_id}
        return json.dumps(ynh_to_docker_export(info), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_migrate_plan(source_type: str, target_type: str, apps: str) -> str:
        """Génère un plan de migration complet entre types de déploiement.
        Args:
            source_type: Type source (yunohost, docker, bare_metal, external)
            target_type: Type cible
            apps: Noms d'apps séparés par des virgules
        """
        from nexora_core.migration import generate_migration_plan

        app_list = [a.strip() for a in apps.split(",")]
        return json.dumps(
            generate_migration_plan(source_type, target_type, app_list),
            indent=2,
            ensure_ascii=False,
        )
