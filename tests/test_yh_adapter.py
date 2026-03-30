"""Tests for nexora_node_sdk.yh_adapter — YunoHost CLI adapter."""

from __future__ import annotations

import json
import subprocess
import unittest
from unittest.mock import patch


def _completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


class TestRunHelper(unittest.TestCase):
    def test_run_returns_completed_process_on_success(self):
        from nexora_node_sdk.yh_adapter import _run

        with patch("subprocess.run", return_value=_completed(0, "ok")) as mock_run:
            result = _run(["echo", "ok"])
            self.assertEqual(result.returncode, 0)
            mock_run.assert_called_once()

    def test_run_returns_127_when_file_not_found(self):
        from nexora_node_sdk.yh_adapter import _run

        with patch("subprocess.run", side_effect=FileNotFoundError("no such file")):
            result = _run(["missing_binary"])
            self.assertEqual(result.returncode, 127)

    def test_run_returns_124_on_timeout(self):
        from nexora_node_sdk.yh_adapter import _run

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 30)):
            result = _run(["slow_cmd"], timeout=30)
            self.assertEqual(result.returncode, 124)
            self.assertIn("Timeout", result.stderr)


class TestRunJson(unittest.TestCase):
    def test_run_json_parses_valid_json(self):
        from nexora_node_sdk.yh_adapter import _run_json

        payload = {"apps": ["nextcloud"]}
        with patch("nexora_node_sdk.yh_adapter._run", return_value=_completed(0, json.dumps(payload))):
            result = _run_json(["yunohost", "app", "list"])
            self.assertEqual(result, payload)

    def test_run_json_returns_error_dict_on_nonzero(self):
        from nexora_node_sdk.yh_adapter import _run_json

        with patch("nexora_node_sdk.yh_adapter._run", return_value=_completed(1, "", "something went wrong")):
            result = _run_json(["yunohost", "oops"])
            self.assertIn("_error", result)

    def test_run_json_returns_error_dict_on_invalid_json(self):
        from nexora_node_sdk.yh_adapter import _run_json

        with patch("nexora_node_sdk.yh_adapter._run", return_value=_completed(0, "not-json")):
            result = _run_json(["yunohost", "cmd"])
            self.assertIn("_raw", result)

    def test_run_json_returns_empty_dict_on_empty_output(self):
        from nexora_node_sdk.yh_adapter import _run_json

        with patch("nexora_node_sdk.yh_adapter._run", return_value=_completed(0, "")):
            result = _run_json(["yunohost", "cmd"])
            self.assertEqual(result, {})


class TestYnhFunctions(unittest.TestCase):
    def _patch(self, payload, rc=0):
        stdout = json.dumps(payload) if rc == 0 else ""
        return patch("nexora_node_sdk.yh_adapter._run", return_value=_completed(rc, stdout, "err" if rc else ""))

    def test_ynh_version(self):
        from nexora_node_sdk.yh_adapter import ynh_version

        with self._patch({"yunohost": "11.0"}):
            result = ynh_version()
            self.assertNotIn("_error", result)

    def test_ynh_apps_returns_dict(self):
        from nexora_node_sdk.yh_adapter import ynh_apps

        with self._patch({"apps": [{"id": "nextcloud"}]}):
            result = ynh_apps()
            self.assertIn("apps", result)

    def test_ynh_domains(self):
        from nexora_node_sdk.yh_adapter import ynh_domains

        with self._patch({"domains": ["example.tld"]}):
            result = ynh_domains()
            self.assertIn("domains", result)

    def test_ynh_services(self):
        from nexora_node_sdk.yh_adapter import ynh_services

        with self._patch({"nginx": {"status": "running"}}):
            result = ynh_services()
            self.assertIn("nginx", result)

    def test_ynh_backups(self):
        from nexora_node_sdk.yh_adapter import ynh_backups

        with self._patch({"archives": []}):
            result = ynh_backups()
            self.assertIn("archives", result)

    def test_ynh_certs(self):
        from nexora_node_sdk.yh_adapter import ynh_certs

        with self._patch({"certificates": {}}):
            result = ynh_certs()
            self.assertNotIn("_error", result)

    def test_ynh_permissions(self):
        from nexora_node_sdk.yh_adapter import ynh_permissions

        with self._patch({"permissions": {}}):
            result = ynh_permissions()
            self.assertNotIn("_error", result)

    def test_ynh_diagnosis(self):
        from nexora_node_sdk.yh_adapter import ynh_diagnosis

        with self._patch({"checks": []}):
            result = ynh_diagnosis()
            self.assertNotIn("_error", result)

    def test_ynh_app_map(self):
        from nexora_node_sdk.yh_adapter import ynh_app_map

        with self._patch({"map": {}}):
            result = ynh_app_map()
            self.assertNotIn("_error", result)

    def test_ynh_settings(self):
        from nexora_node_sdk.yh_adapter import ynh_settings

        with self._patch({"settings": {}}):
            result = ynh_settings()
            self.assertNotIn("_error", result)


