from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from nexora_saas.bootstrap import BootstrapOrchestrator, main as bootstrap_main
from nexora_saas.orchestrator import NexoraService


class BootstrapOrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.repo_root = Path(self.tempdir.name)
        (self.repo_root / "src").mkdir(parents=True, exist_ok=True)
        state_path = self.repo_root / "var" / "state.json"
        self.service = NexoraService(self.repo_root, state_path)
        self.orchestrator = BootstrapOrchestrator(self.service)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_assess_target_allows_missing_domain_for_control_plane(self):
        result = self.orchestrator.assess_target(
            profile="control-plane",
            enrollment_mode="pull",
            mode="fresh",
            yunohost_version="12.1.2",
            target_host="node-01.internal",
            domain="",
            path_url="/nexora",
        )
        self.assertTrue(result["success"])
        self.assertIsNone(result.get("domain"))

    def test_bootstrap_local_node_persists_registered_node(self):
        result = self.orchestrator.bootstrap_local_node(
            profile="control-plane+node-agent",
            enrollment_mode="pull",
            mode="fresh",
            yunohost_version="12.1.2",
            target_host="node-01.internal",
            domain="example.org",
            path_url="/nexora",
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["node"]["status"], "registered")
        state = self.service.state.load()
        self.assertTrue(state["bootstrap_runs"])
        self.assertEqual(state["nodes"][0]["node_id"], result["node"]["node_id"])

    def test_cli_assess_emits_structured_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            state_path = repo_root / "var" / "state.json"
            output_path = repo_root / "output.json"
            cmd = [
                "--repo-root", str(repo_root),
                "--state-path", str(state_path),
                "--profile", "node-agent-only",
                "--enrollment-mode", "pull",
                "--mode", "augment",
                "--yunohost-version", "12.1.2",
                "--target-host", "node-02.internal",
                "--domain", "",
                "--path-url", "/nexora",
            ]
            import io
            import contextlib

            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                rc = bootstrap_main(["assess", *cmd])
            output = buffer.getvalue()
            payload = json.loads(output)
            self.assertEqual(rc, 0)
            self.assertTrue(payload["success"])
            self.assertIn("compatibility", payload)

    def test_assess_package_lifecycle_blocks_unlisted_major(self):
        # Version 10.x has no exact match and no prefix range — must be blocked
        result = self.orchestrator.assess_package_lifecycle(
            yunohost_version="10.0.9",
            operation="install",
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "package_lifecycle_blocked_by_compatibility")

    def test_assess_package_lifecycle_accepts_tested_upgrade_operation(self):
        result = self.orchestrator.assess_package_lifecycle(
            yunohost_version="12.1.2",
            operation="upgrade",
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["required_capability"], "upgrade_app")

    def test_assess_package_lifecycle_rejects_unknown_operation(self):
        result = self.orchestrator.assess_package_lifecycle(
            yunohost_version="12.1.2",
            operation="delete",
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "unsupported_package_operation")


if __name__ == "__main__":
    unittest.main()
