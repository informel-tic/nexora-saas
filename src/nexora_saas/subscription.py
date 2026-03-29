"""SaaS subscription management — organizations, plans, and subscriptions.

This module implements the commercial layer for the Nexora SaaS platform:
- Organizations (the billing entity)
- Subscription plans (free, pro, enterprise)
- Subscriptions (binding an org to a plan with lifecycle)
- Tenant provisioning upon subscription activation
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any


class PlanTier(str, Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class SubscriptionStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


PLAN_CATALOG = {
    PlanTier.FREE: {
        "plan_id": "plan-free",
        "name": "Starter",
        "tier": "free",
        "max_nodes": 5,
        "max_apps_per_node": 10,
        "max_storage_gb": 10,
        "features": ["basic_monitoring", "local_backup", "enrollment"],
        "price_monthly_eur": 0,
    },
    PlanTier.PRO: {
        "plan_id": "plan-pro",
        "name": "Pro",
        "tier": "pro",
        "max_nodes": 50,
        "max_apps_per_node": 50,
        "max_storage_gb": 100,
        "features": [
            "advanced_monitoring",
            "pra_support",
            "priority_support",
            "fleet_lifecycle",
            "automation",
            "multi_tenant",
        ],
        "price_monthly_eur": 49,
    },
    PlanTier.ENTERPRISE: {
        "plan_id": "plan-enterprise",
        "name": "Enterprise",
        "tier": "enterprise",
        "max_nodes": 1000,
        "max_apps_per_node": 200,
        "max_storage_gb": 10000,
        "features": ["all", "24/7_support", "multi_region", "custom_branding", "sla_guarantee"],
        "price_monthly_eur": 199,
    },
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gen_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(8)}"


# ---------------------------------------------------------------------------
# Organization CRUD
# ---------------------------------------------------------------------------

def create_organization(
    state: dict[str, Any],
    *,
    name: str,
    contact_email: str,
    billing_address: str = "",
) -> dict[str, Any]:
    """Create a new organization (billing entity)."""
    state.setdefault("organizations", [])

    if any(o.get("name") == name for o in state["organizations"]):
        return {"success": False, "error": f"Organization '{name}' already exists"}

    org = {
        "org_id": _gen_id("org"),
        "name": name,
        "contact_email": contact_email,
        "billing_address": billing_address,
        "created_at": _utc_now(),
        "status": "active",
    }
    state["organizations"].append(org)
    return {"success": True, "organization": org}


def get_organization(state: dict[str, Any], org_id: str) -> dict[str, Any] | None:
    for org in state.get("organizations", []):
        if org.get("org_id") == org_id:
            return org
    return None


def list_organizations(state: dict[str, Any]) -> list[dict[str, Any]]:
    return list(state.get("organizations", []))


# ---------------------------------------------------------------------------
# Subscription CRUD
# ---------------------------------------------------------------------------

def create_subscription(
    state: dict[str, Any],
    *,
    org_id: str,
    plan_tier: str,
    tenant_label: str = "",
) -> dict[str, Any]:
    """Create a subscription binding an org to a plan, and provision a tenant."""
    org = get_organization(state, org_id)
    if not org:
        return {"success": False, "error": f"Organization '{org_id}' not found"}

    try:
        tier = PlanTier(plan_tier)
    except ValueError:
        return {"success": False, "error": f"Unknown plan tier: {plan_tier}"}

    plan = PLAN_CATALOG[tier]
    state.setdefault("subscriptions", [])

    subscription_id = _gen_id("sub")
    tenant_id = _gen_id("tenant")
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    billing_period_end = (now_dt + timedelta(days=30)).isoformat()

    subscription = {
        "subscription_id": subscription_id,
        "org_id": org_id,
        "plan_id": plan["plan_id"],
        "tier": plan_tier,
        "tenant_id": tenant_id,
        "status": SubscriptionStatus.ACTIVE.value,
        "created_at": now,
        "activated_at": now,
        "billing_period_start": now,
        "billing_period_end": billing_period_end,
        "next_billing_date": billing_period_end,
        "price_monthly_eur": plan["price_monthly_eur"],
        "features": list(plan["features"]),
        "limits": {
            "max_nodes": plan["max_nodes"],
            "max_apps_per_node": plan["max_apps_per_node"],
            "max_storage_gb": plan["max_storage_gb"],
        },
    }
    state["subscriptions"].append(subscription)

    # Auto-provision tenant for this subscription
    state.setdefault("tenants", [])
    tenant = {
        "tenant_id": tenant_id,
        "org_id": org_id,
        "subscription_id": subscription_id,
        "tier": plan_tier,
        "label": tenant_label or f"{org['name']} - {plan['name']}",
        "created_at": now,
        "status": "active",
    }
    state["tenants"].append(tenant)

    return {
        "success": True,
        "subscription": subscription,
        "tenant": tenant,
    }


def get_subscription(state: dict[str, Any], subscription_id: str) -> dict[str, Any] | None:
    for sub in state.get("subscriptions", []):
        if sub.get("subscription_id") == subscription_id:
            return sub
    return None


def get_subscription_by_tenant(state: dict[str, Any], tenant_id: str) -> dict[str, Any] | None:
    for sub in state.get("subscriptions", []):
        if sub.get("tenant_id") == tenant_id:
            return sub
    return None


def list_subscriptions(
    state: dict[str, Any],
    org_id: str | None = None,
    tenant_id: str | None = None,
) -> list[dict[str, Any]]:
    subs = state.get("subscriptions", [])
    if org_id:
        subs = [s for s in subs if s.get("org_id") == org_id]
    if tenant_id:
        subs = [s for s in subs if s.get("tenant_id") == tenant_id]
    return subs


def suspend_subscription(state: dict[str, Any], subscription_id: str, reason: str = "") -> dict[str, Any]:
    sub = get_subscription(state, subscription_id)
    if not sub:
        return {"success": False, "error": "Subscription not found"}
    if sub["status"] != SubscriptionStatus.ACTIVE.value:
        return {"success": False, "error": f"Cannot suspend subscription in status '{sub['status']}'"}

    sub["status"] = SubscriptionStatus.SUSPENDED.value
    sub["suspended_at"] = _utc_now()
    sub["suspend_reason"] = reason

    # Suspend associated tenant
    for tenant in state.get("tenants", []):
        if tenant.get("tenant_id") == sub["tenant_id"]:
            tenant["status"] = "suspended"
            break

    return {"success": True, "subscription": sub}


def reactivate_subscription(state: dict[str, Any], subscription_id: str) -> dict[str, Any]:
    sub = get_subscription(state, subscription_id)
    if not sub:
        return {"success": False, "error": "Subscription not found"}
    if sub["status"] != SubscriptionStatus.SUSPENDED.value:
        return {"success": False, "error": f"Cannot reactivate subscription in status '{sub['status']}'"}

    sub["status"] = SubscriptionStatus.ACTIVE.value
    sub["reactivated_at"] = _utc_now()
    sub.pop("suspend_reason", None)

    for tenant in state.get("tenants", []):
        if tenant.get("tenant_id") == sub["tenant_id"]:
            tenant["status"] = "active"
            break

    return {"success": True, "subscription": sub}


def cancel_subscription(state: dict[str, Any], subscription_id: str) -> dict[str, Any]:
    sub = get_subscription(state, subscription_id)
    if not sub:
        return {"success": False, "error": "Subscription not found"}

    sub["status"] = SubscriptionStatus.CANCELLED.value
    sub["cancelled_at"] = _utc_now()

    # Deactivate associated tenant
    for tenant in state.get("tenants", []):
        if tenant.get("tenant_id") == sub["tenant_id"]:
            tenant["status"] = "cancelled"
            break

    return {"success": True, "subscription": sub}


def upgrade_subscription(state: dict[str, Any], subscription_id: str, new_tier: str) -> dict[str, Any]:
    sub = get_subscription(state, subscription_id)
    if not sub:
        return {"success": False, "error": "Subscription not found"}

    try:
        tier = PlanTier(new_tier)
    except ValueError:
        return {"success": False, "error": f"Unknown plan tier: {new_tier}"}

    plan = PLAN_CATALOG[tier]
    old_tier = sub["tier"]
    tier_order = {PlanTier.FREE.value: 0, PlanTier.PRO.value: 1, PlanTier.ENTERPRISE.value: 2}
    is_downgrade = tier_order.get(new_tier, 0) < tier_order.get(str(old_tier), 0)

    sub["tier"] = new_tier
    sub["plan_id"] = plan["plan_id"]
    sub["price_monthly_eur"] = plan["price_monthly_eur"]
    sub["features"] = list(plan["features"])
    sub["limits"] = {
        "max_nodes": plan["max_nodes"],
        "max_apps_per_node": plan["max_apps_per_node"],
        "max_storage_gb": plan["max_storage_gb"],
    }
    sub["upgraded_at"] = _utc_now()
    sub["previous_tier"] = old_tier
    if is_downgrade:
        sub["downgrade"] = True
        sub["warning"] = f"Downgrade from '{old_tier}' to '{new_tier}'"
    else:
        sub.pop("downgrade", None)
        sub.pop("warning", None)

    # Update associated tenant tier
    for tenant in state.get("tenants", []):
        if tenant.get("tenant_id") == sub["tenant_id"]:
            tenant["tier"] = new_tier
            break

    # If downgrading, check for quota violations against current tenant usage
    violations: list[dict[str, int]] = []
    tenant = next((t for t in state.get("tenants", []) if t.get("tenant_id") == sub.get("tenant_id")), None)
    if tenant:
        # Node count
        current_nodes = int(tenant.get("nodes", 0) or 0)
        allowed_nodes = int(sub.get("limits", {}).get("max_nodes", 0) or 0)
        if current_nodes > allowed_nodes:
            violations.append({"limit": "max_nodes", "current": current_nodes, "allowed": allowed_nodes})

        # Apps per node
        current_apps = int(tenant.get("apps_per_node", 0) or 0)
        allowed_apps = int(sub.get("limits", {}).get("max_apps_per_node", 0) or 0)
        if current_apps > allowed_apps:
            violations.append({"limit": "max_apps_per_node", "current": current_apps, "allowed": allowed_apps})

        # Storage
        current_storage = int(tenant.get("storage_gb", 0) or 0)
        allowed_storage = int(sub.get("limits", {}).get("max_storage_gb", 0) or 0)
        if current_storage > allowed_storage:
            violations.append({"limit": "max_storage_gb", "current": current_storage, "allowed": allowed_storage})

    if violations:
        sub["quota_violations"] = violations
    else:
        sub.pop("quota_violations", None)

    return {
        "success": True,
        "subscription": sub,
        "previous_tier": old_tier,
        "downgrade": is_downgrade,
        "warning": sub.get("warning"),
        "violations": violations,
    }


# ---------------------------------------------------------------------------
# Plan catalog
# ---------------------------------------------------------------------------

def list_plans() -> list[dict[str, Any]]:
    return [dict(plan) for plan in PLAN_CATALOG.values()]


def get_plan(tier: str) -> dict[str, Any] | None:
    try:
        return dict(PLAN_CATALOG[PlanTier(tier)])
    except (ValueError, KeyError):
        return None