class TestSystemctlStatus(unittest.TestCase):
    def test_returns_expected_keys(self):
        from nexora_node_sdk.yh_adapter import systemctl_status

        active_proc = _completed(0, "active")
        props_proc = _completed(0, "ActiveState=active\nSubState=running\nDescription=NGINX\nMainPID=1234\nLoadState=loaded\n")

        with patch("nexora_node_sdk.yh_adapter._run", side_effect=[active_proc, props_proc]):
            result = systemctl_status("nginx")
            self.assertEqual(result["name"], "nginx")
            self.assertEqual(result["active"], "active")
            self.assertIn("description", result)


class TestSystemctlListUnits(unittest.TestCase):
    def test_parses_json_output(self):
        from nexora_node_sdk.yh_adapter import systemctl_list_units

        json_output = json.dumps([
            {"unit": "nginx.service", "active": "active", "sub": "running", "description": "NGINX", "load": "loaded"}
        ])
        with patch("nexora_node_sdk.yh_adapter._run", return_value=_completed(0, json_output)):
            result = systemctl_list_units("active")
            self.assertIn("nginx", result)
            self.assertEqual(result["nginx"]["status"], "active")

    def test_falls_back_to_text_parsing(self):
        from nexora_node_sdk.yh_adapter import systemctl_list_units

        text_output = "  nginx.service  loaded active running NGINX web server\n"
        # First call fails JSON parse (non-json stdout), second succeeds
        bad_json = _completed(0, "not-json")
        text_result = _completed(0, text_output)
        with patch("nexora_node_sdk.yh_adapter._run", side_effect=[bad_json, text_result]):
            result = systemctl_list_units("active")
            self.assertIn("nginx", result)


class TestYnhAppCatalogFiltered(unittest.TestCase):
    def _mock_catalog(self):
        return {
            "apps": {
                "nextcloud": {"name": "Nextcloud", "category": "productivity", "tags": ["files"]},
                "wordpress": {"name": "WordPress", "category": "cms", "tags": ["blog"]},
                "gitea": {"name": "Gitea", "category": "devtools", "tags": ["git"]},
            }
        }

    def test_returns_empty_on_catalog_error(self):
        from nexora_node_sdk.yh_adapter import ynh_app_catalog_filtered

        with patch("nexora_node_sdk.yh_adapter.ynh_app_catalog", return_value={"_error": "unreachable"}):
            result = ynh_app_catalog_filtered()
            self.assertEqual(result, [])

    def test_no_filter_returns_all(self):
        from nexora_node_sdk.yh_adapter import ynh_app_catalog_filtered

        with patch("nexora_node_sdk.yh_adapter.ynh_app_catalog", return_value=self._mock_catalog()):
            result = ynh_app_catalog_filtered()
            self.assertEqual(len(result), 3)

    def test_category_filter(self):
        from nexora_node_sdk.yh_adapter import ynh_app_catalog_filtered

        with patch("nexora_node_sdk.yh_adapter.ynh_app_catalog", return_value=self._mock_catalog()):
            result = ynh_app_catalog_filtered(category="cms")
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["id"], "wordpress")

    def test_query_filter(self):
        from nexora_node_sdk.yh_adapter import ynh_app_catalog_filtered

        with patch("nexora_node_sdk.yh_adapter.ynh_app_catalog", return_value=self._mock_catalog()):
            result = ynh_app_catalog_filtered(query="gitea")
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["id"], "gitea")

    def test_handles_list_format(self):
        from nexora_node_sdk.yh_adapter import ynh_app_catalog_filtered

        list_catalog = {"apps": [{"id": "app1", "name": "App1"}, {"id": "app2", "name": "App2"}]}
        with patch("nexora_node_sdk.yh_adapter.ynh_app_catalog", return_value=list_catalog):
            result = ynh_app_catalog_filtered()
            self.assertEqual(len(result), 2)


