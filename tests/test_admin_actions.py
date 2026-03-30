"""Tests for nexora_saas.admin_actions — admin-level YunoHost operations."""

from __future__ import annotations

import unittest
from unittest.mock import patch


def _ynh_ok(data=None):
    return {"success": True, "data": data or {}, "error": ""}


def _ynh_fail(error="command failed"):
    return {"success": False, "data": {}, "error": error}


def _preflight_ok(app_id="nextcloud", domain="example.tld", path="/"):
    return {
        "allowed": True,
        "status": "ok",
        "blocking_issues": [],
        "warnings": [],
        "manual_review_required": False,
        "domain": domain,
        "path": path,
        "profile": {"app_id": app_id, "automation": "fully_automated"},
        "normalized_request": {"args_string": ""},
    }


def _preflight_blocked():
    return {
        "allowed": False,
        "status": "blocked",
        "blocking_issues": ["disk_too_small"],
        "warnings": [],
        "manual_review_required": False,
        "domain": "example.tld",
        "path": "/",
    }


class TestInstallApp(unittest.TestCase):
    def test_install_rejected_when_preflight_blocked(self):
        from nexora_saas.admin_actions import install_app

        with patch("nexora_saas.admin_actions.build_install_preflight", return_value=_preflight_blocked()), \
             patch("nexora_saas.admin_actions._audit_log"):
            result = install_app("nextcloud", "example.tld")

        self.assertFalse(result["success"])
        self.assertIn("disk_too_small", result["error"])
        self.assertIsNone(result["rollback"])
        self.assertEqual(result["action"], "install_app")

    def test_install_returns_rollback_hint_on_success(self):
        from nexora_saas.admin_actions import install_app

        with patch("nexora_saas.admin_actions.build_install_preflight", return_value=_preflight_ok()), \
             patch("nexora_saas.admin_actions._ynh", return_value=_ynh_ok()), \
             patch("nexora_saas.admin_actions._audit_log"):
            result = install_app("nextcloud", "example.tld")

        self.assertTrue(result["success"])
        self.assertIsNotNone(result["rollback"])
        self.assertIn("nextcloud", result["rollback"])

    def test_install_no_rollback_on_failure(self):
        from nexora_saas.admin_actions import install_app

        with patch("nexora_saas.admin_actions.build_install_preflight", return_value=_preflight_ok()), \
             patch("nexora_saas.admin_actions._ynh", return_value=_ynh_fail()), \
             patch("nexora_saas.admin_actions._audit_log"):
            result = install_app("nextcloud", "example.tld")

        self.assertFalse(result["success"])
        self.assertIsNone(result["rollback"])

    def test_install_includes_label(self):
        from nexora_saas.admin_actions import install_app

        captured_cmd = []

        def fake_ynh(cmd, timeout=300):
            captured_cmd.extend(cmd)
            return _ynh_ok()

        with patch("nexora_saas.admin_actions.build_install_preflight", return_value=_preflight_ok()), \
             patch("nexora_saas.admin_actions._ynh", side_effect=fake_ynh), \
             patch("nexora_saas.admin_actions._audit_log"):
            install_app("nextcloud", "example.tld", label="My Cloud")

        self.assertIn("--label", captured_cmd)
        self.assertIn("My Cloud", captured_cmd)

    def test_install_preflight_included_in_result(self):
        from nexora_saas.admin_actions import install_app

        pf = _preflight_ok()
        with patch("nexora_saas.admin_actions.build_install_preflight", return_value=pf), \
             patch("nexora_saas.admin_actions._ynh", return_value=_ynh_ok()), \
             patch("nexora_saas.admin_actions._audit_log"):
            result = install_app("nextcloud", "example.tld")

        self.assertEqual(result["preflight"], pf)


class TestRemoveApp(unittest.TestCase):
    def test_remove_success(self):
        from nexora_saas.admin_actions import remove_app

        with patch("nexora_saas.admin_actions._ynh", return_value=_ynh_ok()), \
             patch("nexora_saas.admin_actions._audit_log"):
            result = remove_app("nextcloud")

        self.assertTrue(result["success"])
        self.assertEqual(result["action"], "remove_app")
        self.assertEqual(result["app"], "nextcloud")
        self.assertIsNotNone(result["rollback"])

    def test_remove_failure(self):
        from nexora_saas.admin_actions import remove_app

        with patch("nexora_saas.admin_actions._ynh", return_value=_ynh_fail("app not found")), \
             patch("nexora_saas.admin_actions._audit_log"):
            result = remove_app("nonexistent")

        self.assertFalse(result["success"])
        self.assertIsNone(result["rollback"])
        self.assertIn("app not found", result["error"])


