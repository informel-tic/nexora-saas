"""MCP tools for business blueprints: deploy, preview, validate, estimate."""

from __future__ import annotations

import json
from mcp.server.fastmcp import FastMCP
from yunohost_mcp.utils.runner import run_ynh_command, format_result


# Resource estimates per common app
_APP_RESOURCES = {
    "nextcloud": {
        "ram_mb": 512,
        "disk_mb": 2000,
        "description": "Cloud, fichiers, agenda, contacts",
    },
    "roundcube": {"ram_mb": 128, "disk_mb": 200, "description": "Webmail"},
    "vaultwarden": {
        "ram_mb": 64,
        "disk_mb": 100,
        "description": "Gestionnaire de mots de passe",
    },
    "wordpress": {"ram_mb": 256, "disk_mb": 500, "description": "CMS / site web"},
    "wikijs": {"ram_mb": 256, "disk_mb": 300, "description": "Wiki collaboratif"},
    "wekan": {
        "ram_mb": 256,
        "disk_mb": 300,
        "description": "Gestion de projets / Kanban",
    },
    "gitlab": {"ram_mb": 2048, "disk_mb": 5000, "description": "Forge logicielle"},
    "matrix-synapse": {
        "ram_mb": 512,
        "disk_mb": 1000,
        "description": "Messagerie instantanée",
    },
    "jitsi": {"ram_mb": 1024, "disk_mb": 500, "description": "Visioconférence"},
    "borg": {"ram_mb": 128, "disk_mb": 100, "description": "Sauvegarde déportée"},
    "rspamd": {"ram_mb": 256, "disk_mb": 200, "description": "Anti-spam"},
    "hedgedoc": {
        "ram_mb": 256,
        "disk_mb": 300,
        "description": "Éditeur collaboratif Markdown",
    },
    "mattermost": {"ram_mb": 512, "disk_mb": 500, "description": "Messagerie d'équipe"},
    "limesurvey": {
        "ram_mb": 128,
        "disk_mb": 200,
        "description": "Sondages / questionnaires",
    },
    "peertube": {"ram_mb": 1024, "disk_mb": 10000, "description": "Plateforme vidéo"},
}


