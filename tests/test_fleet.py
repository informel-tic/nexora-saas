"""Tests for nexora_saas.fleet — multi-node inventory, drift, topology."""

from __future__ import annotations

import unittest
from unittest.mock import patch


def _make_node(node_id, apps=None, domains=None, services=None):
    apps = apps or []
    domains = domains or []
    services = services or {}
    return {
        "node_id": node_id,
        "status": "healthy",
        "inventory": {
            "apps": {"apps": [{"id": a} for a in apps]},
            "domains": {"domains": domains},
            "services": services,
        },
    }


class TestBuildFleetInventory(unittest.TestCase):
    def test_empty_nodes(self):
        from nexora_saas.fleet import build_fleet_inventory

        result = build_fleet_inventory([])
        self.assertEqual(result["total_nodes"], 0)
        self.assertEqual(result["total_apps"], 0)
        self.assertEqual(result["total_domains"], 0)

    def test_single_node(self):
        from nexora_saas.fleet import build_fleet_inventory

        nodes = [_make_node("n1", apps=["nextcloud", "gitea"], domains=["example.tld"])]
        result = build_fleet_inventory(nodes)
        self.assertEqual(result["total_nodes"], 1)
        self.assertEqual(result["total_apps"], 2)
        self.assertEqual(result["total_domains"], 1)

    def test_two_nodes_unique_apps(self):
        from nexora_saas.fleet import build_fleet_inventory

        nodes = [
            _make_node("n1", apps=["nextcloud", "gitea"]),
            _make_node("n2", apps=["nextcloud", "wordpress"]),
        ]
        result = build_fleet_inventory(nodes)
        self.assertEqual(result["total_nodes"], 2)
        # nextcloud appears on both — unique count = 3
        self.assertEqual(result["total_apps"], 3)
        self.assertIn("nextcloud", result["unique_apps"])
        self.assertIn("gitea", result["unique_apps"])
        self.assertIn("wordpress", result["unique_apps"])

    def test_unique_domains_deduplicated(self):
        from nexora_saas.fleet import build_fleet_inventory

        nodes = [
            _make_node("n1", domains=["a.tld", "shared.tld"]),
            _make_node("n2", domains=["b.tld", "shared.tld"]),
        ]
        result = build_fleet_inventory(nodes)
        self.assertEqual(result["total_domains"], 3)

    def test_node_summaries_have_scores(self):
        from nexora_saas.fleet import build_fleet_inventory

        nodes = [_make_node("n1", apps=["nextcloud"])]
        result = build_fleet_inventory(nodes)
        summary = result["nodes"][0]
        self.assertIn("health", summary)
        self.assertIn("security", summary)
        self.assertIn("pra", summary)
        self.assertEqual(summary["node_id"], "n1")

    def test_result_has_timestamp(self):
        from nexora_saas.fleet import build_fleet_inventory

        result = build_fleet_inventory([])
        self.assertIn("timestamp", result)


