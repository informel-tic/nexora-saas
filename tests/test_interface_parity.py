from __future__ import annotations

import unittest
from pathlib import Path

from nexora_saas.interface_parity import fleet_lifecycle_parity_payload


class InterfaceParityTests(unittest.TestCase):
    def test_fleet_lifecycle_parity_payload_is_structured(self):
        payload = fleet_lifecycle_parity_payload()
        self.assertEqual(payload["surface"], "fleet-lifecycle")
        self.assertGreaterEqual(payload["summary"]["capability_count"], 5)

    def test_fleet_lifecycle_parity_mentions_enrollment_register(self):
        payload = fleet_lifecycle_parity_payload()
        capabilities = {entry["capability"]: entry for entry in payload["capabilities"]}
        self.assertIn("fleet.enrollment-register", capabilities)
        self.assertIn("ynh_fleet_enrollment_register", capabilities["fleet.enrollment-register"]["mcp"])

    def test_control_plane_api_mentions_interface_parity_route(self):
        source = Path("apps/control_plane/api.py").read_text(encoding="utf-8")
        self.assertIn("/api/interface-parity/fleet-lifecycle", source)

    def test_fleet_tools_mention_parity_aligned_tools(self):
        source = Path("src/yunohost_mcp/tools/fleet.py").read_text(encoding="utf-8")
        self.assertIn("ynh_fleet_enrollment_request", source)
        self.assertIn("ynh_fleet_enrollment_register", source)
        self.assertIn("ynh_fleet_lifecycle_action", source)


if __name__ == "__main__":
    unittest.main()
