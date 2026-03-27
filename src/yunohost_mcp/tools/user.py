"""Outils MCP pour la gestion des utilisateurs et groupes YunoHost."""

from mcp.server.fastmcp import FastMCP

from yunohost_mcp.utils.runner import format_result, run_ynh_command


def register_user_tools(mcp: FastMCP, settings=None):

    @mcp.tool()
    async def ynh_user_list() -> str:
        """Liste tous les utilisateurs YunoHost avec leurs infos (email, groupes)."""
        result = await run_ynh_command("user", "list")
        return format_result(result)

    @mcp.tool()
    async def ynh_user_info(username: str) -> str:
        """Affiche les informations détaillées d'un utilisateur.
        Args:
            username: Nom d'utilisateur
        """
        result = await run_ynh_command("user", "info", username)
        return format_result(result)

    @mcp.tool()
    async def ynh_user_create(username: str, fullname: str, domain: str, password: str) -> str:
        """Crée un nouvel utilisateur YunoHost.
        Args:
            username: Nom d'utilisateur (login)
            fullname: Nom complet (ex: "Jean Dupont")
            domain: Domaine pour l'email
            password: Mot de passe
        """
        result = await run_ynh_command(
            "user",
            "create",
            username,
            "--fullname",
            fullname,
            "--domain",
            domain,
            "--password",
            password,
        )
        return format_result(result)

    @mcp.tool()
    async def ynh_user_delete(username: str, purge: bool = False) -> str:
        """Supprime un utilisateur YunoHost.
        Args:
            username: Nom d'utilisateur à supprimer
            purge: Si True, supprime aussi les données
        """
        cmd = ["user", "delete", username]
        if purge:
            cmd.append("--purge")
        result = await run_ynh_command(*cmd)
        return format_result(result)

    @mcp.tool()
    async def ynh_user_update(username: str, fullname: str = "", password: str = "") -> str:
        """Modifie un utilisateur existant.
        Args:
            username: Nom d'utilisateur
            fullname: Nouveau nom complet
            password: Nouveau mot de passe
        """
        cmd = ["user", "update", username]
        if fullname:
            cmd.extend(["--fullname", fullname])
        if password:
            cmd.extend(["--change-password", password])
        result = await run_ynh_command(*cmd)
        return format_result(result)

    @mcp.tool()
    async def ynh_user_group_list() -> str:
        """Liste tous les groupes d'utilisateurs."""
        result = await run_ynh_command("user", "group", "list", "--full")
        return format_result(result)

    @mcp.tool()
    async def ynh_user_permission_list() -> str:
        """Liste toutes les permissions (quelle app est accessible par quel groupe)."""
        result = await run_ynh_command("user", "permission", "list", "--full")
        return format_result(result)
