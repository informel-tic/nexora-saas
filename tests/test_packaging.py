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
        self.assertIn("python3 -m nexora_saas.bootstrap assess-package-lifecycle", script)
        self.assertIn("--operation", script)
        self.assertNotIn("12.2*", script)
        self.assertNotIn("12.3*", script)

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

