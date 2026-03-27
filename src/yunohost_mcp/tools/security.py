"""Outils MCP pour l'audit de sécurité et le hardening YunoHost."""

from mcp.server.fastmcp import FastMCP

from yunohost_mcp.utils.runner import (
    format_result,
    run_shell_command,
    run_shell_command_safe,
    run_ynh_command,
)
from yunohost_mcp.utils.safety import validate_alphanum, validate_ip


def register_security_tools(mcp: FastMCP, settings=None):

    @mcp.tool()
    async def ynh_security_audit() -> str:
        """Lance un audit de sécurité complet du serveur YunoHost."""
        report = ["=== AUDIT DE SÉCURITÉ YUNOHOST ===", ""]
        issues = []
        warnings = []

        report.append("--- Ports ouverts (netstat) ---")
        ports = await run_shell_command("ss -tlnp | grep LISTEN")
        report.append(ports)
        report.append("")

        report.append("--- Firewall YunoHost ---")
        fw = await run_ynh_command("firewall", "list")
        if fw.success:
            report.append(format_result(fw))
        report.append("")

        report.append("--- Configuration SSH ---")
        ssh_root = await run_shell_command("grep -i '^PermitRootLogin' /etc/ssh/sshd_config || echo 'Non défini'")
        ssh_port = await run_shell_command("grep -i '^Port ' /etc/ssh/sshd_config || echo 'Port 22 (défaut)'")
        ssh_passwd = await run_shell_command(
            "grep -i '^PasswordAuthentication' /etc/ssh/sshd_config || echo 'Non défini'"
        )
        report.append(f"  Root login: {ssh_root}")
        report.append(f"  Port SSH: {ssh_port}")
        report.append(f"  Auth par mot de passe: {ssh_passwd}")
        if "yes" in ssh_root.lower():
            warnings.append("SSH: PermitRootLogin est activé")
        if "22" in ssh_port:
            warnings.append("SSH: Port par défaut (22)")
        report.append("")

        report.append("--- Fail2Ban ---")
        f2b_status = await run_shell_command("fail2ban-client status 2>/dev/null || echo 'Fail2Ban non disponible'")
        report.append(f2b_status)
        f2b_banned = await run_shell_command("fail2ban-client status sshd 2>/dev/null | grep 'Banned' || echo ''")
        if f2b_banned:
            report.append(f"  SSH: {f2b_banned}")
        report.append("")

        report.append("--- Mises à jour ---")
        updates = await run_shell_command("apt list --upgradable 2>/dev/null | grep -c upgradable || echo '0'")
        report.append(f"  Paquets à mettre à jour: {updates}")
        if updates.strip() not in ("0", ""):
            try:
                if int(updates.strip()) > 10:
                    issues.append(f"{updates.strip()} paquets système en attente de mise à jour")
            except ValueError:
                warnings.append(f"Impossible d'interpréter le nombre de mises à jour: {updates.strip()}")
        report.append("")

        report.append("--- Permissions des applications ---")
        perms = await run_ynh_command("user", "permission", "list", "--full")
        if perms.success and isinstance(perms.data, dict):
            for perm_name, perm_info in perms.data.get("permissions", {}).items():
                if isinstance(perm_info, dict):
                    allowed = perm_info.get("allowed", [])
                    if "visitors" in allowed and "admin" not in perm_name:
                        warnings.append(f"App '{perm_name}' accessible aux visiteurs anonymes")
        report.append(format_result(perms) if perms.success else "Non disponible")
        report.append("")

        report.append("--- Certificats SSL ---")
        certs = await run_ynh_command("domain", "cert", "status")
        if certs.success:
            report.append(format_result(certs))
        report.append("")

        report.append("=== RÉSUMÉ SÉCURITÉ ===")
        if issues:
            report.append(f"🔴 {len(issues)} problème(s) critique(s) :")
            for i in issues:
                report.append(f"  - {i}")
        if warnings:
            report.append(f"🟡 {len(warnings)} avertissement(s) :")
            for w in warnings:
                report.append(f"  - {w}")
        if not issues and not warnings:
            report.append("🟢 Aucun problème de sécurité majeur détecté.")

        return "\n".join(report)

    @mcp.tool()
    async def ynh_security_fail2ban_status() -> str:
        """Affiche le statut complet de Fail2Ban : jails actives, IPs bannies, stats."""
        report = ["=== Fail2Ban Status ===", ""]
        status = await run_shell_command("fail2ban-client status 2>/dev/null")
        report.append(status)
        report.append("")
        jails = await run_shell_command(
            "fail2ban-client status 2>/dev/null | grep 'Jail list' | sed 's/.*://;s/,/\\n/g' | tr -d ' '"
        )
        for jail in jails.strip().split("\n"):
            jail = jail.strip()
            if jail:
                validate_alphanum(jail, "jail name")
                detail = await run_shell_command_safe(["fail2ban-client", "status", jail])
                report.append(f"--- Jail: {jail} ---")
                report.append(detail)
                report.append("")
        return "\n".join(report)

    @mcp.tool()
    async def ynh_security_fail2ban_ban(ip: str, jail: str = "sshd") -> str:
        """Bannit manuellement une adresse IP via Fail2Ban.
        Args:
            ip: Adresse IP à bannir
            jail: Nom du jail (défaut: sshd)
        """
        validate_ip(ip)
        validate_alphanum(jail, "jail name")
        result = await run_shell_command_safe(["fail2ban-client", "set", jail, "banip", ip])
        return f"Ban IP {ip} sur jail {jail}: {result}"

    @mcp.tool()
    async def ynh_security_fail2ban_unban(ip: str, jail: str = "sshd") -> str:
        """Débannit une adresse IP de Fail2Ban.
        Args:
            ip: Adresse IP à débannir
            jail: Nom du jail (défaut: sshd)
        """
        validate_ip(ip)
        validate_alphanum(jail, "jail name")
        result = await run_shell_command_safe(["fail2ban-client", "set", jail, "unbanip", ip])
        return f"Unban IP {ip} sur jail {jail}: {result}"

    @mcp.tool()
    async def ynh_security_open_ports() -> str:
        """Liste tous les ports ouverts sur le serveur avec les processus associés."""
        return await run_shell_command("ss -tlnp | column -t")

    @mcp.tool()
    async def ynh_security_recent_logins() -> str:
        """Affiche les connexions SSH récentes (dernières 24h)."""
        report = ["=== Connexions récentes ===", ""]
        last = await run_shell_command("last -n 20 --time-format iso")
        report.append(last)
        report.append("")
        report.append("--- Tentatives échouées ---")
        failed = await run_shell_command("lastb -n 20 --time-format iso 2>/dev/null || echo 'Non disponible'")
        report.append(failed)
        return "\n".join(report)

    @mcp.tool()
    async def ynh_security_permissions_audit() -> str:
        """Audit des permissions : vérifie que chaque app a des permissions appropriées."""
        report = ["=== Audit des permissions ===", ""]
        issues = []
        perms = await run_ynh_command("user", "permission", "list", "--full")
        if not perms.success:
            return f"❌ Impossible de lire les permissions: {perms.error}"
        if isinstance(perms.data, dict):
            for perm_name, perm_info in perms.data.get("permissions", {}).items():
                if not isinstance(perm_info, dict):
                    continue
                allowed = perm_info.get("allowed", [])
                url = perm_info.get("url", "")
                if "visitors" in allowed:
                    public_ok = any(x in perm_name for x in ["my_webapp", "site", "blog", "wiki.main"])
                    if not public_ok:
                        issues.append(f"⚠️  {perm_name} est accessible aux visiteurs anonymes (URL: {url})")
                        report.append(f"  ⚠️  {perm_name}: PUBLIC ({', '.join(allowed)})")
                    else:
                        report.append(f"  ✅ {perm_name}: public (normal)")
                else:
                    report.append(f"  🔒 {perm_name}: restreint à {', '.join(allowed)}")
        report.append("")
        if issues:
            report.append(f"⚠️  {len(issues)} permission(s) à vérifier :")
            for i in issues:
                report.append(f"  {i}")
        else:
            report.append("✅ Toutes les permissions semblent correctes.")
        return "\n".join(report)

    @mcp.tool()
    async def ynh_security_check_updates() -> str:
        """Vérifie les mises à jour de sécurité disponibles (système + apps)."""
        report = ["=== Mises à jour de sécurité ===", ""]
        report.append("--- Paquets système ---")
        apt_out = await run_shell_command("apt list --upgradable 2>/dev/null | head -20")
        report.append(apt_out if apt_out else "Aucune mise à jour disponible")
        report.append("")
        report.append("--- Applications YunoHost ---")
        ynh_updates = await run_ynh_command("tools", "update")
        if ynh_updates.success:
            report.append(format_result(ynh_updates))
        report.append("")
        return "\n".join(report)
