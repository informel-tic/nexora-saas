from __future__ import annotations

import unittest
from unittest.mock import patch

from nexora_saas.admin_actions import deploy_blueprint, install_app, upgrade_app
from nexora_saas.preflight import build_blueprint_preflight, build_install_preflight, build_upgrade_preflight


class InstallPreflightTests(unittest.TestCase):
    @patch("nexora_saas.preflight.yh_adapter.ynh_permissions", return_value={"permissions": {}})
    @patch("nexora_saas.preflight.yh_adapter.ynh_services", return_value={"services": {}})
    @patch("nexora_saas.preflight.yh_adapter.ynh_backups", return_value={"archives": []})
    @patch("nexora_saas.preflight.yh_adapter.ynh_app_map", return_value={})
    @patch("nexora_saas.preflight.yh_adapter.ynh_version", return_value={"yunohost": {"version": "12.1.2"}})
    def test_install_preflight_blocks_unknown_profile(self, *_mocks):
        report = build_install_preflight("custom-app", "example.org")
        self.assertFalse(report["allowed"])
        self.assertEqual(report["status"], "blocked")
        self.assertIn("not yet covered by a Nexora automation profile", report["blocking_issues"][0])

    @patch("nexora_saas.preflight.yh_adapter.ynh_permissions", return_value={"permissions": {}})
    @patch("nexora_saas.preflight.yh_adapter.ynh_services", return_value={"services": {}})
    @patch("nexora_saas.preflight.yh_adapter.ynh_backups", return_value={"archives": []})
    @patch("nexora_saas.preflight.yh_adapter.ynh_app_map", return_value={})
    @patch("nexora_saas.preflight.yh_adapter.ynh_version", return_value={"yunohost": {"version": "12.2.0"}})
    def test_install_preflight_blocks_experimental_minor_for_mutations(self, *_mocks):
        report = build_install_preflight("nextcloud", "cloud.example.org")
        self.assertFalse(report["allowed"])
        self.assertEqual(report["status"], "blocked")
        self.assertTrue(report["manual_review_required"])
        self.assertTrue(any(issue.startswith("compatibility:") for issue in report["blocking_issues"]))

    @patch("nexora_saas.preflight.yh_adapter.ynh_permissions", return_value={"permissions": {}})
    @patch("nexora_saas.preflight.yh_adapter.ynh_services", return_value={"services": {}})
    @patch("nexora_saas.preflight.yh_adapter.ynh_backups", return_value={"archives": ["daily-1"]})
    @patch("nexora_saas.preflight.yh_adapter.ynh_app_map", return_value={"example.org": {"/": "nextcloud"}})
    @patch("nexora_saas.preflight.yh_adapter.ynh_version", return_value={"yunohost": {"version": "12.1.2"}})
    def test_install_preflight_detects_path_collision(self, *_mocks):
        report = build_install_preflight("nextcloud", "example.org")
        self.assertFalse(report["allowed"])
        self.assertIn("path_already_used:example.org/->nextcloud", report["blocking_issues"])
        self.assertEqual(report["suggested_changes"][0]["reason"], "avoid_existing_path_collision")

    @patch("nexora_saas.preflight.yh_adapter.ynh_permissions", return_value={"permissions": {"blog.main": {"allowed": ["visitors"]}}})
    @patch("nexora_saas.preflight.yh_adapter.ynh_services", return_value={"services": {"nginx": {"status": "failed"}}})
    @patch("nexora_saas.preflight.yh_adapter.ynh_backups", return_value={"archives": []})
    @patch("nexora_saas.preflight.yh_adapter.ynh_app_map", return_value={})
    @patch("nexora_saas.preflight.yh_adapter.ynh_version", return_value={"yunohost": {"version": "12.1.2"}})
    def test_install_preflight_surfaces_operational_warnings(self, *_mocks):
        report = build_install_preflight("roundcube", "mail.example.org", "")
        self.assertTrue(report["allowed"])
        self.assertEqual(report["status"], "allowed")
        self.assertIn("no_backup_detected", report["warnings"])
        self.assertIn("unhealthy_services:nginx", report["warnings"])
        self.assertIn("public_permissions:blog.main", report["warnings"])


