"""MCP tools for multi-tenant management."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP


def register_multitenant_tools(mcp: FastMCP, settings=None):

    @mcp.tool()
    async def ynh_tenant_create(
        tenant_name: str,
        domain: str = "",
        apps: str = "",
        users: str = "",
        quota_gb: int = 10,
    ) -> str:
        """Génère la configuration d'isolation pour un nouveau client/tenant.
        Args:
            tenant_name: Nom du tenant
            domain: Domaine dédié (auto-généré si vide)
            apps: Apps séparées par des virgules
            users: Utilisateurs séparés par des virgules
            quota_gb: Quota de stockage en Go
        """
        from nexora_saas.multitenant import generate_tenant_config

        app_list = [a.strip() for a in apps.split(",") if a.strip()] if apps else []
        user_list = [u.strip() for u in users.split(",") if u.strip()] if users else []
        config = generate_tenant_config(
            tenant_name,
            domain=domain,
            apps=app_list,
            users=user_list,
            quota_gb=quota_gb,
        )
        return json.dumps(config, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_tenant_setup_commands(tenant_name: str, domain: str, apps: str = "", users: str = "") -> str:
        """Génère les commandes YunoHost pour créer l'environnement d'un tenant.
        Args:
            tenant_name: Nom du tenant
            domain: Domaine dédié
            apps: Apps séparées par des virgules
            users: Utilisateurs séparés par des virgules
        """
        from nexora_saas.multitenant import (
            generate_tenant_config,
            generate_tenant_setup_commands,
        )

        app_list = [a.strip() for a in apps.split(",") if a.strip()] if apps else []
        user_list = [u.strip() for u in users.split(",") if u.strip()] if users else []
        config = generate_tenant_config(tenant_name, domain=domain, apps=app_list, users=user_list)
        commands = generate_tenant_setup_commands(config)
        return "\n".join(commands)

    @mcp.tool()
    async def ynh_tenant_report() -> str:
        """Génère un rapport multi-tenant (vue d'ensemble de tous les clients)."""
        from nexora_node_sdk.state import StateStore
        from nexora_saas.multitenant import generate_tenant_report

        store = StateStore("/opt/nexora/var/state.json")
        state = store.load()
        tenants = state.get("tenants", [])
        if not tenants:
            return "Aucun tenant configuré. Utilisez ynh_tenant_create pour commencer."
        return json.dumps(generate_tenant_report(tenants), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_tenant_deploy(
        tenant_name: str,
        domain: str,
        apps: str = "",
        users: str = "",
        confirm_token: str = "",
    ) -> str:
        """[ADMIN] Déploie un tenant complet : domaine, certificat, groupe, utilisateurs, apps.
        Args:
            tenant_name: Nom du tenant
            domain: Domaine dédié
            apps: Apps séparées par virgules
            users: Utilisateurs séparés par virgules
            confirm_token: Token de confirmation (premier appel sans = demande confirmation)
        """
        from nexora_saas.modes import (
            get_mode_manager,
            request_confirmation,
            validate_confirmation,
        )

        mm = get_mode_manager()
        if not mm.require_mode("admin"):
            return f"❌ Mode actuel: {mm.current_mode}. Nécessite: admin."
        if not confirm_token:
            return json.dumps(
                request_confirmation("deploy_tenant", {"tenant": tenant_name, "domain": domain}),
                indent=2,
            )
        confirmed = validate_confirmation(confirm_token)
        if not confirmed:
            return "❌ Token de confirmation invalide ou expiré."

        from nexora_saas.multitenant import generate_tenant_config
        from yunohost_mcp.utils.runner import run_ynh_command

        app_list = [a.strip() for a in apps.split(",") if a.strip()] if apps else []
        user_list = [u.strip() for u in users.split(",") if u.strip()] if users else []
        config = generate_tenant_config(tenant_name, domain=domain, apps=app_list, users=user_list)

        results = []
        # Add domain
        r = await run_ynh_command("domain", "add", domain)
        results.append({"action": "add_domain", "success": r.success, "error": r.error or ""})
        # Cert
        r = await run_ynh_command("domain", "cert", "install", domain, "--no-checks")
        results.append({"action": "install_cert", "success": r.success})
        # Group
        group = config.get("ynh_group", "")
        if group:
            r = await run_ynh_command("user", "group", "create", group)
            results.append({"action": "create_group", "group": group, "success": r.success})
        # Users
        for user in user_list:
            r = await run_ynh_command(
                "user",
                "create",
                user,
                "--fullname",
                user,
                "--domain",
                domain,
                "--password",
                f"__CHANGE_{user}__",
            )
            results.append({"action": "create_user", "user": user, "success": r.success})
            if group:
                await run_ynh_command("user", "group", "add", group, user)
        # Apps
        for app in app_list:
            r = await run_ynh_command("app", "install", app, "--args", f"domain={domain}&path=/", timeout=600)
            results.append({"action": "install_app", "app": app, "success": r.success})

        # Save tenant to state
        from nexora_node_sdk.state import StateStore

        store = StateStore("/opt/nexora/var/state.json")
        state = store.load()
        state.setdefault("tenants", []).append(config)
        store.save(state)

        ok = sum(1 for r in results if r.get("success"))
        return json.dumps(
            {
                "tenant": tenant_name,
                "domain": domain,
                "total_actions": len(results),
                "succeeded": ok,
                "results": results,
            },
            indent=2,
            ensure_ascii=False,
        )
