from __future__ import annotations

import unittest
from pathlib import Path

from nexora_node_sdk.compatibility import validate_upgrade_path


class PackagingTests(unittest.TestCase):
    def test_manifest_pins_yunohost_12_1_or_newer(self):
        """TASK-3-8-0-1: manifest declares the supported YunoHost baseline."""

        manifest = Path("ynh-package/manifest.toml").read_text(encoding="utf-8")
        self.assertIn('yunohost = ">= 12.1"', manifest)

    def test_install_script_contains_preinstall_checks(self):
        """TASK-3-8-2-1: package scripts enforce pre-install compatibility checks."""

        script = Path("ynh-package/scripts/install").read_text(encoding="utf-8")
        self.assertIn("nexora_validate_yunohost_version", script)
        self.assertIn("nexora_abort_if_port_busy", script)
        self.assertIn("nexora_setup_operator_role_lock", script)

    def test_common_script_delegates_exact_minor_policy_to_bootstrap_service(self):
        """Package-side validation must defer exact-minor policy to the canonical bootstrap service."""

        script = Path("ynh-package/scripts/_common.sh").read_text(encoding="utf-8")
        self.assertIn("nexora_saas.bootstrap assess-package-lifecycle", script)
        self.assertIn("--operation", script)
        self.assertIn("--repo-root", script)
        self.assertIn("--state-path", script)
        self.assertNotIn("12.2*", script)
        self.assertNotIn("12.3*", script)

    def test_common_script_uses_dpkg_query_as_primary_version_detection(self):
        """Inside lifecycle scripts the yunohost CLI is locked; dpkg-query is the safe primary method."""

        script = Path("ynh-package/scripts/_common.sh").read_text(encoding="utf-8")
        dpkg_pos = script.index("dpkg-query -W -f='${Version}' yunohost")
        ynh_cli_pos = script.index("yunohost tools version --output-as json")
        self.assertLess(dpkg_pos, ynh_cli_pos, "dpkg-query must come before yunohost CLI calls")

    def test_common_script_version_check_accepts_operation_parameter(self):
        """nexora_validate_yunohost_version must accept an operation parameter for lifecycle dispatch."""

        script = Path("ynh-package/scripts/_common.sh").read_text(encoding="utf-8")
        self.assertIn('operation="${1:-install}"', script)
        self.assertIn('"$operation"', script)

    def test_upgrade_script_passes_upgrade_operation(self):
        """Upgrade must pass operation=upgrade to compatibility check."""

        script = Path("ynh-package/scripts/upgrade").read_text(encoding="utf-8")
        self.assertIn("nexora_validate_yunohost_version upgrade", script)

    def test_restore_script_passes_restore_operation(self):
        """Restore must pass operation=restore to compatibility check."""

        script = Path("ynh-package/scripts/restore").read_text(encoding="utf-8")
        self.assertIn("nexora_validate_yunohost_version restore", script)

    def test_common_script_gracefully_degrades_without_bootstrap_module(self):
        """When nexora_saas.bootstrap is not available, version check should not abort."""

        script = Path("ynh-package/scripts/_common.sh").read_text(encoding="utf-8")
        self.assertIn('import nexora_saas.bootstrap', script)
        self.assertIn('2>/dev/null', script)

    def test_upgrade_script_stops_service_before_port_check(self):
        """Upgrade must not fail on its own bound port."""

        script = Path("ynh-package/scripts/upgrade").read_text(encoding="utf-8")
        self.assertLess(
            script.index('systemctl stop "$app" || true'),
            script.index("nexora_abort_if_port_busy"),
        )

    def test_restore_script_revalidates_platform_before_restart(self):
        """Restore should re-check compatibility before reviving the service."""

        script = Path("ynh-package/scripts/restore").read_text(encoding="utf-8")
        self.assertIn("nexora_validate_yunohost_version", script)
        self.assertIn('systemctl stop "$app" || true', script)
        self.assertIn("nexora_setup_operator_role_lock", script)

    def test_systemd_enforces_operator_only_guardrails(self):
        """Package service must keep operator-only routes protected by explicit role binding."""

        service = Path("ynh-package/conf/systemd.service").read_text(encoding="utf-8")
        self.assertIn("Environment=NEXORA_OPERATOR_ONLY_ENFORCE=1", service)
        self.assertIn("Environment=NEXORA_API_TOKEN_ROLE_FILE=/etc/nexora/api-token-roles.json", service)
        self.assertIn("Environment=NEXORA_DEPLOYMENT_SCOPE=operator", service)

    def test_validate_upgrade_path_rejects_major_jump(self):
        """TASK-3-8-3-1: upgrade path management rejects incompatible version jumps."""

        report = validate_upgrade_path("11.0.0", "12.1.2")
        self.assertFalse(report["allowed"])
        self.assertIn("major_jump_requires_manual_review", report["reasons"])

    def test_bootstrap_accepts_debian_12_minor_versions_and_ynh_detection_fallbacks(self):
        """Bootstrap must accept Debian 12.x and use resilient YunoHost version detection."""

        script = Path("deploy/bootstrap-node.sh").read_text(encoding="utf-8")
        self.assertIn('^(11|12|13)([.].*)?$', script)
        self.assertIn("yunohost --version", script)
        self.assertIn("dpkg-query -W -f='${Version}", script)
        self.assertIn("Nexora bootstrap supports Debian 11.x/12.x/13.x on YunoHost nodes.", script)
        self.assertIn("scripts/node_coherence_audit.py", script)

    # ── YunoHost v2.1 packaging compliance ──

    def test_manifest_declares_helpers_version_2_1(self):
        """Manifest must declare helpers_version = 2.1 for v2.1 helper names."""
        manifest = Path("ynh-package/manifest.toml").read_text(encoding="utf-8")
        self.assertIn('helpers_version = "2.1"', manifest)

    def test_manifest_declares_port_resource(self):
        """Port must be managed by YunoHost resources to avoid conflicts."""
        manifest = Path("ynh-package/manifest.toml").read_text(encoding="utf-8")
        self.assertIn("[resources.ports]", manifest)
        self.assertIn("main.default = 38120", manifest)

    def test_nginx_config_template_exists(self):
        """NGINX reverse-proxy template is required for web access."""
        self.assertTrue(Path("ynh-package/conf/nginx.conf").exists())
        conf = Path("ynh-package/conf/nginx.conf").read_text(encoding="utf-8")
        self.assertIn("proxy_pass", conf)
        self.assertIn("__PORT__", conf)
        self.assertIn("__PATH__", conf)

    def test_install_configures_nginx_and_service_integration(self):
        """Install must set up NGINX reverse proxy and register in YunoHost panel."""
        script = Path("ynh-package/scripts/install").read_text(encoding="utf-8")
        self.assertIn("ynh_config_add_nginx", script)
        self.assertIn("ynh_config_add_systemd", script)
        self.assertIn('yunohost service add "$app"', script)
        self.assertIn("ynh_systemctl", script)

    def test_remove_cleans_nginx_and_service_integration(self):
        """Remove must tear down NGINX config and deregister from YunoHost panel."""
        script = Path("ynh-package/scripts/remove").read_text(encoding="utf-8")
        self.assertIn("ynh_config_remove_nginx", script)
        self.assertIn("ynh_config_remove_systemd", script)
        self.assertIn('yunohost service remove "$app"', script)

    def test_upgrade_refreshes_nginx_and_service_integration(self):
        """Upgrade must re-provision NGINX config and re-register service."""
        script = Path("ynh-package/scripts/upgrade").read_text(encoding="utf-8")
        self.assertIn("ynh_config_add_nginx", script)
        self.assertIn("ynh_config_add_systemd", script)
        self.assertIn('yunohost service add "$app"', script)

    def test_restore_restores_nginx_and_service_integration(self):
        """Restore must bring back NGINX config and re-register service."""
        script = Path("ynh-package/scripts/restore").read_text(encoding="utf-8")
        self.assertIn("ynh_config_add_nginx", script)
        self.assertIn('yunohost service add "$app"', script)

    def test_backup_script_exists_and_backs_up_nginx(self):
        """Backup script must exist and include NGINX config."""
        self.assertTrue(Path("ynh-package/scripts/backup").exists())
        script = Path("ynh-package/scripts/backup").read_text(encoding="utf-8")
        self.assertIn("ynh_backup", script)
        self.assertIn("nginx", script)

    def test_systemd_template_uses_port_placeholder(self):
        """Systemd service must use __PORT__ placeholder, not hardcoded port."""
        service = Path("ynh-package/conf/systemd.service").read_text(encoding="utf-8")
        self.assertIn("__PORT__", service)
        self.assertNotIn("NEXORA_CONTROL_PLANE_PORT=38120", service)

    def test_scripts_do_not_use_deprecated_ynh_app_instance_name(self):
        """v2 packaging auto-sets $app — no need for $YNH_APP_INSTANCE_NAME."""
        for name in ("install", "remove", "upgrade", "restore"):
            script = Path(f"ynh-package/scripts/{name}").read_text(encoding="utf-8")
            self.assertNotIn("YNH_APP_INSTANCE_NAME", script, f"scripts/{name} still references deprecated variable")

    def test_common_script_venv_uses_system_python(self):
        """nexora_setup_venv must use /usr/bin/python3, not the bootstrap venv python."""
        script = Path("ynh-package/scripts/_common.sh").read_text(encoding="utf-8")
        self.assertIn('/usr/bin/python3', script)
        # Ensure sys_python3 is used for venv creation, not bare python3
        venv_section = script[script.index("nexora_setup_venv"):]
        self.assertIn('sys_python3="/usr/bin/python3"', venv_section)
        self.assertIn('"$sys_python3" -m venv', venv_section)

    def test_bootstrap_cli_returns_nonzero_on_error_contract(self):
        """bootstrap.py main() must return non-zero exit code when payload.success is false."""
        import inspect
        from nexora_saas import bootstrap
        source = inspect.getsource(bootstrap.main)
        self.assertIn('payload.get("success")', source)

    def test_common_script_does_not_export_path_with_venv(self):
        """_common.sh must NOT globally export PATH with the bootstrap venv.

        YunoHost helpers (toml_to_json, etc.) rely on system python3 having
        the toml module. Putting the venv's python3 first in PATH breaks them.
        """
        script = Path("ynh-package/scripts/_common.sh").read_text(encoding="utf-8")
        self.assertNotIn('export PATH="${NEXORA_VENV}/bin:${PATH}"', script)
        self.assertNotIn('export PATH=', script)

    def test_common_script_uses_venv_python_for_bootstrap_only(self):
        """nexora_saas.bootstrap calls must use explicit venv python, not bare python3."""
        script = Path("ynh-package/scripts/_common.sh").read_text(encoding="utf-8")
        self.assertIn('_venv_python="${NEXORA_VENV}/bin/python3"', script)
        self.assertIn('"$_venv_python" -m nexora_saas.bootstrap', script)
        self.assertIn('"$_venv_python" -c "import nexora_saas.bootstrap"', script)

    def test_resolve_repo_root_respects_env_override(self):
        """resolve_repo_root must use NEXORA_REPO_ROOT env var when set."""
        import os
        from pathlib import Path as P
        from nexora_node_sdk.runtime_context import resolve_repo_root

        os.environ["NEXORA_REPO_ROOT"] = "/var/www/nexora/repo"
        try:
            result = resolve_repo_root(__file__)
            self.assertEqual(result, P("/var/www/nexora/repo"))
        finally:
            del os.environ["NEXORA_REPO_ROOT"]

    def test_systemd_sets_repo_root_env(self):
        """Systemd service must set NEXORA_REPO_ROOT for installed-package context."""
        service = Path("ynh-package/conf/systemd.service").read_text(encoding="utf-8")
        self.assertIn("Environment=NEXORA_REPO_ROOT=__INSTALL_DIR__/repo", service)

