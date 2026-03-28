"""Tests for the SaaS subscription module — organizations, plans, lifecycle."""
from __future__ import annotations

import unittest

from nexora_saas.subscription import (
    PLAN_CATALOG,
    PlanTier,
    SubscriptionStatus,
    cancel_subscription,
    create_organization,
    create_subscription,
    get_organization,
    get_plan,
    get_subscription,
    get_subscription_by_tenant,
    list_organizations,
    list_plans,
    list_subscriptions,
    suspend_subscription,
    upgrade_subscription,
)


class PlanCatalogTests(unittest.TestCase):
    def test_catalog_has_all_tiers(self):
        for tier in PlanTier:
            self.assertIn(tier, PLAN_CATALOG)

    def test_list_plans_returns_all(self):
        plans = list_plans()
        self.assertEqual(len(plans), len(PlanTier))

    def test_get_plan_valid(self):
        plan = get_plan("pro")
        self.assertIsNotNone(plan)
        self.assertEqual(plan["tier"], "pro")

    def test_get_plan_invalid(self):
        self.assertIsNone(get_plan("nonsense"))

    def test_free_plan_costs_zero(self):
        plan = get_plan("free")
        self.assertEqual(plan["price_monthly_eur"], 0)

    def test_plan_has_required_fields(self):
        for plan in list_plans():
            for key in ("plan_id", "name", "tier", "max_nodes", "features", "price_monthly_eur"):
                self.assertIn(key, plan, f"Missing {key} in plan {plan.get('tier')}")


class OrganizationTests(unittest.TestCase):
    def setUp(self):
        self.state: dict = {}

    def test_create_organization(self):
        result = create_organization(self.state, name="Acme", contact_email="admin@acme.test")
        self.assertTrue(result["success"])
        self.assertIn("organization", result)
        self.assertEqual(result["organization"]["name"], "Acme")
        self.assertTrue(result["organization"]["org_id"].startswith("org-"))

    def test_duplicate_organization_rejected(self):
        create_organization(self.state, name="Acme", contact_email="a@a.test")
        result = create_organization(self.state, name="Acme", contact_email="b@a.test")
        self.assertFalse(result["success"])
        self.assertIn("already exists", result["error"])

    def test_get_organization(self):
        created = create_organization(self.state, name="ACME", contact_email="x@y.test")
        org_id = created["organization"]["org_id"]
        found = get_organization(self.state, org_id)
        self.assertIsNotNone(found)
        self.assertEqual(found["org_id"], org_id)

    def test_get_organization_not_found(self):
        self.assertIsNone(get_organization(self.state, "org-nonexistent"))

    def test_list_organizations(self):
        create_organization(self.state, name="A", contact_email="a@a.test")
        create_organization(self.state, name="B", contact_email="b@b.test")
        orgs = list_organizations(self.state)
        self.assertEqual(len(orgs), 2)


class SubscriptionLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.state: dict = {}
        self.org = create_organization(
            self.state, name="TestCorp", contact_email="admin@testcorp.test"
        )["organization"]

    def test_create_subscription_provisions_tenant(self):
        result = create_subscription(
            self.state, org_id=self.org["org_id"], plan_tier="pro"
        )
        self.assertTrue(result["success"])
        sub = result["subscription"]
        tenant = result["tenant"]
        self.assertEqual(sub["tier"], "pro")
        self.assertEqual(sub["status"], "active")
        self.assertTrue(sub["subscription_id"].startswith("sub-"))
        self.assertTrue(tenant["tenant_id"].startswith("tenant-"))
        self.assertEqual(tenant["org_id"], self.org["org_id"])

    def test_subscription_unknown_org(self):
        result = create_subscription(self.state, org_id="org-nope", plan_tier="free")
        self.assertFalse(result["success"])

    def test_subscription_unknown_tier(self):
        result = create_subscription(
            self.state, org_id=self.org["org_id"], plan_tier="platinum"
        )
        self.assertFalse(result["success"])

    def test_suspend_subscription(self):
        sub_id = create_subscription(
            self.state, org_id=self.org["org_id"], plan_tier="free"
        )["subscription"]["subscription_id"]
        result = suspend_subscription(self.state, sub_id, reason="non-payment")
        self.assertTrue(result["success"])
        self.assertEqual(result["subscription"]["status"], "suspended")

    def test_suspend_already_suspended(self):
        sub_id = create_subscription(
            self.state, org_id=self.org["org_id"], plan_tier="free"
        )["subscription"]["subscription_id"]
        suspend_subscription(self.state, sub_id)
        result = suspend_subscription(self.state, sub_id)
        self.assertFalse(result["success"])

    def test_cancel_subscription(self):
        sub_id = create_subscription(
            self.state, org_id=self.org["org_id"], plan_tier="pro"
        )["subscription"]["subscription_id"]
        result = cancel_subscription(self.state, sub_id)
        self.assertTrue(result["success"])
        self.assertEqual(result["subscription"]["status"], "cancelled")
        # Tenant should also be cancelled
        tenant = next(
            t for t in self.state["tenants"]
            if t["tenant_id"] == result["subscription"]["tenant_id"]
        )
        self.assertEqual(tenant["status"], "cancelled")

    def test_upgrade_subscription(self):
        sub_id = create_subscription(
            self.state, org_id=self.org["org_id"], plan_tier="free"
        )["subscription"]["subscription_id"]
        result = upgrade_subscription(self.state, sub_id, "enterprise")
        self.assertTrue(result["success"])
        self.assertEqual(result["subscription"]["tier"], "enterprise")
        self.assertEqual(result["previous_tier"], "free")

    def test_upgrade_invalid_tier(self):
        sub_id = create_subscription(
            self.state, org_id=self.org["org_id"], plan_tier="free"
        )["subscription"]["subscription_id"]
        result = upgrade_subscription(self.state, sub_id, "platinum")
        self.assertFalse(result["success"])

    def test_get_subscription_by_tenant(self):
        result = create_subscription(
            self.state, org_id=self.org["org_id"], plan_tier="pro"
        )
        tenant_id = result["tenant"]["tenant_id"]
        sub = get_subscription_by_tenant(self.state, tenant_id)
        self.assertIsNotNone(sub)
        self.assertEqual(sub["tier"], "pro")

    def test_list_subscriptions_filtered(self):
        create_subscription(self.state, org_id=self.org["org_id"], plan_tier="free")
        create_subscription(self.state, org_id=self.org["org_id"], plan_tier="pro")

        all_subs = list_subscriptions(self.state)
        self.assertEqual(len(all_subs), 2)

        filtered = list_subscriptions(self.state, org_id=self.org["org_id"])
        self.assertEqual(len(filtered), 2)

        filtered_empty = list_subscriptions(self.state, org_id="org-other")
        self.assertEqual(len(filtered_empty), 0)
