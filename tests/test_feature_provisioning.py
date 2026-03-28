"""Tests for the feature provisioning engine — SaaS pushes features to nodes."""
from __future__ import annotations

import unittest

from nexora_saas.feature_provisioning import (
    TIER_FEATURE_SETS,
    build_heartbeat_for_node,
    deprovision_node,
    get_node_provisioning_status,
    provision_node_features,
    resolve_features_for_tier,
)
from nexora_saas.subscription import create_organization, create_subscription


class FeatureCatalogTests(unittest.TestCase):
    def test_all_tiers_have_features(self):
        for tier in ("free", "pro", "enterprise"):
            features = TIER_FEATURE_SETS[tier]
            self.assertGreater(len(features), 0, f"Tier {tier} has no features")

    def test_each_feature_has_required_fields(self):
        for tier, features in TIER_FEATURE_SETS.items():
            for f in features:
                for key in ("feature_id", "name", "kind", "config"):
                    self.assertIn(key, f, f"Missing {key} in feature {f.get('name')} of tier {tier}")

    def test_resolve_features_known_tier(self):
        features = resolve_features_for_tier("pro")
        self.assertEqual(features, TIER_FEATURE_SETS["pro"])

    def test_resolve_features_unknown_tier_fallback_free(self):
        features = resolve_features_for_tier("platinum")
        self.assertEqual(features, TIER_FEATURE_SETS["free"])

    def test_enterprise_has_more_features_than_free(self):
        self.assertGreater(
            len(TIER_FEATURE_SETS["enterprise"]),
            len(TIER_FEATURE_SETS["free"]),
        )

    def test_feature_kinds_are_valid(self):
        valid_kinds = {"cron", "systemd", "nginx", "docker"}
        for tier, features in TIER_FEATURE_SETS.items():
            for f in features:
                self.assertIn(f["kind"], valid_kinds, f"Invalid kind '{f['kind']}' in {tier}")


class ProvisionNodeTests(unittest.TestCase):
    def setUp(self):
        self.state: dict = {}
        org = create_organization(self.state, name="Prov-Corp", contact_email="admin@prov.test")
        self.org_id = org["organization"]["org_id"]
        sub_result = create_subscription(self.state, org_id=self.org_id, plan_tier="pro")
        self.sub = sub_result["subscription"]
        self.tenant_id = sub_result["tenant"]["tenant_id"]

        # Add a node to the state
        self.state.setdefault("nodes", [])
        self.state["nodes"].append({
            "node_id": "node-prov-01",
            "tenant_id": self.tenant_id,
            "hostname": "prov01.test",
            "status": "registered",
        })

    def test_provision_node_builds_commands(self):
        result = provision_node_features(
            self.state,
            node_id="node-prov-01",
            node_url="http://192.168.1.100:38121",
            hmac_secret="abcdefghijklmnopqrstuvwxyz123456",
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["tier"], "pro")
        self.assertGreater(len(result["commands"]), 0)
        self.assertGreater(len(result["features"]), 0)

    def test_first_command_is_establish_secret(self):
        result = provision_node_features(
            self.state,
            node_id="node-prov-01",
            node_url="http://192.168.1.100:38121",
            hmac_secret="abcdefghijklmnopqrstuvwxyz123456",
        )
        first_cmd = result["commands"][0]
        self.assertEqual(first_cmd["action"], "establish-secret")

    def test_last_command_is_heartbeat(self):
        result = provision_node_features(
            self.state,
            node_id="node-prov-01",
            node_url="http://192.168.1.100:38121",
            hmac_secret="abcdefghijklmnopqrstuvwxyz123456",
        )
        last_cmd = result["commands"][-1]
        self.assertEqual(last_cmd["action"], "overlay/heartbeat")

    def test_commands_have_hmac_headers(self):
        result = provision_node_features(
            self.state,
            node_id="node-prov-01",
            node_url="http://192.168.1.100:38121",
            hmac_secret="abcdefghijklmnopqrstuvwxyz123456",
        )
        for cmd in result["commands"]:
            self.assertIn("X-Nexora-SaaS-Signature", cmd["headers"], f"Missing HMAC in {cmd['action']}")

    def test_provision_records_event(self):
        provision_node_features(
            self.state,
            node_id="node-prov-01",
            node_url="http://192.168.1.100:38121",
            hmac_secret="abcdefghijklmnopqrstuvwxyz123456",
        )
        events = self.state["provisioning_events"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["node_id"], "node-prov-01")
        self.assertEqual(events[0]["tier"], "pro")

    def test_provision_with_explicit_tenant_id(self):
        result = provision_node_features(
            self.state,
            node_id="node-prov-01",
            node_url="http://192.168.1.100:38121",
            hmac_secret="abcdefghijklmnopqrstuvwxyz123456",
            tenant_id=self.tenant_id,
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["tenant_id"], self.tenant_id)

    def test_provision_unknown_node(self):
        result = provision_node_features(
            self.state,
            node_id="node-nonexistent",
            node_url="http://192.168.1.100:38121",
            hmac_secret="abcdefghijklmnopqrstuvwxyz123456",
        )
        self.assertFalse(result["success"])

    def test_provision_free_tier(self):
        """Free tier has fewer features than pro."""
        free_state: dict = {}
        org = create_organization(free_state, name="Free-Corp", contact_email="free@test.test")
        sub_result = create_subscription(free_state, org_id=org["organization"]["org_id"], plan_tier="free")
        free_state.setdefault("nodes", [])
        free_state["nodes"].append({
            "node_id": "node-free-01",
            "tenant_id": sub_result["tenant"]["tenant_id"],
        })

        result = provision_node_features(
            free_state,
            node_id="node-free-01",
            node_url="http://192.168.1.100:38121",
            hmac_secret="abcdefghijklmnopqrstuvwxyz123456",
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["tier"], "free")
        # Free tier: 2 features + establish-secret + heartbeat = 4 commands
        self.assertEqual(result["tier"], "free")