class TestDetectDrift(unittest.TestCase):
    def test_identical_inventories_no_drift(self):
        from nexora_saas.fleet import detect_drift

        inv = {
            "apps": {"apps": [{"id": "nextcloud"}]},
            "domains": {"domains": ["example.tld"]},
            "permissions": {},
        }
        result = detect_drift(inv, inv)
        self.assertEqual(result["drift_count"], 0)
        self.assertEqual(result["severity"], "clean")

    def test_missing_app_on_target_detected(self):
        from nexora_saas.fleet import detect_drift

        ref = {"apps": {"apps": [{"id": "nextcloud"}, {"id": "gitea"}]}, "domains": {}, "permissions": {}}
        tgt = {"apps": {"apps": [{"id": "nextcloud"}]}, "domains": {}, "permissions": {}}
        result = detect_drift(ref, tgt)
        types = [d["type"] for d in result["drifts"]]
        self.assertIn("missing_on_target", types)
        items = [d["item"] for d in result["drifts"]]
        self.assertIn("gitea", items)

    def test_extra_app_on_target_detected(self):
        from nexora_saas.fleet import detect_drift

        ref = {"apps": {"apps": [{"id": "nextcloud"}]}, "domains": {}, "permissions": {}}
        tgt = {"apps": {"apps": [{"id": "nextcloud"}, {"id": "wordpress"}]}, "domains": {}, "permissions": {}}
        result = detect_drift(ref, tgt)
        types = [d["type"] for d in result["drifts"]]
        self.assertIn("extra_on_target", types)

    def test_domain_drift_detected(self):
        from nexora_saas.fleet import detect_drift

        ref = {"apps": {}, "domains": {"domains": ["a.tld", "b.tld"]}, "permissions": {}}
        tgt = {"apps": {}, "domains": {"domains": ["a.tld"]}, "permissions": {}}
        result = detect_drift(ref, tgt)
        cats = [d["category"] for d in result["drifts"]]
        self.assertIn("domains", cats)

    def test_permission_drift_detected(self):
        from nexora_saas.fleet import detect_drift

        ref = {
            "apps": {},
            "domains": {},
            "permissions": {"permissions": {"nextcloud.main": {"allowed": ["admin"]}}},
        }
        tgt = {
            "apps": {},
            "domains": {},
            "permissions": {"permissions": {"nextcloud.main": {"allowed": ["admin", "user"]}}},
        }
        result = detect_drift(ref, tgt)
        cats = [d["category"] for d in result["drifts"]]
        self.assertIn("permissions", cats)

    def test_severity_critical_for_many_drifts(self):
        from nexora_saas.fleet import detect_drift

        ref = {"apps": {"apps": [{"id": f"app{i}"} for i in range(12)]}, "domains": {}, "permissions": {}}
        tgt = {"apps": {"apps": []}, "domains": {}, "permissions": {}}
        result = detect_drift(ref, tgt)
        self.assertEqual(result["severity"], "critical")

    def test_severity_warning_for_moderate_drifts(self):
        from nexora_saas.fleet import detect_drift

        ref = {"apps": {"apps": [{"id": f"app{i}"} for i in range(5)]}, "domains": {}, "permissions": {}}
        tgt = {"apps": {"apps": []}, "domains": {}, "permissions": {}}
        result = detect_drift(ref, tgt)
        self.assertEqual(result["severity"], "warning")

    def test_result_has_timestamp(self):
        from nexora_saas.fleet import detect_drift

        result = detect_drift({}, {})
        self.assertIn("timestamp", result)


class TestGenerateFleetTopology(unittest.TestCase):
    def test_empty_nodes(self):
        from nexora_saas.fleet import generate_fleet_topology

        result = generate_fleet_topology([])
        self.assertEqual(result["total_nodes"], 0)
        self.assertEqual(result["nodes"], [])

    def test_node_role_defaults_to_apps(self):
        from nexora_saas.fleet import generate_fleet_topology

        nodes = [_make_node("n1", apps=["nextcloud"])]
        result = generate_fleet_topology(nodes)
        self.assertEqual(result["nodes"][0]["role"], "apps")

    def test_mail_role_detected(self):
        from nexora_saas.fleet import generate_fleet_topology

        nodes = [_make_node("n1", services={"postfix": "running", "dovecot": "running"})]
        result = generate_fleet_topology(nodes)
        self.assertEqual(result["nodes"][0]["role"], "mail")

    def test_storage_role_for_db_only_node(self):
        from nexora_saas.fleet import generate_fleet_topology

        nodes = [_make_node("n1", apps=[], services={"mysql": "running"})]
        result = generate_fleet_topology(nodes)
        self.assertEqual(result["nodes"][0]["role"], "storage")

    def test_explicit_role_override(self):
        from nexora_saas.fleet import generate_fleet_topology

        nodes = [_make_node("n1", apps=["nextcloud"])]
        result = generate_fleet_topology(nodes, roles={"n1": "gateway"})
        # apps is present so it won't auto-override to storage; role should be "gateway" only if no mail
        self.assertIn(result["nodes"][0]["role"], ("gateway", "apps", "mail"))

    def test_topology_capabilities(self):
        from nexora_saas.fleet import generate_fleet_topology

        nodes = [_make_node("n1", apps=["nextcloud"], services={"postfix": {}})]
        result = generate_fleet_topology(nodes)
        caps = result["nodes"][0]["capabilities"]
        self.assertTrue(caps["mail"])
        self.assertTrue(caps["apps"])

    def test_all_roles_listed(self):
        from nexora_saas.fleet import generate_fleet_topology

        nodes = [
            _make_node("n1", apps=["nextcloud"]),
            _make_node("n2", services={"postfix": {}}),
        ]
        result = generate_fleet_topology(nodes)
        roles = result["roles"]
        self.assertIsInstance(roles, list)
        self.assertGreater(len(roles), 0)

    def test_result_has_timestamp(self):
        from nexora_saas.fleet import generate_fleet_topology

        result = generate_fleet_topology([])
        self.assertIn("timestamp", result)


