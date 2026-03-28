from __future__ import annotations

import unittest
from pathlib import Path


class APIContractTests(unittest.TestCase):
    def test_control_plane_api_source_mentions_api_v1_namespace(self):
        source = Path("apps/control_plane/api.py").read_text(encoding="utf-8")
        self.assertIn('/api/v1', source)

    def test_console_source_mentions_enrollment_and_sla_views(self):
        source = Path("apps/console/app.js").read_text(encoding="utf-8")
        self.assertIn('sla', source.lower())
        self.assertIn('fleet', source.lower())

    def test_console_token_is_session_scoped(self):
        source = Path("apps/console/api.js").read_text(encoding="utf-8")
        self.assertIn("sessionStorage.setItem('nexora_token'", source)
        self.assertIn("localStorage.removeItem('nexora_token')", source)

    def test_control_plane_api_source_mentions_openapi(self):
        source = Path("apps/control_plane/api.py").read_text(encoding="utf-8")
        self.assertIn('openapi', source.lower())

    def test_control_plane_api_mentions_capability_catalog_route(self):
        source = Path("apps/control_plane/api.py").read_text(encoding="utf-8")
        self.assertIn('/api/capabilities', source)

    def test_control_plane_api_mentions_persistence_route(self):
        source = Path("apps/control_plane/api.py").read_text(encoding="utf-8")
        self.assertIn('/api/persistence', source)

    def test_control_plane_api_mentions_interface_parity_route(self):
        source = Path("apps/control_plane/api.py").read_text(encoding="utf-8")
        self.assertIn('/api/interface-parity/fleet-lifecycle', source)

    def test_fleet_node_action_validates_target_node(self):
        source = Path("apps/control_plane/api.py").read_text(encoding="utf-8")
        self.assertIn("Unknown node_id", source)
        self.assertIn("target_node_id", source)

    def test_node_agent_initializes_logging(self):
        source = Path("apps/node_agent/api.py").read_text(encoding="utf-8")
        self.assertIn("setup_logging()", source)

    def test_failover_tool_no_longer_uses_secondary_placeholder_fallback(self):
        source = Path("src/yunohost_mcp/tools/failover.py").read_text(encoding="utf-8")
        self.assertIn("failover requires at least two enrolled nodes", source)
        self.assertNotIn("secondary_placeholder", source)


if __name__ == "__main__":
    unittest.main()
