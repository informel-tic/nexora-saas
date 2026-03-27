"""Outils MCP pour la gestion des sauvegardes YunoHost."""

import shlex

from mcp.server.fastmcp import FastMCP

from yunohost_mcp.utils.runner import (
    format_result,
    run_shell_command_safe,
    run_ynh_command,
)
from yunohost_mcp.utils.safety import validate_name


def register_backup_tools(mcp: FastMCP, settings=None):

    @mcp.tool()
    async def ynh_backup_list() -> str:
        """Liste toutes les sauvegardes disponibles sur le serveur YunoHost."""
        result = await run_ynh_command("backup", "list")
        return format_result(result)

    @mcp.tool()
    async def ynh_backup_info(name: str) -> str:
        """Affiche les détails d'une sauvegarde spécifique.
        Args:
            name: Nom de l'archive de sauvegarde
        """
        validate_name(name, "backup name")
        result = await run_ynh_command("backup", "info", name)
        return format_result(result)

    @mcp.tool()
    async def ynh_backup_create(name: str = "", description: str = "", apps: str = "", system: str = "") -> str:
        """Crée une sauvegarde YunoHost.
        Args:
            name: Nom de l'archive (optionnel, auto-généré si vide)
            description: Description de la sauvegarde
            apps: Apps à sauvegarder séparées par espaces (vide = toutes)
            system: Parties système séparées par espaces (vide = toutes)
        """
        cmd = ["backup", "create"]
        if name:
            validate_name(name, "backup name")
            cmd.extend(["--name", name])
        if description:
            cmd.extend(["--description", description])
        if apps:
            cmd.extend(["--apps"] + apps.split())
        if system:
            cmd.extend(["--system"] + system.split())
        result = await run_ynh_command(*cmd, timeout=1800)
        return format_result(result)

    @mcp.tool()
    async def ynh_backup_restore(name: str, apps: str = "", system: str = "") -> str:
        """Restaure une sauvegarde. ATTENTION : opération destructive.
        Args:
            name: Nom de l'archive à restaurer
            apps: Apps spécifiques à restaurer (vide = toutes)
            system: Parties système à restaurer (vide = toutes)
        """
        validate_name(name, "backup name")
        cmd = ["backup", "restore", name]
        if apps:
            cmd.extend(["--apps"] + apps.split())
        if system:
            cmd.extend(["--system"] + system.split())
        result = await run_ynh_command(*cmd, timeout=3600)
        return format_result(result)

    @mcp.tool()
    async def ynh_backup_delete(name: str) -> str:
        """Supprime une archive de sauvegarde.
        Args:
            name: Nom de l'archive à supprimer
        """
        validate_name(name, "backup name")
        result = await run_ynh_command("backup", "delete", name)
        return format_result(result)

    @mcp.tool()
    async def ynh_backup_verify(name: str) -> str:
        """Vérifie l'intégrité d'une sauvegarde (contenu, dumps SQL, taille).
        Args:
            name: Nom de l'archive à vérifier
        """
        validate_name(name, "backup name")
        archive_path = f"/home/yunohost.backup/archives/{name}.tar"

        ls_out = await run_shell_command_safe(["ls", "-lh", archive_path])
        tar_count = await run_shell_command_safe(
            ["bash", "-c", f"tar -tvf {shlex.quote(archive_path)} 2>/dev/null | wc -l"]
        )
        sql_out = await run_shell_command_safe(
            [
                "bash",
                "-c",
                f"tar -tvf {shlex.quote(archive_path)} 2>/dev/null | grep -i sql || echo 'Aucun dump SQL'",
            ]
        )
        info_result = await run_ynh_command("backup", "info", name)

        return f"""=== Vérification backup: {name} ===
Taille: {ls_out}
Fichiers: {tar_count}
Dumps SQL: {sql_out}

Info YunoHost:
{format_result(info_result)}"""
