from __future__ import annotations

import unittest
from pathlib import Path


class RuntimeBoundaryRefactorTests(unittest.TestCase):
    def test_control_plane_backend_is_thin_launcher(self):
        source = Path("apps/control_plane/backend.py").read_text(encoding="utf-8")
        # accepts both absolute (source context) and relative (wheel context) import
        self.assertTrue(
            "from apps.control_plane.api import app, main" in source
            or "from .api import app, main" in source,
            "backend.py must import app and main from the control_plane api module",
        )

    def test_control_plane_api_registers_lifecycle_routes_by_table(self):
        source = Path("apps/control_plane/api.py").read_text(encoding="utf-8")
        self.assertIn("lifecycle_actions =", source)
        self.assertIn("register_fleet_routes", source)

    def test_node_agent_is_thin_launcher(self):
        source = Path("apps/node_agent/agent.py").read_text(encoding="utf-8")
        # accepts both absolute (source context) and relative (wheel context) import
        self.assertTrue(
            "from apps.node_agent.api import app, main" in source
            or "from .api import app, main" in source,
            "agent.py must import app and main from the node_agent api module",
        )

    def test_node_agent_api_registers_overlay_routes(self):
        source = Path("apps/node_agent/api.py").read_text(encoding="utf-8")
        self.assertIn("register_overlay_routes", source)
        self.assertIn("build_application", source)

    def test_mcp_fleet_tools_use_adapter_context(self):
        source = Path("src/yunohost_mcp/tools/fleet.py").read_text(encoding="utf-8")
        self.assertIn("MCPAdapterContext", source)
        self.assertIn("adapter = MCPAdapterContext.from_environment()", source)

    def test_mcp_adapter_lives_in_mcp_package(self):
        source = Path("src/yunohost_mcp/adapter.py").read_text(encoding="utf-8")
        self.assertIn("class MCPAdapterContext", source)

    def test_bootstrap_scripts_call_python_bootstrap_service(self):
        source = Path("deploy/bootstrap-node.sh").read_text(encoding="utf-8")
        self.assertIn("python3 -m nexora_saas.bootstrap assess", source)
        self.assertIn("python3 -m nexora_saas.bootstrap bootstrap-node", source)
        package_common = Path("ynh-package/scripts/_common.sh").read_text(encoding="utf-8")
        self.assertIn("nexora_saas.bootstrap assess-package-lifecycle", package_common)

    def test_sync_tools_use_mcp_adapter_context(self):
        source = Path("src/yunohost_mcp/tools/sync.py").read_text(encoding="utf-8")
        self.assertIn("MCPAdapterContext", source)
        self.assertIn("adapter = MCPAdapterContext.from_environment()", source)

    def test_orchestrator_uses_persistence_abstraction(self):
        source = Path("src/nexora_node_sdk/orchestrator.py").read_text(encoding="utf-8")
        self.assertIn("build_state_repository", source)
        self.assertIn("persistence_status", source)

    def test_fleet_tools_call_service_for_parity_sensitive_surfaces(self):
        source = Path("src/yunohost_mcp/tools/fleet.py").read_text(encoding="utf-8")
        self.assertIn("adapter.service.fleet_summary()", source)
        self.assertIn("adapter.service.request_enrollment_token", source)
        self.assertIn("adapter.service.run_lifecycle_action", source)


if __name__ == "__main__":
    unittest.main()
