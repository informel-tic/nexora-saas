"""Outils MCP pour le Plan de Reprise d'Activité (PRA) YunoHost."""

import datetime
import json

from mcp.server.fastmcp import FastMCP

from yunohost_mcp.utils.runner import format_result, run_shell_command, run_ynh_command
from yunohost_mcp.utils.safety import validate_name, validate_output_path


def register_pra_tools(mcp: FastMCP, settings=None):

    @mcp.tool()
    async def ynh_pra_snapshot() -> str:
        """Crée un snapshot complet de la configuration du serveur YunoHost."""
        snapshot = {
            "pra_version": "1.0",
            "timestamp": datetime.datetime.now().isoformat(),
            "type": "yunohost_pra_snapshot",
        }
        for key, cmd in [
            ("version", ["--version"]),
            ("domains", ["domain", "list"]),
            ("main_domain", ["domain", "main-domain"]),
            ("apps", ["app", "list"]),
            ("app_map", ["app", "map"]),
            ("users", ["user", "list"]),
            ("groups", ["user", "group", "list", "--full"]),
            ("permissions", ["user", "permission", "list", "--full"]),
            ("settings", ["settings", "list"]),
            ("certificates", ["domain", "cert", "status"]),
            ("firewall", ["firewall", "list"]),
            ("services", ["service", "status"]),
            ("backups", ["backup", "list"]),
        ]:
            result = await run_ynh_command(*cmd)
            if result.success:
                snapshot[key] = result.data
        return json.dumps(snapshot, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_pra_generate_rebuild_script() -> str:
        """Génère un script bash de reconstruction du serveur YunoHost.
        Les mots de passe sont remplacés par des placeholders à renseigner manuellement."""
        lines = [
            "#!/bin/bash",
            f"# Script de reconstruction YunoHost - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "set -euo pipefail",
            'echo "=== Début de la reconstruction YunoHost ==="',
            "",
            "# IMPORTANT: Remplacez les mots de passe ci-dessous avant exécution.",
            "# Ne transmettez JAMAIS ce script avec des mots de passe en clair.",
            "",
        ]

        result = await run_ynh_command("domain", "list")
        if result.success and isinstance(result.data, dict):
            domains = result.data.get("domains", [])
            main_r = await run_ynh_command("domain", "main-domain")
            main_d = (
                str(main_r.data.get("current_main_domain", ""))
                if main_r.success and isinstance(main_r.data, dict)
                else ""
            )
            lines.append("# --- DOMAINES ---")
            for d in domains:
                if d != main_d:
                    lines.append(f"yunohost domain add {d} || true")
            lines.append("")
            lines.append("# --- CERTIFICATS ---")
            for d in domains:
                lines.append(f"yunohost domain cert install {d} --no-checks || true")
            lines.append("")

        result = await run_ynh_command("user", "list")
        if result.success and isinstance(result.data, dict):
            lines.append("# --- UTILISATEURS ---")
            lines.append("# ATTENTION: Remplacez __PASSWORD_xxx__ par de vrais mots de passe sécurisés")
            for username, info in result.data.get("users", {}).items():
                fullname = info.get("fullname", username)
                mail = info.get("mail", "")
                domain = mail.split("@")[1] if "@" in mail else ""
                lines.append(
                    f"yunohost user create {username}"
                    f' --fullname "{fullname}"'
                    f" --domain {domain}"
                    f' --password "__PASSWORD_{username}__"'
                    f" || true"
                )
            lines.append("")

        result = await run_ynh_command("app", "list")
        if result.success and isinstance(result.data, dict):
            lines.append("# --- APPLICATIONS ---")
            for app in result.data.get("apps", []):
                aid = app.get("id", "")
                label = app.get("label", "")
                dp = app.get("domain_path", "")
                if dp:
                    parts = dp.split("/", 1)
                    dom, pth = parts[0], "/" + parts[1] if len(parts) > 1 else "/"
                else:
                    dom, pth = "DOMAINE_A_DEFINIR", "/"
                lines.append(f'yunohost app install {aid} --args "domain={dom}&path={pth}" --label "{label}" || true')
            lines.append("")

        lines.extend(
            [
                'echo "=== Reconstruction terminée ==="',
                'echo "Prochaines étapes: restaurer les backups, changer les mots de passe, vérifier DNS"',
            ]
        )
        return "\n".join(lines)

    @mcp.tool()
    async def ynh_pra_check_readiness() -> str:
        """Vérifie que le serveur est prêt pour un PRA."""
        report = [
            f"=== RAPPORT PRA - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} ===",
            "",
        ]
        issues = []

        backup_r = await run_ynh_command("backup", "list")
        if backup_r.success and isinstance(backup_r.data, dict):
            archives = backup_r.data.get("archives", [])
            report.append(f"💾 Sauvegardes: {len(archives)} archive(s)")
            if not archives:
                issues.append("CRITIQUE: Aucune sauvegarde !")
        else:
            issues.append("CRITIQUE: Impossible de lister les sauvegardes")

        app_r = await run_ynh_command("app", "list")
        if app_r.success and isinstance(app_r.data, dict):
            apps = [a.get("id") for a in app_r.data.get("apps", [])]
            report.append(f"📦 Applications: {', '.join(apps)}")

        report.append(f"\n💽 Espace disque:\n{await run_shell_command('df -h / /home')}")

        svc_r = await run_ynh_command("service", "status")
        if svc_r.success and isinstance(svc_r.data, dict):
            report.append("\n🔧 Services:")
            for svc, info in svc_r.data.items():
                st = info.get("status", "?") if isinstance(info, dict) else "?"
                icon = "✅" if st == "running" else "⚠️"
                report.append(f"  {icon} {svc}: {st}")
                if st != "running":
                    issues.append(f"Service {svc} est {st}")

        report.append("\n=== RÉSUMÉ ===")
        if issues:
            report.append(f"⚠️  {len(issues)} problème(s):")
            for i in issues:
                report.append(f"  - {i}")
        else:
            report.append("✅ Serveur prêt pour un PRA.")
        return "\n".join(report)

    @mcp.tool()
    async def ynh_pra_export_config(
        output_path: str = "/tmp/nexora-export/ynh_pra_config.json",  # nosec B108
    ) -> str:
        """Exporte la configuration PRA dans un fichier JSON.
        Args:
            output_path: Chemin de sortie (redirigé si hors zone autorisée)
        """
        safe_path = validate_output_path(output_path)
        snapshot_json = await ynh_pra_snapshot()
        safe_path.write_text(snapshot_json, encoding="utf-8")
        return f"✅ Configuration PRA exportée vers {safe_path}"

    @mcp.tool()
    async def ynh_pra_full_backup(name: str = "") -> str:
        """Lance un backup complet (système + toutes les apps) pour le PRA.
        Args:
            name: Nom du backup (défaut: pra_YYYYMMDD_HHMM)
        """
        if not name:
            name = f"pra_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}"
        else:
            validate_name(name, "backup name")
        result = await run_ynh_command(
            "backup",
            "create",
            "--name",
            name,
            "--description",
            f"Backup PRA - {datetime.datetime.now().isoformat()}",
            timeout=3600,
        )
        return f"{'✅' if result.success else '❌'} Backup PRA '{name}': {format_result(result)}"
