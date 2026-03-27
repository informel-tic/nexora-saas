"""Monitoring et santé du serveur YunoHost."""

from __future__ import annotations

import shlex

from mcp.server.fastmcp import FastMCP

from yunohost_mcp.utils.runner import format_result, run_shell_command, run_ynh_command
from yunohost_mcp.utils.safety import validate_alphanum, validate_positive_int


def register_monitoring_tools(mcp: FastMCP, settings=None):

    @mcp.tool()
    async def ynh_monitor_resources() -> str:
        """Affiche CPU, mémoire, swap, disque et charge système."""
        return "\n\n".join(
            [
                "=== Ressources système ===",
                await run_shell_command("uptime"),
                await run_shell_command("free -h"),
                await run_shell_command("df -h"),
            ]
        )

    @mcp.tool()
    async def ynh_monitor_services() -> str:
        """Résume l'état des services critiques YunoHost."""
        return format_result(await run_ynh_command("service", "status"))

    @mcp.tool()
    async def ynh_monitor_nginx() -> str:
        """Montre l'état nginx et les erreurs récentes."""
        return "\n\n".join(
            [
                "=== Nginx ===",
                await run_shell_command("systemctl is-active nginx || true"),
                await run_shell_command(
                    "tail -n 40 /var/log/nginx/error.log 2>/dev/null || echo 'Pas de log nginx global'"
                ),
            ]
        )

    @mcp.tool()
    async def ynh_monitor_php_fpm() -> str:
        """Montre l'état des services PHP-FPM."""
        return await run_shell_command(
            "systemctl --type=service --state=running | grep php.*fpm || echo 'Aucun php-fpm détecté'"
        )

    @mcp.tool()
    async def ynh_monitor_db() -> str:
        """Montre l'état des bases MariaDB/MySQL/PostgreSQL."""
        return "\n".join(
            [
                "=== Databases ===",
                await run_shell_command("systemctl is-active mysql 2>/dev/null || true"),
                await run_shell_command("systemctl is-active mariadb 2>/dev/null || true"),
                await run_shell_command("systemctl is-active postgresql 2>/dev/null || true"),
            ]
        )

    @mcp.tool()
    async def ynh_monitor_mail_queue() -> str:
        """Affiche la file d'attente mail Postfix."""
        return await run_shell_command(
            "mailq 2>/dev/null || postqueue -p 2>/dev/null || echo 'Pas de file mail accessible'"
        )

    @mcp.tool()
    async def ynh_monitor_ssl() -> str:
        """Affiche le statut des certificats SSL/TLS."""
        return format_result(await run_ynh_command("domain", "cert", "status"))

    @mcp.tool()
    async def ynh_monitor_backups() -> str:
        """Affiche l'état des sauvegardes et leur ancienneté."""
        return "\n\n".join(
            [
                format_result(await run_ynh_command("backup", "list")),
                await run_shell_command("ls -lht /home/yunohost.backup/archives 2>/dev/null | head -n 20"),
            ]
        )

    @mcp.tool()
    async def ynh_monitor_fail2ban() -> str:
        """Résume l'activité récente de Fail2Ban."""
        return await run_shell_command("fail2ban-client status 2>/dev/null || echo 'Fail2Ban indisponible'")

    @mcp.tool()
    async def ynh_monitor_ports() -> str:
        """Liste les ports d'écoute et les processus associés."""
        return await run_shell_command("ss -tulpen")

    @mcp.tool()
    async def ynh_monitor_logs_search(pattern: str, lines: int = 40) -> str:
        """Recherche un motif dans les logs système récents.
        Args:
            pattern: Motif à rechercher (alphanumérique)
            lines: Nombre de lignes max (défaut: 40, max: 500)
        """
        validate_alphanum(pattern, "search pattern")
        lines = validate_positive_int(int(lines), "lines", 500)
        fetch_lines = lines * 5
        cmd = f"journalctl -n {fetch_lines} --no-pager 2>/dev/null | grep -i {shlex.quote(pattern)} | tail -n {lines}"
        return await run_shell_command(cmd)

    @mcp.tool()
    async def ynh_monitor_incidents_summary() -> str:
        """Produit un résumé rapide des signaux faibles à surveiller."""
        return "\n\n".join(
            [
                "=== Résumé incidents ===",
                "Services en échec:\n" + await run_shell_command("systemctl --failed --no-legend 2>/dev/null || true"),
                "Logs récents niveau err:\n"
                + await run_shell_command("journalctl -p err -n 20 --no-pager 2>/dev/null || true"),
            ]
        )
