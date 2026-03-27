"""Outils MCP pour l'administration système YunoHost."""

from mcp.server.fastmcp import FastMCP

from yunohost_mcp.utils.runner import format_result, run_shell_command, run_ynh_command


def register_system_tools(mcp: FastMCP, settings=None):

    @mcp.tool()
    async def ynh_diagnosis_run() -> str:
        """Lance un diagnostic complet du serveur YunoHost."""
        result = await run_ynh_command("diagnosis", "run", timeout=120)
        return format_result(result)

    @mcp.tool()
    async def ynh_diagnosis_show() -> str:
        """Affiche les résultats du dernier diagnostic."""
        result = await run_ynh_command("diagnosis", "show", "--full")
        return format_result(result)

    @mcp.tool()
    async def ynh_service_status(service: str = "") -> str:
        """Vérifie le statut des services (nginx, postfix, etc).
        Args:
            service: Nom du service (vide = tous)
        """
        cmd = ["service", "status"]
        if service:
            cmd.append(service)
        result = await run_ynh_command(*cmd)
        return format_result(result)

    @mcp.tool()
    async def ynh_service_restart(service: str) -> str:
        """Redémarre un service.
        Args:
            service: Nom du service (ex: nginx, postfix, mysql)
        """
        result = await run_ynh_command("service", "restart", service)
        return format_result(result)

    @mcp.tool()
    async def ynh_service_log(service: str, lines: int = 50) -> str:
        """Affiche les dernières lignes de log d'un service.
        Args:
            service: Nom du service
            lines: Nombre de lignes (défaut: 50)
        """
        result = await run_ynh_command("service", "log", service, "--number", str(lines), json_output=False)
        return format_result(result)

    @mcp.tool()
    async def ynh_firewall_list() -> str:
        """Liste les règles du firewall YunoHost (ports ouverts)."""
        result = await run_ynh_command("firewall", "list")
        return format_result(result)

    @mcp.tool()
    async def ynh_settings_list() -> str:
        """Liste tous les paramètres globaux de YunoHost."""
        result = await run_ynh_command("settings", "list")
        return format_result(result)

    @mcp.tool()
    async def ynh_system_update() -> str:
        """Vérifie les mises à jour disponibles (système et apps)."""
        result = await run_ynh_command("tools", "update")
        return format_result(result)

    @mcp.tool()
    async def ynh_system_upgrade(apps: bool = False, system: bool = False) -> str:
        """Applique les mises à jour. ATTENTION : opération risquée.
        Args:
            apps: Mettre à jour les applications
            system: Mettre à jour le système
        """
        cmd = ["tools", "upgrade"]
        if apps:
            cmd.append("--apps")
        if system:
            cmd.append("--system")
        if not apps and not system:
            return "❌ Spécifie apps=True et/ou system=True pour confirmer."
        result = await run_ynh_command(*cmd, timeout=1800)
        return format_result(result)

    @mcp.tool()
    async def ynh_version() -> str:
        """Affiche la version de YunoHost et de ses composants."""
        result = await run_ynh_command("--version")
        return format_result(result)

    @mcp.tool()
    async def ynh_disk_usage() -> str:
        """Affiche l'utilisation disque du serveur."""
        return await run_shell_command("df -h")
