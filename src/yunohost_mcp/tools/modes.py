"""MCP tools for runtime mode management, escalation and confirmation."""

from __future__ import annotations

import json
from mcp.server.fastmcp import FastMCP
from yunohost_mcp.utils.safety import validate_alphanum


def register_mode_tools(mcp: FastMCP, settings=None):

    @mcp.tool()
    async def ynh_mode_current() -> str:
        """Affiche le mode opérationnel actuel et ses capacités."""
        from nexora_core.modes import get_mode_manager

        mm = get_mode_manager()
        return json.dumps(mm.get_mode_info(), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_mode_list() -> str:
        """Liste tous les modes disponibles avec leurs capacités."""
        from nexora_core.modes import list_modes

        return json.dumps(list_modes(), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_mode_switch(target_mode: str, reason: str = "") -> str:
        """Change le mode opérationnel (observer, operator, architect, admin).
        Args:
            target_mode: Mode cible
            reason: Raison du changement
        """
        validate_alphanum(target_mode, "mode")
        from nexora_core.modes import get_mode_manager

        mm = get_mode_manager()
        result = mm.switch_mode(target_mode, reason=reason, operator="mcp")
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_mode_escalate(
        target_mode: str, duration_minutes: int = 60, reason: str = ""
    ) -> str:
        """Crée un token d'escalation temporaire vers un mode supérieur.
        Args:
            target_mode: Mode cible temporaire
            duration_minutes: Durée en minutes (défaut: 60, max: 480)
            reason: Raison de l'escalation
        """
        validate_alphanum(target_mode, "mode")
        duration = min(max(int(duration_minutes), 5), 480) * 60
        from nexora_core.modes import get_mode_manager

        mm = get_mode_manager()
        result = mm.create_escalation_token(
            target_mode, duration_seconds=duration, reason=reason
        )
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_mode_list_escalations() -> str:
        """Liste les tokens d'escalation actifs."""
        from nexora_core.modes import get_mode_manager

        mm = get_mode_manager()
        return json.dumps(mm.list_escalation_tokens(), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_mode_history() -> str:
        """Affiche l'historique des changements de mode."""
        from nexora_core.modes import get_mode_manager

        mm = get_mode_manager()
        info = mm.get_mode_info()
        return json.dumps(
            {"current": info["mode"], "history": info["history"]},
            indent=2,
            ensure_ascii=False,
        )

    @mcp.tool()
    async def ynh_mode_pending_confirmations() -> str:
        """Liste les actions en attente de confirmation."""
        from nexora_core.modes import list_pending_confirmations

        pending = list_pending_confirmations()
        if not pending:
            return "Aucune action en attente de confirmation."
        return json.dumps(pending, indent=2, ensure_ascii=False)

    # ── Operator actions ──────────────────────────────────────────────

    @mcp.tool()
    async def ynh_op_restart_service(service: str) -> str:
        """[OPERATOR] Redémarre un service YunoHost.
        Args:
            service: Nom du service
        """
        validate_alphanum(service, "service")
        from nexora_core.modes import get_mode_manager

        mm = get_mode_manager()
        if not mm.require_mode("operator"):
            return f"❌ Mode actuel: {mm.current_mode}. Nécessite au minimum: operator."
        from nexora_core.operator_actions import restart_service

        return json.dumps(restart_service(service), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_op_create_backup(name: str = "", description: str = "") -> str:
        """[OPERATOR] Crée une sauvegarde YunoHost.
        Args:
            name: Nom (optionnel)
            description: Description
        """
        from nexora_core.modes import get_mode_manager

        mm = get_mode_manager()
        if not mm.require_mode("operator"):
            return f"❌ Mode actuel: {mm.current_mode}. Nécessite: operator."
        from nexora_core.operator_actions import create_backup

        return json.dumps(
            create_backup(name, description), indent=2, ensure_ascii=False
        )

    @mcp.tool()
    async def ynh_op_renew_cert(domain: str) -> str:
        """[OPERATOR] Renouvelle le certificat Let's Encrypt d'un domaine.
        Args:
            domain: Domaine cible
        """
        from nexora_core.modes import get_mode_manager

        mm = get_mode_manager()
        if not mm.require_mode("operator"):
            return f"❌ Mode actuel: {mm.current_mode}. Nécessite: operator."
        from nexora_core.operator_actions import renew_certificate

        return json.dumps(renew_certificate(domain), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_op_apply_branding(brand_name: str, accent: str = "#2dd4bf") -> str:
        """[OPERATOR] Applique un branding au portail Nexora.
        Args:
            brand_name: Nom de la marque
            accent: Couleur accent (hex)
        """
        from nexora_core.modes import get_mode_manager

        mm = get_mode_manager()
        if not mm.require_mode("operator"):
            return f"❌ Mode actuel: {mm.current_mode}. Nécessite: operator."
        from nexora_core.operator_actions import apply_branding

        return json.dumps(
            apply_branding(brand_name, accent), indent=2, ensure_ascii=False
        )

    @mcp.tool()
    async def ynh_op_backup_rotate(keep_count: int = 7) -> str:
        """[OPERATOR] Rotation des sauvegardes — garde les N plus récentes.
        Args:
            keep_count: Nombre de backups à conserver (défaut: 7)
        """
        from nexora_core.modes import get_mode_manager

        mm = get_mode_manager()
        if not mm.require_mode("operator"):
            return f"❌ Mode actuel: {mm.current_mode}. Nécessite: operator."
        from nexora_core.operator_actions import execute_backup_rotation

        return json.dumps(
            execute_backup_rotation(keep_count), indent=2, ensure_ascii=False
        )

    # ── Admin actions (with confirmation) ─────────────────────────────

    @mcp.tool()
    async def ynh_admin_install_app(
        app_id: str,
        domain: str,
        path: str = "/",
        label: str = "",
        confirm_token: str = "",
    ) -> str:
        """[ADMIN] Installe une application YunoHost. Nécessite confirmation.
        Args:
            app_id: Application à installer
            domain: Domaine
            path: Chemin URL
            label: Label affiché
            confirm_token: Token de confirmation (obtenu via un premier appel sans token)
        """
        from nexora_core.modes import (
            get_mode_manager,
            request_confirmation,
            validate_confirmation,
        )

        mm = get_mode_manager()
        if not mm.require_mode("admin"):
            return f"❌ Mode actuel: {mm.current_mode}. Nécessite: admin."
        if not confirm_token:
            return json.dumps(
                request_confirmation(
                    "install_app", {"app": app_id, "domain": domain, "path": path}
                ),
                indent=2,
                ensure_ascii=False,
            )
        confirmed = validate_confirmation(confirm_token)
        if not confirmed:
            return "❌ Token de confirmation invalide ou expiré."
        from nexora_core.admin_actions import install_app

        return json.dumps(
            install_app(app_id, domain, path, label), indent=2, ensure_ascii=False
        )

    @mcp.tool()
    async def ynh_admin_remove_app(app_id: str, confirm_token: str = "") -> str:
        """[ADMIN] Supprime une application. Nécessite confirmation.
        Args:
            app_id: Application à supprimer
            confirm_token: Token de confirmation
        """
        from nexora_core.modes import (
            get_mode_manager,
            request_confirmation,
            validate_confirmation,
        )

        mm = get_mode_manager()
        if not mm.require_mode("admin"):
            return f"❌ Mode actuel: {mm.current_mode}. Nécessite: admin."
        if not confirm_token:
            return json.dumps(
                request_confirmation("remove_app", {"app": app_id}),
                indent=2,
                ensure_ascii=False,
            )
        confirmed = validate_confirmation(confirm_token)
        if not confirmed:
            return "❌ Token de confirmation invalide ou expiré."
        from nexora_core.admin_actions import remove_app

        return json.dumps(remove_app(app_id), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_admin_upgrade_apps(app_id: str = "", confirm_token: str = "") -> str:
        """[ADMIN] Met à jour les applications. Nécessite confirmation.
        Args:
            app_id: App spécifique (vide = toutes)
            confirm_token: Token de confirmation
        """
        from nexora_core.modes import (
            get_mode_manager,
            request_confirmation,
            validate_confirmation,
        )

        mm = get_mode_manager()
        if not mm.require_mode("admin"):
            return f"❌ Mode actuel: {mm.current_mode}. Nécessite: admin."
        if not confirm_token:
            return json.dumps(
                request_confirmation("upgrade_apps", {"app": app_id or "all"}),
                indent=2,
                ensure_ascii=False,
            )
        confirmed = validate_confirmation(confirm_token)
        if not confirmed:
            return "❌ Token de confirmation invalide ou expiré."
        from nexora_core.admin_actions import upgrade_app

        return json.dumps(upgrade_app(app_id), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_admin_deploy_blueprint(
        slug: str, domain: str, confirm_token: str = ""
    ) -> str:
        """[ADMIN] Déploie un blueprint métier complet. Nécessite confirmation.
        Args:
            slug: Identifiant du blueprint
            domain: Domaine principal
            confirm_token: Token de confirmation
        """
        from nexora_core.modes import (
            get_mode_manager,
            request_confirmation,
            validate_confirmation,
        )

        mm = get_mode_manager()
        if not mm.require_mode("admin"):
            return f"❌ Mode actuel: {mm.current_mode}. Nécessite: admin."
        from nexora_core.blueprints import load_blueprints
        from pathlib import Path

        bps = load_blueprints(Path("/opt/nexora/blueprints")) or load_blueprints(
            Path(__file__).resolve().parents[3] / "blueprints"
        )
        bp = next((b for b in bps if b.slug == slug), None)
        if not bp:
            return f"❌ Blueprint '{slug}' non trouvé."
        if not confirm_token:
            return json.dumps(
                request_confirmation(
                    "deploy_blueprint",
                    {"blueprint": slug, "domain": domain, "apps": bp.recommended_apps},
                ),
                indent=2,
                ensure_ascii=False,
            )
        confirmed = validate_confirmation(confirm_token)
        if not confirmed:
            return "❌ Token de confirmation invalide ou expiré."
        from nexora_core.admin_actions import deploy_blueprint

        return json.dumps(
            deploy_blueprint(slug, domain, bp.recommended_apps, bp.subdomains),
            indent=2,
            ensure_ascii=False,
        )

    @mcp.tool()
    async def ynh_admin_system_upgrade(
        apps: bool = False, system: bool = False, confirm_token: str = ""
    ) -> str:
        """[ADMIN] Mise à jour système et/ou apps. Nécessite confirmation.
        Args:
            apps: Mettre à jour les apps
            system: Mettre à jour le système
            confirm_token: Token de confirmation
        """
        from nexora_core.modes import (
            get_mode_manager,
            request_confirmation,
            validate_confirmation,
        )

        mm = get_mode_manager()
        if not mm.require_mode("admin"):
            return f"❌ Mode actuel: {mm.current_mode}. Nécessite: admin."
        if not confirm_token:
            return json.dumps(
                request_confirmation(
                    "system_upgrade", {"apps": apps, "system": system}
                ),
                indent=2,
                ensure_ascii=False,
            )
        confirmed = validate_confirmation(confirm_token)
        if not confirmed:
            return "❌ Token de confirmation invalide ou expiré."
        from nexora_core.admin_actions import system_upgrade

        return json.dumps(system_upgrade(apps, system), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_admin_action_log(lines: int = 50) -> str:
        """[ADMIN] Affiche le journal des actions admin.
        Args:
            lines: Nombre d'entrées (défaut: 50)
        """
        from nexora_core.modes import get_mode_manager

        mm = get_mode_manager()
        if not mm.require_mode("admin"):
            return f"❌ Mode actuel: {mm.current_mode}. Nécessite: admin."
        from nexora_core.admin_actions import get_admin_action_log

        log = get_admin_action_log(lines)
        if not log:
            return "Aucune action admin enregistrée."
        return json.dumps(log, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_admin_restore_backup(
        name: str, apps: str = "", confirm_token: str = ""
    ) -> str:
        """[ADMIN] Restaure un backup YunoHost. Nécessite confirmation.
        Args:
            name: Nom de l'archive
            apps: Apps à restaurer (vide = toutes)
            confirm_token: Token de confirmation
        """
        from nexora_core.modes import (
            get_mode_manager,
            request_confirmation,
            validate_confirmation,
        )

        mm = get_mode_manager()
        if not mm.require_mode("admin"):
            return f"❌ Mode actuel: {mm.current_mode}. Nécessite: admin."
        if not confirm_token:
            return json.dumps(
                request_confirmation("restore_backup", {"name": name, "apps": apps}),
                indent=2,
            )
        confirmed = validate_confirmation(confirm_token)
        if not confirmed:
            return "❌ Token invalide ou expiré."
        from nexora_core.admin_actions import restore_backup

        return json.dumps(restore_backup(name, apps), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_admin_create_user(
        username: str,
        fullname: str,
        domain: str,
        password: str,
        confirm_token: str = "",
    ) -> str:
        """[ADMIN] Crée un utilisateur YunoHost. Nécessite confirmation.
        Args:
            username: Login
            fullname: Nom complet
            domain: Domaine email
            password: Mot de passe
            confirm_token: Token de confirmation
        """
        from nexora_core.modes import (
            get_mode_manager,
            request_confirmation,
            validate_confirmation,
        )

        mm = get_mode_manager()
        if not mm.require_mode("admin"):
            return f"❌ Mode actuel: {mm.current_mode}. Nécessite: admin."
        if not confirm_token:
            return json.dumps(
                request_confirmation(
                    "create_user", {"username": username, "domain": domain}
                ),
                indent=2,
            )
        confirmed = validate_confirmation(confirm_token)
        if not confirmed:
            return "❌ Token invalide ou expiré."
        from nexora_core.admin_actions import create_user

        return json.dumps(
            create_user(username, fullname, domain, password),
            indent=2,
            ensure_ascii=False,
        )

    @mcp.tool()
    async def ynh_admin_delete_user(
        username: str, purge: bool = False, confirm_token: str = ""
    ) -> str:
        """[ADMIN] Supprime un utilisateur. Nécessite confirmation.
        Args:
            username: Login
            purge: Supprimer aussi les données
            confirm_token: Token de confirmation
        """
        from nexora_core.modes import (
            get_mode_manager,
            request_confirmation,
            validate_confirmation,
        )

        mm = get_mode_manager()
        if not mm.require_mode("admin"):
            return f"❌ Mode actuel: {mm.current_mode}. Nécessite: admin."
        if not confirm_token:
            return json.dumps(
                request_confirmation(
                    "delete_user", {"username": username, "purge": purge}
                ),
                indent=2,
            )
        confirmed = validate_confirmation(confirm_token)
        if not confirmed:
            return "❌ Token invalide ou expiré."
        from nexora_core.admin_actions import delete_user

        return json.dumps(delete_user(username, purge), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_admin_add_domain(domain: str, confirm_token: str = "") -> str:
        """[ADMIN] Ajoute un domaine. Nécessite confirmation.
        Args:
            domain: Nom de domaine
            confirm_token: Token de confirmation
        """
        from nexora_core.modes import (
            get_mode_manager,
            request_confirmation,
            validate_confirmation,
        )

        mm = get_mode_manager()
        if not mm.require_mode("admin"):
            return f"❌ Mode actuel: {mm.current_mode}. Nécessite: admin."
        if not confirm_token:
            return json.dumps(
                request_confirmation("add_domain", {"domain": domain}), indent=2
            )
        confirmed = validate_confirmation(confirm_token)
        if not confirmed:
            return "❌ Token invalide ou expiré."
        from nexora_core.admin_actions import add_domain

        return json.dumps(add_domain(domain), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_admin_remove_domain(domain: str, confirm_token: str = "") -> str:
        """[ADMIN] Supprime un domaine. Nécessite confirmation.
        Args:
            domain: Nom de domaine
            confirm_token: Token de confirmation
        """
        from nexora_core.modes import (
            get_mode_manager,
            request_confirmation,
            validate_confirmation,
        )

        mm = get_mode_manager()
        if not mm.require_mode("admin"):
            return f"❌ Mode actuel: {mm.current_mode}. Nécessite: admin."
        if not confirm_token:
            return json.dumps(
                request_confirmation("remove_domain", {"domain": domain}), indent=2
            )
        confirmed = validate_confirmation(confirm_token)
        if not confirmed:
            return "❌ Token invalide ou expiré."
        from nexora_core.admin_actions import remove_domain

        return json.dumps(remove_domain(domain), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_op_sync_branding_to_node(node_id: str) -> str:
        """[OPERATOR] Pousse le branding actuel vers un nœud distant.
        Args:
            node_id: ID du nœud cible
        """
        from nexora_core.modes import get_mode_manager

        mm = get_mode_manager()
        if not mm.require_mode("operator"):
            return f"❌ Mode actuel: {mm.current_mode}. Nécessite: operator."
        from nexora_core.state import StateStore
        from nexora_core.operator_actions import sync_branding_to_node
        from nexora_core.auth import get_api_token

        store = StateStore("/opt/nexora/var/state.json")
        state = store.load()
        branding = state.get("branding", {})
        node = next(
            (n for n in state.get("nodes", []) if n.get("node_id") == node_id), None
        )
        if not node:
            return f"❌ Nœud '{node_id}' non trouvé."
        result = sync_branding_to_node(
            node.get("hostname", ""),
            node.get("agent_port", 38121),
            branding,
            get_api_token(),
        )
        return json.dumps(result, indent=2, ensure_ascii=False)
