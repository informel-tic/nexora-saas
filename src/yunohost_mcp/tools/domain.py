"""Outils MCP pour la gestion des domaines YunoHost."""

from mcp.server.fastmcp import FastMCP
from yunohost_mcp.utils.runner import run_ynh_command, format_result


def register_domain_tools(mcp: FastMCP, settings=None):

    @mcp.tool()
    async def ynh_domain_list() -> str:
        """Liste tous les domaines configurés sur le serveur YunoHost."""
        result = await run_ynh_command("domain", "list")
        return format_result(result)

    @mcp.tool()
    async def ynh_domain_info(domain: str) -> str:
        """Affiche les informations d'un domaine (certificat, apps, DNS).
        Args:
            domain: Le nom de domaine
        """
        result = await run_ynh_command("domain", "info", domain)
        return format_result(result)

    @mcp.tool()
    async def ynh_domain_add(domain: str) -> str:
        """Ajoute un nouveau domaine au serveur YunoHost.
        Args:
            domain: Le nom de domaine à ajouter
        """
        result = await run_ynh_command("domain", "add", domain)
        return format_result(result)

    @mcp.tool()
    async def ynh_domain_remove(domain: str) -> str:
        """Supprime un domaine du serveur.
        Args:
            domain: Le nom de domaine à supprimer
        """
        result = await run_ynh_command("domain", "remove", domain)
        return format_result(result)

    @mcp.tool()
    async def ynh_domain_main(domain: str = "") -> str:
        """Affiche ou définit le domaine principal du serveur.
        Args:
            domain: Nouveau domaine principal (vide = afficher l'actuel)
        """
        cmd = ["domain", "main-domain"]
        if domain:
            cmd.extend(["--new-main-domain", domain])
        result = await run_ynh_command(*cmd)
        return format_result(result)

    @mcp.tool()
    async def ynh_domain_cert_status(domain: str = "") -> str:
        """Vérifie le statut des certificats SSL/TLS.
        Args:
            domain: Domaine spécifique (vide = tous)
        """
        cmd = ["domain", "cert", "status"]
        if domain:
            cmd.append(domain)
        result = await run_ynh_command(*cmd)
        return format_result(result)

    @mcp.tool()
    async def ynh_domain_cert_install(domain: str) -> str:
        """Installe ou renouvelle un certificat Let's Encrypt.
        Args:
            domain: Le domaine pour le certificat
        """
        result = await run_ynh_command("domain", "cert", "install", domain)
        return format_result(result)

    @mcp.tool()
    async def ynh_domain_dns_suggest(domain: str) -> str:
        """Affiche la configuration DNS recommandée pour un domaine.
        Args:
            domain: Le nom de domaine
        """
        result = await run_ynh_command("domain", "dns", "suggest", domain)
        return format_result(result)
