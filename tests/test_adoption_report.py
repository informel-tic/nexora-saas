from __future__ import annotations

import unittest

from nexora_saas.adoption import build_adoption_report


class AdoptionReportTests(unittest.TestCase):
    def test_happy_path_safe_to_install_when_domain_path_are_clean(self):
        inventory = {
            "apps": {"apps": [{"id": "nextcloud"}]},
            "domains": {"domains": ["example.org"]},
            "app_map": {"example.org": {"/": "nextcloud"}},
            "services": {"services": {"nginx": {"status": "running"}}},
            "certs": {"certificates": {"example.org": {"style": "success"}}},
            "backups": {"archives": ["daily-1"]},
        }
        report = build_adoption_report(inventory, requested_domain="example.org", requested_path="/nexora")
        self.assertTrue(report["safe_to_install"])
        self.assertEqual(report["blocking_collisions"], [])
        self.assertEqual(report["warnings"], [])

    def test_error_path_blocks_on_nginx_unhealthy_and_used_path(self):
        inventory = {
            "apps": {"apps": [{"id": "nextcloud"}]},
            "domains": {"domains": ["example.org"]},
            "app_map": {"example.org": {"/nexora": "wordpress"}},
            "services": {"services": {"nginx": {"status": "failed"}}},
            "certs": {"certificates": {"example.org": {"style": "warning"}}},
        }
        report = build_adoption_report(inventory, requested_domain="example.org", requested_path="/nexora")
        blocking_types = {item["type"] for item in report["blocking_collisions"]}
        self.assertFalse(report["safe_to_install"])
        self.assertIn("path-already-used", blocking_types)
        self.assertIn("nginx-unhealthy", blocking_types)
        warning_types = {item["type"] for item in report["warnings"]}
        self.assertIn("certificate-not-ready", warning_types)

    def test_edge_path_detects_nested_prefix_conflict(self):
        inventory = {
            "apps": {"apps": [{"id": "nextcloud"}]},
            "domains": {"domains": ["example.org"]},
            "app_map": {"example.org": {"/nexora/admin": "custom-app"}},
            "services": {"services": {"nginx": {"status": "running"}}},
            "certs": {"certificates": {}},
        }
        report = build_adoption_report(inventory, requested_domain="example.org", requested_path="nexora")
        collision_types = {item["type"] for item in report["collisions"]}
        self.assertIn("path-prefix-conflict", collision_types)
        self.assertFalse(report["safe_to_install"])
        self.assertEqual(report["suggested_path"], "/nexora")
        warning_types = {item["type"] for item in report["warnings"]}
        self.assertIn("missing-domain-certificate", warning_types)


if __name__ == "__main__":
    unittest.main()
