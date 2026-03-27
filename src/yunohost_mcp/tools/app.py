"""
Outils MCP pour la gestion des applications YunoHost.
"""

import json

from mcp.server.fastmcp import FastMCP
from nexora_core.app_profiles import (
    AppProfileError,
    list_app_profiles,
    resolve_app_profile,
)
from nexora_core.preflight import build_install_preflight
from yunohost_mcp.utils.runner import run_ynh_command, format_result


def register_app_tools(mcp: FastMCP, settings=None):

    @mcp.tool()
    async def ynh_app_install_profiles() -> str:
        """Liste les profils d'installation automatisée supportés par Nexora."""
        return json.dumps(list_app_profiles(), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_app_install_profile(app: str) -> str:
        """Affiche le profil d'installation automatisée Nexora pour une app.

        Args:
            app: Identifiant de l'application (ex: nextcloud, wordpress)
        """
        try:
            return json.dumps(resolve_app_profile(app), indent=2, ensure_ascii=False)
        except AppProfileError as exc:
            return f"❌ {exc}"

    @mcp.tool()
    async def ynh_app_install_preflight(
        app: str, domain: str, path: str = "/", args: str = ""
    ) -> str:
        """Préflight bloquant avant une installation automatisée d'application.

        Args:
            app: Identifiant de l'application
            domain: Domaine cible
            path: Chemin URL cible
            args: Arguments supplémentaires (format: "key=value&key2=value2")
        """
        return json.dumps(
            build_install_preflight(app, domain, path, args),
            indent=2,
            ensure_ascii=False,
        )

    @mcp.tool()
    async def ynh_app_list() -> str:
        """Liste toutes les applications installées sur YunoHost avec leur version et statut."""
        result = await run_ynh_command("app", "list")
        return format_result(result)

    @mcp.tool()
    async def ynh_app_info(app: str) -> str:
        """Affiche les informations détaillées d'une application installée.

        Args:
            app: Identifiant de l'application (ex: nextcloud, wordpress)
        """
        result = await run_ynh_command("app", "info", app)
        return format_result(result)

    @mcp.tool()
    async def ynh_app_install(
        app: str,
        domain: str,
        path: str = "/",
        label: str = "",
        args: str = "",
    ) -> str:
        """Installe une application YunoHost.

        Args:
            app: Nom ou URL de l'application à installer
            domain: Domaine sur lequel installer l'app
            path: Chemin URL (ex: / ou /app)
            label: Nom affiché pour l'application
            args: Arguments supplémentaires (format: "key=value&key2=value2")
        """
        preflight = build_install_preflight(app, domain, path, args)
        if not preflight.get("allowed"):
            return json.dumps(preflight, indent=2, ensure_ascii=False)

        request = (
            preflight.get("normalized_request", {})
            if isinstance(preflight.get("normalized_request"), dict)
            else {}
        )
        install_args = f"domain={preflight['domain']}&path={preflight['path']}"
        if request.get("args_string"):
            install_args += f"&{request['args_string']}"

        cmd = ["app", "install", app, "--args", install_args]
        if label:
            cmd.extend(["--label", label])

        result = await run_ynh_command(*cmd, timeout=600)
        payload = {
            "profile": preflight.get("profile"),
            "warnings": preflight.get("warnings", []),
            "preflight": preflight,
            "result": format_result(result),
        }
        return json.dumps(payload, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_app_remove(app: str) -> str:
        """Désinstalle une application. ATTENTION : les données de l'app seront supprimées.

        Args:
            app: Identifiant de l'application à supprimer
        """
        result = await run_ynh_command("app", "remove", app)
        return format_result(result)

    @mcp.tool()
    async def ynh_app_upgrade(app: str = "") -> str:
        """Met à jour une ou toutes les applications.

        Args:
            app: Identifiant de l'app (vide = mettre à jour toutes les apps)
        """
        cmd = ["app", "upgrade"]
        if app:
            cmd.append(app)
        result = await run_ynh_command(*cmd, timeout=900)
        return format_result(result)

    @mcp.tool()
    async def ynh_app_config_get(app: str, key: str = "") -> str:
        """Récupère la configuration d'une application.

        Args:
            app: Identifiant de l'application
            key: Clé de configuration spécifique (vide = toute la config)
        """
        cmd = ["app", "config", "get", app]
        if key:
            cmd.append(key)
        result = await run_ynh_command(*cmd)
        return format_result(result)

    @mcp.tool()
    async def ynh_app_config_set(app: str, key: str, value: str) -> str:
        """Modifie la configuration d'une application.

        Args:
            app: Identifiant de l'application
            key: Clé de configuration
            value: Nouvelle valeur
        """
        result = await run_ynh_command(
            "app", "config", "set", app, key, "--value", value
        )
        return format_result(result)

    @mcp.tool()
    async def ynh_app_map() -> str:
        """Affiche la carte des applications : quel domaine, quel chemin, quelle app.
        Essentiel pour documenter l'architecture du serveur et préparer un PRA."""
        result = await run_ynh_command("app", "map")
        return format_result(result)

    @mcp.tool()
    async def ynh_app_catalog() -> str:
        """Liste les applications disponibles dans le catalogue YunoHost."""
        result = await run_ynh_command("app", "catalog")
        return format_result(result)
