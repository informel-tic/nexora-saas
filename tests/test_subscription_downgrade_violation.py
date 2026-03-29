from __future__ import annotations

import unittest

from nexora_saas.subscription import (
    create_organization,
    create_subscription,
    upgrade_subscription,
)


class SubscriptionDowngradeQuotaTests(unittest.TestCase):
    def test_downgrade_detects_quota_violations(self):
        """When downgrading a subscription, existing tenant usage that exceeds
        the new plan limits must be reported as quota violations.
        """
        state: dict = {}
        org = create_organization(state, name="QuotaOrg", contact_email="q@test")["organization"]

        # Create a pro subscription (max_nodes: 50)
        res = create_subscription(state, org_id=org["org_id"], plan_tier="pro")
        self.assertTrue(res["success"], res)
        subscription = res["subscription"]
        tenant = res["tenant"]

        # Simulate tenant currently having 10 nodes
        for t in state.get("tenants", []):
            if t["tenant_id"] == tenant["tenant_id"]:
                t["nodes"] = 10
                break

        # Downgrade to 'free' (max_nodes: 5) — should detect violation
        result = upgrade_subscription(state, subscription["subscription_id"], "free")
        self.assertTrue(result["success"], result)
        self.assertTrue(result.get("downgrade"), "Downgrade flag expected")

        violations = result.get("violations") or result.get("quota_violations") or []
        self.assertTrue(violations, "Expected at least one quota violation")

        # Expect a max_nodes violation with current=10 and allowed=5
        found = any(v.get("limit") == "max_nodes" and v.get("current") == 10 and v.get("allowed") == 5 for v in violations)
        self.assertTrue(found, f"Expected max_nodes violation in {violations}")


if __name__ == "__main__":
    unittest.main()
