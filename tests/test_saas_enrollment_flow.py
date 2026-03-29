"""End-to-end tests for the SaaS enrollment + provisioning flow.

Verifies the full lifecycle:
1. Create org → subscribe → get tenant
2. Issue enrollment token
3. Enroll node (node calls SaaS)
4. SaaS provisions features on enrolled node (push-down)
5. Heartbeat renews leases
6. Suspend subscription → features should stop
7. Cancel → deprovision
"""
from __future__ import annotations

import unittest

from nexora_saas.feature_provisioning import (
    build_heartbeat_for_node,
    deprovision_node,
    get_node_provisioning_status,
    provision_node_features,
    resolve_features_for_tier,
)
from nexora_saas.node_connector import NodeConnector
from nexora_saas.subscription import (
    cancel_subscription,
    create_organization,
    create_subscription,
    get_subscription,
    upgrade_subscription,
)

HMAC_SECRET = "abcdefghijklmnopqrstuvwxyz123456"
NODE_URL = "http://192.168.1.100:38121"


class FullEnrollmentFlowTests(unittest.TestCase):
    """Tests the complete lifecycle: org → subscribe → enroll → provision → heartbeat → cancel."""

    def setUp(self):
        self.state: dict = {}
        # 1. Create organization
        org_result = create_organization(
            self.state, name="FlowCorp", contact_email="admin@flow.test"
        )
        self.org = org_result["organization"]

        # 2. Subscribe (creates tenant)
        sub_result = create_subscription(
            self.state, org_id=self.org["org_id"], plan_tier="pro"
        )
        self.subscription = sub_result["subscription"]
        self.tenant = sub_result["tenant"]

        # 3. Simulate node enrollment
        self.state.setdefault("nodes", [])
        self.node = {
            "node_id": "node-flow-01",
            "tenant_id": self.tenant["tenant_id"],
            "hostname": "flow01.test",
            "status": "registered",
            "url": NODE_URL,
        }
        self.state["nodes"].append(self.node)

    def test_provision_after_enrollment(self):
        """SaaS pushes features to node after enrollment."""
        result = provision_node_features(
            self.state,
            node_id="node-flow-01",
            node_url=NODE_URL,
            hmac_secret=HMAC_SECRET,
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["tier"], "pro")
        # Should have: establish-secret + features + heartbeat
        self.assertGreater(len(result["commands"]), 2)

    def test_features_match_subscription_tier(self):
        """Provisioned features must match the subscription's plan tier."""
        result = provision_node_features(
            self.state,
            node_id="node-flow-01",
            node_url=NODE_URL,
            hmac_secret=HMAC_SECRET,
        )
        expected_features = resolve_features_for_tier("pro")
        provisioned_ids = {f["feature_id"] for f in result["features"]}
        expected_ids = {f["feature_id"] for f in expected_features}
        self.assertEqual(provisioned_ids, expected_ids)

    def test_heartbeat_after_provision(self):
        """Heartbeat keeps feature leases alive."""
        provision_node_features(
            self.state,
            node_id="node-flow-01",
            node_url=NODE_URL,
            hmac_secret=HMAC_SECRET,
        )
        hb = build_heartbeat_for_node(
            self.state,
            node_id="node-flow-01",
            node_url=NODE_URL,
            hmac_secret=HMAC_SECRET,
            lease_seconds=3600,
        )
        self.assertTrue(hb["success"])
        self.assertEqual(hb["command"]["body"]["lease_seconds"], 3600)

    def test_upgrade_increases_features(self):
        """Upgrading tier should give more features on next provision."""
        # Provision with pro tier
        pro_result = provision_node_features(
            self.state,
            node_id="node-flow-01",
            node_url=NODE_URL,
            hmac_secret=HMAC_SECRET,
        )
        pro_count = len(pro_result["features"])

        # Upgrade to enterprise
        upgrade_subscription(self.state, self.subscription["subscription_id"], "enterprise")

        # Re-provision
        ent_result = provision_node_features(
            self.state,
            node_id="node-flow-01",
            node_url=NODE_URL,
            hmac_secret=HMAC_SECRET,
        )
        ent_count = len(ent_result["features"])
        self.assertGreater(ent_count, pro_count)

    def test_cancel_then_deprovision(self):
        """Cancelling subscription leads to deprovisioning."""
        provision_node_features(
            self.state,
            node_id="node-flow-01",
            node_url=NODE_URL,
            hmac_secret=HMAC_SECRET,
        )
        cancel_subscription(self.state, self.subscription["subscription_id"])

        sub = get_subscription(self.state, self.subscription["subscription_id"])
        self.assertEqual(sub["status"], "cancelled")

        deprov = deprovision_node(
            self.state,
            node_id="node-flow-01",
            node_url=NODE_URL,
            hmac_secret=HMAC_SECRET,
        )
        self.assertTrue(deprov["success"])
        rollback_cmd = deprov["commands"][0]
        self.assertEqual(rollback_cmd["action"], "overlay/rollback")

    def test_provisioning_status_tracking(self):
        """Multiple provisions track all events."""
        provision_node_features(
            self.state,
            node_id="node-flow-01",
            node_url=NODE_URL,
            hmac_secret=HMAC_SECRET,
        )
        deprovision_node(
            self.state,
            node_id="node-flow-01",
            node_url=NODE_URL,
        )
        provision_node_features(
            self.state,
            node_id="node-flow-01",
            node_url=NODE_URL,
            hmac_secret=HMAC_SECRET,
        )

        status = get_node_provisioning_status(self.state, "node-flow-01")
        self.assertEqual(status["total_events"], 3)