class TestUpgradeApp(unittest.TestCase):
    def _preflight_upgrade_ok(self):
        return {
            "allowed": True,
            "status": "ok",
            "blocking_issues": [],
            "warnings": [],
        }

    def _preflight_upgrade_blocked(self):
        return {
            "allowed": False,
            "status": "blocked",
            "blocking_issues": ["maintenance_window_required"],
            "warnings": [],
        }

    def test_upgrade_blocked_when_preflight_fails(self):
        from nexora_saas.admin_actions import upgrade_app

        with patch("nexora_saas.admin_actions.build_upgrade_preflight", return_value=self._preflight_upgrade_blocked()), \
             patch("nexora_saas.admin_actions._audit_log"):
            result = upgrade_app("nextcloud")

        self.assertFalse(result["success"])
        self.assertIn("maintenance_window_required", result["error"])
        self.assertIsNone(result["rollback"])

    def test_upgrade_success_single_app(self):
        from nexora_saas.admin_actions import upgrade_app

        with patch("nexora_saas.admin_actions.build_upgrade_preflight", return_value=self._preflight_upgrade_ok()), \
             patch("nexora_saas.admin_actions._ynh", return_value=_ynh_ok()), \
             patch("nexora_saas.admin_actions._audit_log"):
            result = upgrade_app("nextcloud")

        self.assertTrue(result["success"])
        self.assertEqual(result["app"], "nextcloud")
        self.assertIn("rollback", result)

    def test_upgrade_all_apps(self):
        from nexora_saas.admin_actions import upgrade_app

        with patch("nexora_saas.admin_actions.build_upgrade_preflight", return_value=self._preflight_upgrade_ok()), \
             patch("nexora_saas.admin_actions._ynh", return_value=_ynh_ok()), \
             patch("nexora_saas.admin_actions._audit_log"):
            result = upgrade_app()  # empty app_id = all

        self.assertEqual(result["app"], "all")

    def test_upgrade_failure_returns_error(self):
        from nexora_saas.admin_actions import upgrade_app

        with patch("nexora_saas.admin_actions.build_upgrade_preflight", return_value=self._preflight_upgrade_ok()), \
             patch("nexora_saas.admin_actions._ynh", return_value=_ynh_fail("network error")), \
             patch("nexora_saas.admin_actions._audit_log"):
            result = upgrade_app("nextcloud")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "network error")


class TestRestoreBackup(unittest.TestCase):
    def test_restore_success(self):
        from nexora_saas.admin_actions import restore_backup

        with patch("nexora_saas.admin_actions._ynh", return_value=_ynh_ok()), \
             patch("nexora_saas.admin_actions._audit_log"):
            result = restore_backup("20240101-backup")

        self.assertTrue(result["success"])
        self.assertEqual(result["name"], "20240101-backup")
        self.assertEqual(result["action"], "restore_backup")

    def test_restore_failure(self):
        from nexora_saas.admin_actions import restore_backup

        with patch("nexora_saas.admin_actions._ynh", return_value=_ynh_fail("backup not found")), \
             patch("nexora_saas.admin_actions._audit_log"):
            result = restore_backup("missing-backup")

        self.assertFalse(result["success"])
        self.assertIn("backup not found", result["error"])

    def test_restore_with_apps_and_system(self):
        from nexora_saas.admin_actions import restore_backup

        captured_cmd = []

        def fake_ynh(cmd, timeout=300):
            captured_cmd.extend(cmd)
            return _ynh_ok()

        with patch("nexora_saas.admin_actions._ynh", side_effect=fake_ynh), \
             patch("nexora_saas.admin_actions._audit_log"):
            restore_backup("20240101-backup", apps="nextcloud gitea", system="ldap")

        self.assertIn("--apps", captured_cmd)
        self.assertIn("--system", captured_cmd)


class TestYnhHelper(unittest.TestCase):
    def test_ynh_helper_returns_success_false_on_timeout(self):
        from nexora_saas.admin_actions import _ynh
        import subprocess

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 300)):
            result = _ynh(["app", "list"])

        self.assertFalse(result["success"])
        self.assertIn("Timeout", result["error"])

    def test_ynh_helper_returns_success_false_on_exception(self):
        from nexora_saas.admin_actions import _ynh

        with patch("subprocess.run", side_effect=RuntimeError("unexpected")):
            result = _ynh(["app", "list"])

        self.assertFalse(result["success"])

    def test_ynh_helper_parses_json_output(self):
        import json
        import subprocess
        from nexora_saas.admin_actions import _ynh

        proc = subprocess.CompletedProcess([], 0, stdout=json.dumps({"apps": []}), stderr="")
        with patch("subprocess.run", return_value=proc):
            result = _ynh(["app", "list"])

        self.assertTrue(result["success"])
        self.assertIn("apps", result["data"])


class TestAuditLog(unittest.TestCase):
    def test_audit_log_does_not_raise_on_permission_error(self):
        from nexora_saas.admin_actions import _audit_log
        from unittest.mock import mock_open

        with patch("pathlib.Path.mkdir", side_effect=PermissionError("no access")):
            # Should silently handle the error
            _audit_log("test_action", {"details": "test"})


if __name__ == "__main__":
    unittest.main()
