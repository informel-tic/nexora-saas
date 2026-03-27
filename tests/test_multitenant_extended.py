from __future__ import annotations

import unittest

from nexora_saas.multitenant import generate_tenant_config, generate_tenant_report, generate_tenant_setup_commands


class MultiTenantExtendedTests(unittest.TestCase):
    def test_generate_tenant_config_creates_group(self):
        tenant = generate_tenant_config("Alpha", apps=["nextcloud"], users=["alice"])
        self.assertTrue(tenant["ynh_group"].startswith("tenant_"))

    def test_generate_tenant_setup_commands_contains_permissions(self):
        tenant = generate_tenant_config("Alpha", domain="alpha.example.org", apps=["wiki"], users=["alice"])
        commands = generate_tenant_setup_commands(tenant)
        self.assertTrue(any("permission update" in cmd for cmd in commands))

    def test_generate_tenant_report_counts_users(self):
        report = generate_tenant_report([generate_tenant_config("Alpha", users=["alice"])])
        self.assertEqual(report["total_users"], 1)


if __name__ == "__main__":
    unittest.main()
