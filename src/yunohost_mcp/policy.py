from __future__ import annotations

from yunohost_mcp.config import MCPSettings

DANGEROUS_TOOLS = {
    "ynh_app_install",
    "ynh_app_remove",
    "ynh_app_upgrade",
    "ynh_backup_restore",
    "ynh_backup_delete",
    "ynh_domain_add",
    "ynh_domain_remove",
    "ynh_domain_cert_install",
    "ynh_user_create",
    "ynh_user_delete",
    "ynh_user_update",
    "ynh_service_restart",
    "ynh_system_upgrade",
    "ynh_security_fail2ban_ban",
    "ynh_security_fail2ban_unban",
    "ynh_blueprint_deploy",
    "ynh_portal_apply_theme",
    "ynh_admin_install_app",
    "ynh_admin_remove_app",
    "ynh_admin_upgrade_apps",
    "ynh_admin_deploy_blueprint",
    "ynh_admin_system_upgrade",
}

OPERATOR_TOOLS = DANGEROUS_TOOLS | {
    "ynh_backup_create",
    "ynh_backup_verify",
    "ynh_pra_full_backup",
    "ynh_fleet_register_node",
    "ynh_op_restart_service",
    "ynh_op_create_backup",
    "ynh_op_renew_cert",
    "ynh_op_apply_branding",
    "ynh_op_backup_rotate",
}

PREFIXES = {
    "app": "ynh_app_",
    "backup": "ynh_backup_",
    "domain": "ynh_domain_",
    "user": "ynh_user_",
    "system": "ynh_system_",
    "pra": "ynh_pra_",
    "security": "ynh_security_",
    "monitoring": "ynh_monitor_",
    "documentation": "ynh_doc_",
    "packaging": "ynh_pkg_",
    "fleet": "ynh_fleet_",
    "sync": "ynh_fleet_sync_",
    "edge": "ynh_edge_",
    "portal": "ynh_portal_",
    "governance": "ynh_gov_",
    "automation": "ynh_auto_",
    "blueprints": "ynh_blueprint_",
    "docker": "ynh_docker_",
    "failover": "ynh_failover_",
    "storage": "ynh_storage_",
    "notifications": "ynh_notify_",
    "sla": "ynh_sla_",
    "migration": "ynh_migrate_",
    "multitenant": "ynh_tenant_",
    "hooks": "ynh_hooks_",
}


def module_enabled(tool_name: str, settings: MCPSettings) -> bool:
    for module, prefix in PREFIXES.items():
        if tool_name.startswith(prefix):
            return module in settings.enabled_modules
    return True


def tool_allowed(tool_name: str, settings: MCPSettings) -> bool:
    if not module_enabled(tool_name, settings):
        return False
    profile = settings.profile.lower()
    if profile == "admin":
        return settings.allow_destructive_tools or tool_name not in DANGEROUS_TOOLS
    if profile == "operator":
        if tool_name in DANGEROUS_TOOLS:
            return settings.allow_destructive_tools
        return True
    if profile == "architect":
        return tool_name not in DANGEROUS_TOOLS
    return tool_name not in OPERATOR_TOOLS