class UpgradeAndBlueprintPreflightTests(unittest.TestCase):
    @patch("nexora_saas.preflight.yh_adapter.ynh_services", return_value={"services": {}})
    @patch("nexora_saas.preflight.yh_adapter.ynh_backups", return_value={"archives": []})
    @patch("nexora_saas.preflight.yh_adapter.ynh_version", return_value={"yunohost": {"version": "12.1.2"}})
    def test_upgrade_preflight_requires_backup(self, *_mocks):
        report = build_upgrade_preflight("nextcloud")
        self.assertFalse(report["allowed"])
        self.assertIn("pre_upgrade_backup_required", report["blocking_issues"])

    @patch("nexora_saas.preflight.yh_adapter.ynh_permissions", return_value={"permissions": {}})
    @patch("nexora_saas.preflight.yh_adapter.ynh_services", return_value={"services": {}})
    @patch("nexora_saas.preflight.yh_adapter.ynh_backups", return_value={"archives": ["daily-1"]})
    @patch("nexora_saas.preflight.yh_adapter.ynh_app_map", return_value={})
    @patch("nexora_saas.preflight.yh_adapter.ynh_version", return_value={"yunohost": {"version": "12.1.1"}})
    def test_blueprint_preflight_marks_supported_minor_for_manual_review(self, *_mocks):
        report = build_blueprint_preflight("pme", "example.org", ["nextcloud", "roundcube"])
        self.assertFalse(report["allowed"])
        self.assertTrue(report["manual_review_required"])
        self.assertTrue(any(issue.startswith("compatibility:") for issue in report["blocking_issues"]))


class AdminActionPreflightGuardsTests(unittest.TestCase):
    @patch("nexora_saas.admin_actions._ynh")
    @patch("nexora_saas.admin_actions.build_install_preflight")
    def test_install_app_stops_before_yunohost_when_preflight_blocks(self, mock_preflight, mock_ynh):
        mock_preflight.return_value = {
            "allowed": False,
            "status": "blocked",
            "blocking_issues": ["path_already_used:example.org/->nextcloud"],
            "warnings": ["no_backup_detected"],
            "profile": {"app_id": "nextcloud", "automation": "supported"},
            "domain": "example.org",
            "path": "/",
        }
        result = install_app("nextcloud", "example.org")
        self.assertFalse(result["success"])
        self.assertIn("path_already_used", result["error"])
        self.assertIn("preflight", result)
        mock_ynh.assert_not_called()

    @patch("nexora_saas.admin_actions._ynh")
    @patch("nexora_saas.admin_actions.build_upgrade_preflight")
    def test_upgrade_app_stops_before_yunohost_when_preflight_blocks(self, mock_preflight, mock_ynh):
        mock_preflight.return_value = {
            "allowed": False,
            "status": "blocked",
            "blocking_issues": ["pre_upgrade_backup_required"],
            "warnings": [],
        }
        result = upgrade_app("nextcloud")
        self.assertFalse(result["success"])
        self.assertIn("pre_upgrade_backup_required", result["error"])
        mock_ynh.assert_not_called()

    @patch("nexora_saas.admin_actions._ynh")
    @patch("nexora_saas.admin_actions.resolve_blueprint_plan")
    def test_deploy_blueprint_stops_before_install_loop_when_preflight_blocks(self, mock_plan, mock_ynh):
        mock_plan.return_value = {
            "allowed": False,
            "status": "manual_review_required",
            "blocking_issues": ["compatibility:status_not_allowed:supported"],
            "warnings": [],
        }
        result = deploy_blueprint("pme", "example.org", ["nextcloud"])
        self.assertFalse(result["success"])
        self.assertIn("compatibility:", result["error"])
        mock_ynh.assert_not_called()


if __name__ == "__main__":
    unittest.main()
