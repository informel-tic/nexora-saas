"""Tests: console JS handlers, window functions, and view integrity."""
from __future__ import annotations

import unittest
from pathlib import Path


class ConsoleAppHandlerTests(unittest.TestCase):
    """Verify that all required window.* handlers are declared in app.js."""

    @classmethod
    def setUpClass(cls):
        cls.app_source = Path("apps/console/app.js").read_text(encoding="utf-8")
        cls.views_source = Path("apps/console/views.js").read_text(encoding="utf-8")
        cls.api_source = Path("apps/console/api.js").read_text(encoding="utf-8")

    # ── Window handlers ──

    def test_handler_create_org(self):
        self.assertIn("window.createOrg", self.app_source)

    def test_handler_create_subscription(self):
        self.assertIn("window.createSubscription", self.app_source)

    def test_handler_suspend_subscription(self):
        self.assertIn("window.suspendSubscription", self.app_source)

    def test_handler_cancel_subscription(self):
        self.assertIn("window.cancelSubscription", self.app_source)

    def test_handler_provision_node(self):
        self.assertIn("window.provisionNode", self.app_source)

    def test_handler_deprovision_node(self):
        self.assertIn("window.deprovisionNode", self.app_source)

    def test_handler_enroll_node(self):
        self.assertIn("window.enrollNode", self.app_source)

    # ── Toast notification system ──

    def test_toast_system_exists(self):
        self.assertIn("window.nxToast", self.app_source)

    # ── Section renderers map covers all sections ──

    def test_all_section_renderers_declared(self):
        expected = [
            "dashboard", "scores", "apps", "services", "domains",
            "security", "pra", "fleet", "blueprints", "automation",
            "adoption", "modes", "docker", "storage", "notifications",
            "hooks", "governance", "sla-tracking", "subscription", "provisioning",
        ]
        for section in expected:
            # Accept `section:`, `"section":`, or `'section':` keys
            self.assertTrue(
                f"{section}:" in self.app_source
                or f'"{section}":' in self.app_source
                or f"'{section}':" in self.app_source,
                f"sectionRenderers missing key: {section}",
            )

    # ── View functions exist ──

    def test_all_view_functions_exist(self):
        expected_fns = [
            "loadDashboard", "loadScores", "loadApps", "loadServices",
            "loadDomains", "loadSecurity", "loadPra", "loadFleet",
            "loadBlueprints", "loadAutomation", "loadAdoption", "loadModes",
            "loadDocker", "loadStorage", "loadNotifications", "loadHooks",
            "loadGovernanceRisks", "loadSlaTracking", "loadSubscription",
            "loadProvisioning",
        ]
        for fn in expected_fns:
            self.assertIn(f"export async function {fn}(", self.views_source,
                          f"views.js missing function: {fn}")

    # ── API module ──

    def test_api_uses_bearer_header(self):
        self.assertIn("Authorization", self.api_source)
        self.assertIn("Bearer", self.api_source)

    def test_api_exports_needed_functions(self):
        for fn in ["initToken", "api", "apiPost", "loadAccessContext", "showTokenPrompt"]:
            self.assertTrue(
                f"export function {fn}" in self.api_source
                or f"export async function {fn}" in self.api_source,
                f"api.js missing export: {fn}",
            )

    # ── Dashboard cards ──

    def test_dashboard_shows_host_identity(self):
        self.assertIn("identity", self.views_source)
        self.assertIn("Nœud hôte SaaS", self.views_source.encode().decode("unicode_escape", errors="ignore")
                       if False else self.views_source)

    def test_dashboard_shows_session_context(self):
        self.assertIn("nexora_token", self.views_source)
        self.assertIn("Session console", self.views_source)

    # ── Security subpanels ──

    def test_security_view_has_real_subpanels(self):
        for endpoint in ["security/updates", "security/fail2ban/status",
                         "security/open-ports", "security/permissions-audit",
                         "security/recent-logins"]:
            self.assertIn(endpoint, self.views_source,
                          f"loadSecurity missing fetch for {endpoint}")

    def test_governance_view_includes_changelog(self):
        self.assertIn("governance/changelog", self.views_source)

    # ── Automation / notifications / SLA views ──

    def test_automation_view_fetches_templates_and_checklists(self):
        for endpoint in ["automation/templates", "automation/checklists"]:
            self.assertIn(endpoint, self.views_source,
                          f"loadAutomation missing fetch for {endpoint}")

    def test_notifications_view_fetches_templates(self):
        self.assertIn("notifications/templates", self.views_source)

    def test_sla_tracking_fetches_tiers(self):
        self.assertIn("sla/tiers", self.views_source)

    # ── Subscription actions ──

    def test_subscription_view_has_action_buttons(self):
        self.assertIn("suspendSubscription", self.views_source)
        self.assertIn("cancelSubscription", self.views_source)

    # ── Provisioning refresh ──

    def test_provisioning_has_refresh_button(self):
        self.assertIn("Rafra", self.views_source)


if __name__ == "__main__":
    unittest.main()