class TestYnhInstallRemoveUpgradeApp(unittest.TestCase):
    def test_ynh_install_app_success(self):
        from nexora_node_sdk.yh_adapter import ynh_install_app

        with patch("nexora_node_sdk.yh_adapter._run", return_value=_completed(0, '{"msg": "ok"}')):
            result = ynh_install_app("nextcloud", "example.tld")
            self.assertTrue(result.get("success"))

    def test_ynh_install_app_failure(self):
        from nexora_node_sdk.yh_adapter import ynh_install_app

        with patch("nexora_node_sdk.yh_adapter._run", return_value=_completed(1, "", "install failed")):
            result = ynh_install_app("nextcloud", "example.tld")
            self.assertFalse(result.get("success"))

    def test_ynh_remove_app(self):
        from nexora_node_sdk.yh_adapter import ynh_remove_app

        with patch("nexora_node_sdk.yh_adapter._run", return_value=_completed(0, "{}")):
            result = ynh_remove_app("nextcloud")
            self.assertTrue(result.get("success"))

    def test_ynh_remove_app_purge(self):
        from nexora_node_sdk.yh_adapter import ynh_remove_app

        with patch("nexora_node_sdk.yh_adapter._run", return_value=_completed(0, "{}")):
            result = ynh_remove_app("nextcloud", purge=True)
            self.assertTrue(result.get("success"))

    def test_ynh_upgrade_app_success(self):
        from nexora_node_sdk.yh_adapter import ynh_upgrade_app

        with patch("nexora_node_sdk.yh_adapter._run", return_value=_completed(0, "")):
            result = ynh_upgrade_app("nextcloud")
            self.assertTrue(result.get("success"))

    def test_ynh_upgrade_app_failure(self):
        from nexora_node_sdk.yh_adapter import ynh_upgrade_app

        with patch("nexora_node_sdk.yh_adapter._run", return_value=_completed(1, "", "upgrade failed")):
            result = ynh_upgrade_app("nextcloud")
            self.assertFalse(result.get("success"))


class TestServicesWithFallback(unittest.TestCase):
    def test_returns_ynh_services_when_available(self):
        from nexora_node_sdk.yh_adapter import services_with_fallback

        with patch("nexora_node_sdk.yh_adapter.ynh_services", return_value={"nginx": {"status": "running"}}):
            result = services_with_fallback()
            self.assertIn("nginx", result)

    def test_falls_back_to_systemctl_on_error(self):
        from nexora_node_sdk.yh_adapter import services_with_fallback

        active_proc = _completed(0, "active")
        props_proc = _completed(0, "ActiveState=active\nSubState=running\nDescription=NGINX\nMainPID=1\nLoadState=loaded\n")

        with patch("nexora_node_sdk.yh_adapter.ynh_services", return_value={"_error": "no root"}), \
             patch("nexora_node_sdk.yh_adapter.systemctl_status", return_value={
                 "name": "nginx",
                 "active": "active",
                 "status": "active",
                 "sub": "running",
                 "description": "NGINX",
                 "pid": "1",
                 "load": "loaded",
             }), \
             patch("nexora_node_sdk.yh_adapter.systemctl_list_units", return_value={"nginx": {"status": "active"}}):
            result = services_with_fallback()
            self.assertIsInstance(result, dict)


if __name__ == "__main__":
    unittest.main()