def register_blueprint_tools(mcp: FastMCP, settings=None):

    @mcp.tool()
    async def ynh_blueprint_list() -> str:
        """Liste tous les blueprints métier disponibles."""
        from nexora_core.blueprints import load_blueprints
        from pathlib import Path

        bps = load_blueprints(Path("/opt/nexora") / "blueprints")
        if not bps:
            bps = load_blueprints(Path(__file__).resolve().parents[3] / "blueprints")
        return json.dumps([bp.model_dump() for bp in bps], indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_blueprint_preview(slug: str) -> str:
        """Affiche le détail d'un blueprint métier.
        Args:
            slug: Identifiant du blueprint (pme, msp, agency, collective, training)
        """
        from nexora_core.blueprints import load_blueprints
        from pathlib import Path

        bps = load_blueprints(Path("/opt/nexora") / "blueprints")
        if not bps:
            bps = load_blueprints(Path(__file__).resolve().parents[3] / "blueprints")
        bp = next((b for b in bps if b.slug == slug), None)
        if not bp:
            return f"❌ Blueprint '{slug}' non trouvé. Disponibles: {[b.slug for b in bps]}"
        return json.dumps(bp.model_dump(), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_blueprint_resolve_plan(slug: str, domain: str) -> str:
        """Résout un blueprint en plan d'installation exécutable avec préflights par app.
        Args:
            slug: Identifiant du blueprint
            domain: Domaine principal
        """
        from nexora_core.blueprints import load_blueprints, resolve_blueprint_plan
        from pathlib import Path

        bps = load_blueprints(Path("/opt/nexora") / "blueprints")
        if not bps:
            bps = load_blueprints(Path(__file__).resolve().parents[3] / "blueprints")
        bp = next((b for b in bps if b.slug == slug), None)
        if not bp:
            return f"❌ Blueprint '{slug}' non trouvé. Disponibles: {[b.slug for b in bps]}"
        return json.dumps(
            resolve_blueprint_plan(bp, domain), indent=2, ensure_ascii=False
        )

    @mcp.tool()
    async def ynh_blueprint_validate_prereqs(slug: str) -> str:
        """Vérifie si le serveur remplit les prérequis d'un blueprint.
        Args:
            slug: Identifiant du blueprint
        """
        from nexora_core.blueprints import load_blueprints
        from pathlib import Path

        bps = load_blueprints(Path("/opt/nexora") / "blueprints")
        if not bps:
            bps = load_blueprints(Path(__file__).resolve().parents[3] / "blueprints")
        bp = next((b for b in bps if b.slug == slug), None)
        if not bp:
            return f"❌ Blueprint '{slug}' non trouvé."

        issues: list[str] = []
        warnings: list[str] = []

        # Check disk
        from yunohost_mcp.utils.runner import run_shell_command

        disk = await run_shell_command("df -m / | tail -1 | awk '{print $4}'")
        try:
            free_mb = int(disk.strip())
            needed = sum(
                _APP_RESOURCES.get(a, {}).get("disk_mb", 500)
                for a in bp.recommended_apps
            )
            if free_mb < needed:
                issues.append(
                    f"Espace disque insuffisant: {free_mb}MB libre, {needed}MB nécessaire"
                )
        except ValueError:
            warnings.append("Impossible de vérifier l'espace disque")

        # Check existing apps
        result = await run_ynh_command("app", "list")
        existing = set()
        if result.success and isinstance(result.data, dict):
            for a in result.data.get("apps", []):
                existing.add(a.get("id", ""))
        already = existing & set(bp.recommended_apps)
        if already:
            warnings.append(f"Apps déjà installées: {', '.join(already)}")

        to_install = set(bp.recommended_apps) - existing

        return json.dumps(
            {
                "blueprint": slug,
                "apps_to_install": sorted(to_install),
                "apps_already_installed": sorted(already),
                "issues": issues,
                "warnings": warnings,
                "ready": len(issues) == 0,
            },
            indent=2,
            ensure_ascii=False,
        )

    @mcp.tool()
    async def ynh_blueprint_estimate_resources(slug: str) -> str:
        """Estime les ressources nécessaires pour un blueprint.
        Args:
            slug: Identifiant du blueprint
        """
        from nexora_core.blueprints import load_blueprints
        from pathlib import Path

        bps = load_blueprints(Path("/opt/nexora") / "blueprints")
        if not bps:
            bps = load_blueprints(Path(__file__).resolve().parents[3] / "blueprints")
        bp = next((b for b in bps if b.slug == slug), None)
        if not bp:
            return f"❌ Blueprint '{slug}' non trouvé."

        total_ram = 0
        total_disk = 0
        app_details = []
        for app_id in bp.recommended_apps:
            res = _APP_RESOURCES.get(
                app_id, {"ram_mb": 256, "disk_mb": 500, "description": "App YunoHost"}
            )
            total_ram += res["ram_mb"]
            total_disk += res["disk_mb"]
            app_details.append({"app": app_id, **res})

        return json.dumps(
            {
                "blueprint": slug,
                "apps": app_details,
                "total_ram_mb": total_ram,
                "total_disk_mb": total_disk,
                "recommended_ram_gb": max(2, (total_ram + 512) // 1024 + 1),
                "recommended_disk_gb": max(20, total_disk // 1024 + 10),
            },
            indent=2,
            ensure_ascii=False,
        )

    @mcp.tool()
    async def ynh_blueprint_generate_topology(slug: str, domain: str) -> str:
        """Génère la topologie réseau pour un blueprint sur un domaine.
        Args:
            slug: Identifiant du blueprint
            domain: Domaine principal
        """
        from nexora_core.blueprints import load_blueprints
        from pathlib import Path

        bps = load_blueprints(Path("/opt/nexora") / "blueprints")
        if not bps:
            bps = load_blueprints(Path(__file__).resolve().parents[3] / "blueprints")
        bp = next((b for b in bps if b.slug == slug), None)
        if not bp:
            return f"❌ Blueprint '{slug}' non trouvé."

        from nexora_core.blueprints import resolve_blueprint_plan

        plan = resolve_blueprint_plan(bp, domain)
        topology = {
            "blueprint": slug,
            "domain": domain,
            "subdomains": [f"{sub}.{domain}" for sub in bp.subdomains],
            "apps_mapping": plan.get("topology", []),
            "status": plan.get("status"),
            "warnings": plan.get("warnings", []),
        }
        return json.dumps(topology, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_blueprint_generate_security_policy(slug: str) -> str:
        """Génère la politique de sécurité recommandée pour un blueprint.
        Args:
            slug: Identifiant du blueprint
        """
        from nexora_core.blueprints import load_blueprints
        from pathlib import Path

        bps = load_blueprints(Path("/opt/nexora") / "blueprints")
        if not bps:
            bps = load_blueprints(Path(__file__).resolve().parents[3] / "blueprints")
        bp = next((b for b in bps if b.slug == slug), None)
        if not bp:
            return f"❌ Blueprint '{slug}' non trouvé."

        return json.dumps(
            {
                "blueprint": slug,
                "security_baseline": bp.security_baseline,
                "monitoring_baseline": bp.monitoring_baseline,
                "pra_baseline": bp.pra_baseline,
                "recommendations": [
                    "Activer HTTPS forcé sur tous les domaines",
                    "Restreindre l'accès admin aux IP de confiance",
                    "Configurer Fail2Ban",
                    "Mettre en place des sauvegardes quotidiennes",
                    "Revoir les permissions mensuellement",
                ],
            },
            indent=2,
            ensure_ascii=False,
        )

    @mcp.tool()
    async def ynh_blueprint_generate_pra_plan(slug: str) -> str:
        """Génère un plan PRA adapté à un blueprint.
        Args:
            slug: Identifiant du blueprint
        """
        from nexora_core.blueprints import load_blueprints
        from pathlib import Path

        bps = load_blueprints(Path("/opt/nexora") / "blueprints")
        if not bps:
            bps = load_blueprints(Path(__file__).resolve().parents[3] / "blueprints")
        bp = next((b for b in bps if b.slug == slug), None)
        if not bp:
            return f"❌ Blueprint '{slug}' non trouvé."

        return json.dumps(
            {
                "blueprint": slug,
                "pra_baseline": bp.pra_baseline,
                "recovery_steps": [
                    "1. Provisionner un nouveau serveur Debian 12",
                    "2. Installer YunoHost",
                    f"3. Restaurer les domaines: {', '.join(bp.subdomains)}",
                    f"4. Réinstaller les apps: {', '.join(bp.recommended_apps)}",
                    "5. Restaurer les données depuis les backups",
                    "6. Vérifier les certificats et DNS",
                    "7. Tester l'accès à chaque application",
                    "8. Valider les permissions utilisateurs",
                ],
                "rto_estimate": "4-8 heures",
                "rpo_estimate": "Dernière sauvegarde (idéalement < 24h)",
            },
            indent=2,
            ensure_ascii=False,
        )

    @mcp.tool()
    async def ynh_blueprint_deploy(slug: str, domain: str) -> str:
        """Déploie un blueprint métier : installe les apps recommandées.
        ATTENTION : opération modifiante.
        Args:
            slug: Identifiant du blueprint
            domain: Domaine principal
        """
        from nexora_core.blueprints import load_blueprints
        from pathlib import Path

        bps = load_blueprints(Path("/opt/nexora") / "blueprints")
        if not bps:
            bps = load_blueprints(Path(__file__).resolve().parents[3] / "blueprints")
        bp = next((b for b in bps if b.slug == slug), None)
        if not bp:
            return f"❌ Blueprint '{slug}' non trouvé."

        from nexora_core.blueprints import resolve_blueprint_plan

        plan = resolve_blueprint_plan(bp, domain)
        if not plan.get("allowed"):
            return json.dumps(plan, indent=2, ensure_ascii=False)

        results = []
        for step in plan.get("app_plans", []):
            r = await run_ynh_command(
                "app",
                "install",
                step["app"],
                "--args",
                f"domain={step['target_domain']}&path={step['target_path']}",
                timeout=600,
            )
            results.append(
                {
                    "app": step["app"],
                    "domain": step["target_domain"],
                    "path": step["target_path"],
                    "success": r.success,
                    "message": format_result(r)[:200],
                }
            )

        ok = sum(1 for r in results if r["success"])
        return json.dumps(
            {
                "blueprint": slug,
                "domain": domain,
                "plan": plan,
                "results": results,
                "summary": f"{ok}/{len(results)} apps installées avec succès",
            },
            indent=2,
            ensure_ascii=False,
        )