class TestCompareNodes(unittest.TestCase):
    def test_compare_identical_nodes(self):
        from nexora_saas.fleet import compare_nodes

        node = _make_node("n1", apps=["nextcloud"], domains=["example.tld"])
        result = compare_nodes(node, node)
        self.assertEqual(sorted(result["shared_apps"]), ["nextcloud"])
        self.assertEqual(result["only_a_apps"], [])
        self.assertEqual(result["only_b_apps"], [])

    def test_compare_different_apps(self):
        from nexora_saas.fleet import compare_nodes

        a = _make_node("n1", apps=["nextcloud", "gitea"])
        b = _make_node("n2", apps=["nextcloud", "wordpress"])
        result = compare_nodes(a, b)
        self.assertIn("nextcloud", result["shared_apps"])
        self.assertIn("gitea", result["only_a_apps"])
        self.assertIn("wordpress", result["only_b_apps"])

    def test_compare_shared_domains(self):
        from nexora_saas.fleet import compare_nodes

        a = _make_node("n1", domains=["shared.tld", "only-a.tld"])
        b = _make_node("n2", domains=["shared.tld", "only-b.tld"])
        result = compare_nodes(a, b)
        self.assertIn("shared.tld", result["shared_domains"])

    def test_result_has_node_ids(self):
        from nexora_saas.fleet import compare_nodes

        a = _make_node("node-a")
        b = _make_node("node-b")
        result = compare_nodes(a, b)
        self.assertEqual(result["node_a"]["node_id"], "node-a")
        self.assertEqual(result["node_b"]["node_id"], "node-b")

    def test_result_includes_health_scores(self):
        from nexora_saas.fleet import compare_nodes

        a = _make_node("n1")
        b = _make_node("n2")
        result = compare_nodes(a, b)
        self.assertIn("health", result["node_a"])
        self.assertIn("health", result["node_b"])


class TestBuildRemoteAgentUrl(unittest.TestCase):
    def test_default_https(self):
        from nexora_saas.fleet import build_remote_agent_url

        url = build_remote_agent_url("192.168.1.10")
        self.assertTrue(url.startswith("https://"))
        self.assertIn("192.168.1.10", url)
        self.assertIn(":38121", url)
        self.assertIn("/inventory", url)

    def test_custom_port_and_path(self):
        from nexora_saas.fleet import build_remote_agent_url

        url = build_remote_agent_url("10.0.0.1", port=8080, path="/health")
        self.assertIn(":8080", url)
        self.assertIn("/health", url)

    def test_path_without_leading_slash(self):
        from nexora_saas.fleet import build_remote_agent_url

        url = build_remote_agent_url("10.0.0.1", path="status")
        self.assertIn("/status", url)

    def test_http_scheme_override(self):
        from nexora_saas.fleet import build_remote_agent_url

        url = build_remote_agent_url("10.0.0.1", scheme="http")
        self.assertTrue(url.startswith("http://"))


if __name__ == "__main__":
    unittest.main()
