from __future__ import annotations

import unittest
from pathlib import Path


class SaaSAPIContractTests(unittest.TestCase):
    def test_control_plane_api_source_mentions_api_v1_namespace(self):
        source = Path("apps/control_plane/api.py").read_text(encoding="utf-8")
        self.assertIn("/api/v1", source)

    def test_console_token_is_session_scoped(self):
        source = Path("apps/console/api.js").read_text(encoding="utf-8")
        self.assertIn("sessionStorage.setItem('nexora_token'", source)
        self.assertIn("localStorage.removeItem('nexora_token')", source)

    def test_mcp_adapter_exists(self):
        source = Path("src/yunohost_mcp/adapter.py").read_text(encoding="utf-8")
        self.assertIn("NexoraService", source)

    def test_node_agent_is_not_present(self):
        self.assertFalse(Path("apps/node_agent").exists())


if __name__ == "__main__":
    unittest.main()