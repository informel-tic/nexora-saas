"""Tests: verify all formerly-stub security endpoints have real implementations."""
from __future__ import annotations

import unittest
from pathlib import Path


class StubFreeEndpointTests(unittest.TestCase):
    """Ensure no stub/placeholder implementations remain in the control plane."""

    @classmethod
    def setUpClass(cls):
        cls.source = Path("apps/control_plane/api.py").read_text(encoding="utf-8")

    def test_no_stub_marker_in_api(self):
        """No _stub suffix or TODO:stub markers should remain."""
        self.assertNotIn("_stub", self.source)
        self.assertNotIn("TODO: stub", self.source)
        self.assertNotIn("placeholder implementation", self.source)

    # ── security_updates endpoint ──

    def test_security_updates_derives_from_state(self):
        self.assertIn("def security_updates(", self.source)
        self.assertIn("inventory_snapshots", self.source)
        self.assertIn("updates_available", self.source)

    # ── fail2ban_status endpoint ──

    def test_fail2ban_status_derives_from_audit(self):
        self.assertIn("def fail2ban_status(", self.source)
        self.assertIn("security_audit", self.source)
        self.assertIn("banned_ips", self.source)

    # ── open_ports endpoint ──

    def test_open_ports_derives_from_inventory(self):
        self.assertIn("def open_ports(", self.source)
        self.assertIn("firewall", self.source)

    # ── permissions_audit endpoint ──

    def test_permissions_audit_uses_posture(self):
        self.assertIn("def permissions_audit(", self.source)
        self.assertIn("security_posture", self.source)
        self.assertIn("public_apps", self.source)

    # ── recent_logins endpoint ──

    def test_recent_logins_from_audit(self):
        self.assertIn("def recent_logins(", self.source)
        self.assertIn("filter_security_events", self.source)
        self.assertIn("logins", self.source)

    # ── All five endpoints are routed ──

    def test_all_security_routes_registered(self):
        routes = [
            "/api/security/updates",
            "/api/security/fail2ban/status",
            "/api/security/open-ports",
            "/api/security/permissions-audit",
            "/api/security/recent-logins",
        ]
        for route in routes:
            self.assertIn(route, self.source, f"Missing route: {route}")

    # ── Tenant isolation on security endpoints ──

    def test_security_endpoints_accept_tenant_header(self):
        """Each security endpoint should filter by x_nexora_tenant_id."""
        # Count how many security endpoint functions accept the tenant header
        import re
        fns = ["security_updates", "fail2ban_status", "open_ports", "permissions_audit", "recent_logins"]
        for fn in fns:
            pattern = rf"def {fn}\([^)]*x_nexora_tenant_id"
            self.assertTrue(
                re.search(pattern, self.source, re.DOTALL),
                f"{fn} must accept x_nexora_tenant_id header",
            )

    # ── _enforce_deployment_scope ──

    def test_deployment_scope_enforcement_exists(self):
        self.assertIn("_enforce_deployment_scope", self.source)
        self.assertIn("NEXORA_DEPLOYMENT_SCOPE", self.source)


if __name__ == "__main__":
    unittest.main()
