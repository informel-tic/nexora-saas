"""WS9-T04: Quotas and entitlements enforcement for Nexora SaaS."""

from __future__ import annotations

from nexora_core.domain_models import TenantTier

# Default quotas per tier
DEFAULT_QUOTAS = {
    TenantTier.FREE: {
        "max_nodes": 5,
        "max_apps_per_node": 10,
        "max_storage_gb": 10,
        "features": ["basic_monitoring", "local_backup"],
    },
    TenantTier.PRO: {
        "max_nodes": 50,
        "max_apps_per_node": 50,
        "max_storage_gb": 100,
        "features": ["advanced_monitoring", "pra_support", "priority_support"],
    },
    TenantTier.ENTERPRISE: {
        "max_nodes": 1000,
        "max_apps_per_node": 200,
        "max_storage_gb": 10000,
        "features": ["all", "24/7_support", "multi_region"],
    },
}


def get_quota_limit(tier: TenantTier | str, resource: str) -> int:
    """Get the limit for a specific resource and tier."""
    # Handle string-based tier names (e.g. from JSON state)
    if isinstance(tier, str):
        try:
            tier = TenantTier(tier)
        except ValueError:
            tier = TenantTier.FREE

    limit = DEFAULT_QUOTAS.get(tier, {}).get(resource, 0)
    return limit if isinstance(limit, int) else 0


def is_quota_exceeded(
    tier: TenantTier | str, resource: str, current_value: int
) -> bool:
    """Check if a resource quota has been exceeded."""
    limit = get_quota_limit(tier, resource)
    return current_value >= limit


def get_tenant_entitlements(tier: TenantTier | str) -> list[str]:
    """Get the list of features enabled for a given tier."""
    if isinstance(tier, str):
        try:
            tier = TenantTier(tier)
        except ValueError:
            tier = TenantTier.FREE

    return DEFAULT_QUOTAS.get(tier, {}).get("features", [])