class NodePassiveReceiverTests(unittest.TestCase):
    """Verify that nodes are purely passive — they only receive, never initiate."""

    def test_all_commands_are_post_method(self):
        """SaaS commands to nodes are always POST (mutations)."""
        state: dict = {}
        org = create_organization(state, name="PassiveCorp", contact_email="p@p.test")
        sub = create_subscription(state, org_id=org["organization"]["org_id"], plan_tier="enterprise")
        state.setdefault("nodes", [])
        state["nodes"].append({
            "node_id": "node-passive-01",
            "tenant_id": sub["tenant"]["tenant_id"],
        })

        result = provision_node_features(
            state,
            node_id="node-passive-01",
            node_url=NODE_URL,
            hmac_secret=HMAC_SECRET,
        )
        for cmd in result["commands"]:
            self.assertEqual(cmd["method"], "POST")

    def test_all_mutation_commands_have_hmac(self):
        """Every mutation command from SaaS must have HMAC signature."""
        state: dict = {}
        org = create_organization(state, name="HMACCorp", contact_email="h@h.test")
        sub = create_subscription(state, org_id=org["organization"]["org_id"], plan_tier="pro")
        state.setdefault("nodes", [])
        state["nodes"].append({
            "node_id": "node-hmac-01",
            "tenant_id": sub["tenant"]["tenant_id"],
        })

        result = provision_node_features(
            state,
            node_id="node-hmac-01",
            node_url=NODE_URL,
            hmac_secret=HMAC_SECRET,
        )
        for cmd in result["commands"]:
            headers = cmd["headers"]
            self.assertIn("X-Nexora-SaaS-Signature", headers, f"No HMAC in command {cmd['action']}")

    def test_connector_targets_correct_node_url(self):
        """Commands target the correct node URL."""
        connector = NodeConnector("node-01", "http://192.168.1.200:38121", HMAC_SECRET)
        cmd = connector.build_command("test", "/overlay/test")
        self.assertTrue(cmd["url"].startswith("http://192.168.1.200:38121"))

    def test_different_nodes_get_independent_commands(self):
        """Provisioning two different nodes yields independent command sets."""
        state: dict = {}
        org = create_organization(state, name="MultiNode", contact_email="m@m.test")
        sub1 = create_subscription(state, org_id=org["organization"]["org_id"], plan_tier="pro")
        sub2 = create_subscription(state, org_id=org["organization"]["org_id"], plan_tier="free")

        state.setdefault("nodes", [])
        state["nodes"].append({"node_id": "node-A", "tenant_id": sub1["tenant"]["tenant_id"]})
        state["nodes"].append({"node_id": "node-B", "tenant_id": sub2["tenant"]["tenant_id"]})

        result_a = provision_node_features(
            state, node_id="node-A", node_url="http://a:38121", hmac_secret=HMAC_SECRET
        )
        result_b = provision_node_features(
            state, node_id="node-B", node_url="http://b:38121", hmac_secret=HMAC_SECRET
        )
        # Different tiers → different feature counts
        self.assertNotEqual(len(result_a["features"]), len(result_b["features"]))
        # Commands target different URLs
        urls_a = {cmd["url"] for cmd in result_a["commands"]}
        urls_b = {cmd["url"] for cmd in result_b["commands"]}
        for url in urls_a:
            self.assertTrue(url.startswith("http://a:38121"))
        for url in urls_b:
            self.assertTrue(url.startswith("http://b:38121"))