class DeprovisionTests(unittest.TestCase):
    def test_deprovision_builds_rollback(self):
        state: dict = {}
        result = deprovision_node(
            state,
            node_id="node-x",
            node_url="http://192.168.1.100:38121",
            hmac_secret="secret" * 6,
        )
        self.assertTrue(result["success"])
        self.assertEqual(len(result["commands"]), 1)
        self.assertEqual(result["commands"][0]["action"], "overlay/rollback")

    def test_deprovision_records_event(self):
        state: dict = {}
        deprovision_node(state, node_id="node-y", node_url="http://x:38121")
        events = state["provisioning_events"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["action"], "deprovision")


class HeartbeatTests(unittest.TestCase):
    def test_build_heartbeat(self):
        state: dict = {}
        result = build_heartbeat_for_node(
            state,
            node_id="node-hb-01",
            node_url="http://192.168.1.100:38121",
            hmac_secret="abcdefghijklmnopqrstuvwxyz123456",
            lease_seconds=7200,
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["command"]["action"], "overlay/heartbeat")
        self.assertEqual(result["command"]["body"]["lease_seconds"], 7200)


class ProvisioningStatusTests(unittest.TestCase):
    def test_status_empty(self):
        state: dict = {}
        status = get_node_provisioning_status(state, "node-z")
        self.assertEqual(status["total_events"], 0)
        self.assertIsNone(status["last_event"])

    def test_status_after_provision(self):
        state: dict = {}
        org = create_organization(state, name="Status-Corp", contact_email="s@s.test")
        sub_result = create_subscription(state, org_id=org["organization"]["org_id"], plan_tier="enterprise")
        state.setdefault("nodes", [])
        state["nodes"].append({
            "node_id": "node-status-01",
            "tenant_id": sub_result["tenant"]["tenant_id"],
        })

        provision_node_features(
            state,
            node_id="node-status-01",
            node_url="http://192.168.1.100:38121",
            hmac_secret="abcdefghijklmnopqrstuvwxyz123456",
        )

        status = get_node_provisioning_status(state, "node-status-01")
        self.assertEqual(status["total_events"], 1)
        self.assertIsNotNone(status["last_event"])
        self.assertEqual(status["last_event"]["tier"], "enterprise")
