from __future__ import annotations

import unittest
from pathlib import Path


class OrchestratorTests(unittest.TestCase):
    def test_orchestrator_source_mentions_registration_and_lifecycle(self):
        source = Path("src/nexora_node_sdk/orchestrator.py").read_text(encoding="utf-8")
        self.assertIn("register_enrolled_node", source)
        self.assertIn("run_lifecycle_action", source)

    def test_blueprints_source_mentions_profile_loading(self):
        source = Path("src/nexora_node_sdk/blueprints.py").read_text(encoding="utf-8")
        self.assertIn("profile.yaml", source)

    def test_backend_source_mentions_blueprints_endpoint(self):
        source = Path("apps/control_plane/api.py").read_text(encoding="utf-8")
        self.assertIn('/api/blueprints', source)


if __name__ == "__main__":
    unittest.main()
