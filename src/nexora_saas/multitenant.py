"""Multi-tenant: client isolation, resource quotas, tenant management."""

from __future__ import annotations

import datetime
from typing import Any


def generate_tenant_config(
    tenant_name: str,
    *,
    domain: str = "",
    apps: list[str] | None = None,
    users: list[str] | None = None,
    quota_gb: int = 10,
) -> dict[str, Any]:
    """Generate a tenant isolation configuration."""
    return {
        "tenant_id": tenant_name.lower().replace(" ", "-"),
        "tenant_name": tenant_name,
        "domain": domain or f"{tenant_name.lower()}.example.com",
        "apps": apps or [],
        "users": users or [],
        "quotas": {
            "storage_gb": quota_gb,
            "max_apps": len(apps) + 5 if apps else 10,
            "max_users": len(users) + 20 if users else 25,
        },
        "isolation": {
            "method": "subdomain",
            "network": "shared",
            "data": "separated",
            "permissions": "per_tenant_group",
        },
        "ynh_group": f"tenant_{tenant_name.lower().replace(' ', '_')}",
        "timestamp": datetime.datetime.now().isoformat(),
    }


def generate_tenant_setup_commands(tenant: dict[str, Any]) -> list[str]:
    """Generate YunoHost commands to set up a tenant."""
    commands = []
    domain = tenant.get("domain", "")
    group = tenant.get("ynh_group", "")
    if domain:
        commands.append(f"yunohost domain add {domain}")
        commands.append(f"yunohost domain cert install {domain}")
    if group:
        commands.append(f"yunohost user group create {group}")
    for user in tenant.get("users", []):
        commands.append(f'yunohost user create {user} --domain {domain} --fullname "{user}" --password "__CHANGE__"')
        if group:
            commands.append(f"yunohost user group add {group} {user}")
    for app in tenant.get("apps", []):
        commands.append(f'yunohost app install {app} --args "domain={domain}&path=/" --label "{app}"')
        if group:
            commands.append(f"yunohost user permission update {app}.main --add {group} --remove all_users")
    return commands


def generate_tenant_report(tenants: list[dict[str, Any]]) -> dict[str, Any]:
    """Generate a multi-tenant overview report."""
    total_apps = sum(len(t.get("apps", [])) for t in tenants)
    total_users = sum(len(t.get("users", [])) for t in tenants)
    total_storage = sum(t.get("quotas", {}).get("storage_gb", 0) for t in tenants)

    return {
        "tenants": [
            {
                "name": t.get("tenant_name"),
                "domain": t.get("domain"),
                "apps": len(t.get("apps", [])),
                "users": len(t.get("users", [])),
            }
            for t in tenants
        ],
        "total_tenants": len(tenants),
        "total_apps": total_apps,
        "total_users": total_users,
        "total_storage_gb": total_storage,
        "timestamp": datetime.datetime.now().isoformat(),
    }
