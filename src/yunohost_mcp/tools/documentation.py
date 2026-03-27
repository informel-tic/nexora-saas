"""Documentation vivante et exports Markdown/JSON."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from yunohost_mcp.utils.runner import run_shell_command, run_ynh_command
from yunohost_mcp.utils.safety import validate_output_path, validate_positive_int


def _data(result):
    return result.data if result.success else {"error": result.error}


def register_documentation_tools(mcp: FastMCP, settings=None):

    @mcp.tool()
    async def ynh_doc_capability_catalog() -> str:
        """Expose le catalogue canonique des capacités Nexora."""
        from nexora_core.capabilities import capability_catalog_payload

        return json.dumps(capability_catalog_payload(), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_doc_generate_overview() -> str:
        version = await run_ynh_command("--version")
        domains = await run_ynh_command("domain", "list")
        apps = await run_ynh_command("app", "list")
        users = await run_ynh_command("user", "list")
        return "\n".join(
            [
                "# Vue d'ensemble YunoHost",
                "",
                "## Version",
                f"```json\n{json.dumps(_data(version), indent=2, ensure_ascii=False)}\n```",
                "## Domaines",
                f"```json\n{json.dumps(_data(domains), indent=2, ensure_ascii=False)}\n```",
                "## Applications",
                f"```json\n{json.dumps(_data(apps), indent=2, ensure_ascii=False)}\n```",
                "## Utilisateurs",
                f"```json\n{json.dumps(_data(users), indent=2, ensure_ascii=False)}\n```",
            ]
        )

    @mcp.tool()
    async def ynh_doc_apps_inventory() -> str:
        result = await run_ynh_command("app", "list")
        data = _data(result)
        lines = ["# Inventaire des apps", ""]
        for app in data.get("apps", []) if isinstance(data, dict) else []:
            lines.append(f"- **{app.get('name', app.get('id', 'app'))}** — `{app.get('version', 'n/a')}`")
        return "\n".join(lines)

    @mcp.tool()
    async def ynh_doc_domains_inventory() -> str:
        domains = await run_ynh_command("domain", "list")
        certs = await run_ynh_command("domain", "cert", "status")
        return "\n\n".join(
            [
                "# Domaines",
                f"```json\n{json.dumps(_data(domains), indent=2, ensure_ascii=False)}\n```",
                "# Certificats",
                f"```json\n{json.dumps(_data(certs), indent=2, ensure_ascii=False)}\n```",
            ]
        )

    @mcp.tool()
    async def ynh_doc_users_permissions() -> str:
        users = await run_ynh_command("user", "list")
        groups = await run_ynh_command("user", "group", "list", "--full")
        perms = await run_ynh_command("user", "permission", "list", "--full")
        return "\n\n".join(
            [
                "# Utilisateurs / Permissions",
                f"```json\n{json.dumps(_data(users), indent=2, ensure_ascii=False)}\n```",
                f"```json\n{json.dumps(_data(groups), indent=2, ensure_ascii=False)}\n```",
                f"```json\n{json.dumps(_data(perms), indent=2, ensure_ascii=False)}\n```",
            ]
        )

    @mcp.tool()
    async def ynh_doc_services_inventory() -> str:
        result = await run_ynh_command("service", "status")
        return f"# Services\n\n```json\n{json.dumps(_data(result), indent=2, ensure_ascii=False)}\n```"

    @mcp.tool()
    async def ynh_doc_network_map() -> str:
        app_map = await run_ynh_command("app", "map")
        ports = await run_shell_command("ss -tulpen")
        return "\n\n".join(
            [
                "# Schéma réseau logique",
                f"```json\n{json.dumps(_data(app_map), indent=2, ensure_ascii=False)}\n```",
                "## Ports d'écoute",
                f"```text\n{ports}\n```",
            ]
        )

    @mcp.tool()
    async def ynh_doc_pra_runbook() -> str:
        return "\n".join(
            [
                "# Runbook PRA",
                "",
                "1. Vérifier l'accès SSH et l'état réseau.",
                "2. Installer YunoHost sur un système vierge.",
                "3. Rejouer le script de reconstruction généré par le MCP.",
                "4. Restaurer les backups YunoHost.",
                "5. Vérifier DNS, certificats, mail et accès applicatifs.",
                "6. Comparer avec un snapshot PRA récent.",
            ]
        )

    @mcp.tool()
    async def ynh_doc_backup_strategy() -> str:
        backups = await run_ynh_command("backup", "list")
        return "\n\n".join(
            [
                "# Stratégie de sauvegarde",
                f"```json\n{json.dumps(_data(backups), indent=2, ensure_ascii=False)}\n```",
                "Recommandation: backup quotidien, rétention multi-générations, export hors-site et test régulier de restauration.",
            ]
        )

    @mcp.tool()
    async def ynh_doc_security_posture() -> str:
        ssh = await run_shell_command(
            "grep -E '^(Port|PermitRootLogin|PasswordAuthentication)' /etc/ssh/sshd_config 2>/dev/null || true"
        )
        return "\n\n".join(["# Posture sécurité", "## SSH", f"```text\n{ssh}\n```"])

    @mcp.tool()
    async def ynh_doc_changes_from_logs(lines: int = 200) -> str:
        """Affiche les logs système récents.
        Args:
            lines: Nombre de lignes (défaut: 200, max: 2000)
        """
        lines = validate_positive_int(int(lines), "lines", 2000)
        logs = await run_shell_command(f"journalctl -n {lines} --no-pager 2>/dev/null")
        return f"# Changelog approximatif\n\n```text\n{logs}\n```"

    @mcp.tool()
    async def ynh_doc_export_markdown(output_path: str, section: str = "overview") -> str:
        """Exporte la documentation en Markdown.
        Args:
            output_path: Chemin de sortie (redirigé vers /tmp/nexora-export/ si hors zone)
            section: Section à exporter
        """
        generators = {
            "overview": ynh_doc_generate_overview,
            "apps": ynh_doc_apps_inventory,
            "domains": ynh_doc_domains_inventory,
            "users": ynh_doc_users_permissions,
            "services": ynh_doc_services_inventory,
            "network": ynh_doc_network_map,
            "pra": ynh_doc_pra_runbook,
        }
        if section not in generators:
            return f"❌ Section inconnue: {section}"
        safe_path = validate_output_path(output_path)
        content = await generators[section]()
        safe_path.write_text(content, encoding="utf-8")
        return f"✅ Documentation Markdown exportée vers {safe_path}"

    @mcp.tool()
    async def ynh_doc_export_json(output_path: str) -> str:
        """Exporte la documentation complète en JSON.
        Args:
            output_path: Chemin de sortie (redirigé vers /tmp/nexora-export/ si hors zone)
        """
        safe_path = validate_output_path(output_path)
        payload = {
            "version": _data(await run_ynh_command("--version")),
            "domains": _data(await run_ynh_command("domain", "list")),
            "apps": _data(await run_ynh_command("app", "list")),
            "users": _data(await run_ynh_command("user", "list")),
            "services": _data(await run_ynh_command("service", "status")),
        }
        safe_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return f"✅ Documentation JSON exportée vers {safe_path}"
