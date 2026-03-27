from __future__ import annotations

import unittest
from unittest.mock import patch

from nexora_saas.admin_actions import install_app
from nexora_node_sdk.app_profiles import AppProfileError, list_app_profiles, resolve_app_profile, validate_install_request


class AppProfileRegistryTests(unittest.TestCase):
    def test_registry_lists_supported_profiles(self):
        profiles = list_app_profiles()
        app_ids = [profile["app_id"] for profile in profiles]
        self.assertIn("nextcloud", app_ids)
        self.assertIn("jitsi", app_ids)

    def test_unknown_app_requires_manual_review(self):
        with self.assertRaises(AppProfileError):
            resolve_app_profile("custom-app")

    def test_subdomain_only_profile_rejects_non_root_path(self):
        with self.assertRaises(AppProfileError):
            validate_install_request("jitsi", "meet.example.org", "/rooms")

    def test_domain_path_profile_uses_safe_default_path(self):
        request = validate_install_request("roundcube", "mail.example.org", "")
        self.assertEqual(request["path"], "/webmail")
        self.assertEqual(request["profile"]["install_mode"], "domain_path")

    def test_profile_rejects_unexpected_extra_args(self):
        with self.assertRaises(AppProfileError):
            validate_install_request("nextcloud", "cloud.example.org", "/", "foo=bar")


class AdminInstallGuardTests(unittest.TestCase):
    @patch("nexora_saas.admin_actions._ynh")
    def test_install_app_rejects_unknown_profile_before_running_yunohost(self, mock_ynh):
        result = install_app("custom-app", "example.org")
        self.assertFalse(result["success"])
        self.assertIn("not yet covered by a Nexora automation profile", result["error"])
        mock_ynh.assert_not_called()

    @patch("nexora_saas.admin_actions._ynh")
    @patch("nexora_saas.admin_actions.build_install_preflight")
    def test_install_app_includes_profile_metadata_on_success(self, mock_preflight, mock_ynh):
        mock_preflight.return_value = {
            "allowed": True,
            "status": "allowed",
            "warnings": ["no_backup_detected"],
            "profile": {"app_id": "roundcube", "install_mode": "domain_path"},
            "normalized_request": {"args_string": ""},
            "domain": "mail.example.org",
            "path": "/webmail",
        }
        mock_ynh.return_value = {"success": True, "data": {"installed": True}, "error": ""}
        result = install_app("roundcube", "mail.example.org", "")
        self.assertTrue(result["success"])
        self.assertEqual(result["path"], "/webmail")
        self.assertEqual(result["profile"]["app_id"], "roundcube")
        self.assertIn("preflight", result)
        mock_ynh.assert_called_once()
        cmd = mock_ynh.call_args.args[0]
        self.assertEqual(cmd[:3], ["app", "install", "roundcube"])
        self.assertIn("domain=mail.example.org&path=/webmail", cmd)


if __name__ == "__main__":
    unittest.main()
