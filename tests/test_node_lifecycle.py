from __future__ import annotations

import tempfile
import unittest
import unittest.mock
from pathlib import Path

from nexora_saas.node_lifecycle import apply_lifecycle_action
from nexora_node_sdk.state import DEFAULT_STATE


class NodeLifecycleTests(unittest.TestCase):
    def _state(self) -> dict:
        return {
            **DEFAULT_STATE,
            "fleet": {"mode": "fleet", "managed_nodes": ["node-1"], "fleet_id": "fleet-123"},
            "nodes": [
                {
                    "node_id": "node-1",
                    "hostname": "node-1.example.test",
                    "status": "healthy",
                    "apps_count": 1,
                    "profile": "node-agent-only",
                    "roles": ["apps"],
                }
            ],
        }

    def test_drain_requires_confirmation_when_workloads_exist(self):
        """TASK-3-1-5-1: drain is protected by operational safety checks."""

        with self.assertRaises(ValueError):
            apply_lifecycle_action(self._state(), node_id="node-1", action="drain", operator="tester")

    def test_revoke_and_reenroll_updates_state(self):
        """TASK-3-1-5-1: revoke and re-enroll mutate lifecycle metadata."""

        state = self._state()
        revoked = apply_lifecycle_action(state, node_id="node-1", action="revoke", operator="tester", confirmation=True)
        reenrolled = apply_lifecycle_action(state, node_id="node-1", action="re_enroll", operator="tester", confirmation=True)
        self.assertEqual(revoked["node"]["status"], "revoked")
        self.assertEqual(reenrolled["node"]["status"], "bootstrap_pending")

    @unittest.mock.patch("nexora_saas.node_lifecycle.generate_node_credentials")
    def test_rotate_credentials_issues_real_files(self, mock_gen):
        """TASK-3-1-5-1: rotation re-issues certificate material on disk."""

        def mock_generate(node_id, fleet_id, certs_dir):
            c = Path(certs_dir) / f"{node_id}.crt"
            k = Path(certs_dir) / f"{node_id}.key"
            c.write_text("mock-cert-data")
            k.write_text("mock-key-data")
            return {
                "token_id": "tok-123",
                "expires_at": "2030-01-01T00:00:00Z",
                "cert_path": str(c),
                "key_path": str(k),
            }
        mock_gen.side_effect = mock_generate

        state = self._state()
        with tempfile.TemporaryDirectory() as tmp:
            result = apply_lifecycle_action(
                state,
                node_id="node-1",
                action="rotate_credentials",
                operator="tester",
                confirmation=True,
                certs_dir=tmp,
            )
            cert_path = Path(result["node"]["cert_path"])
            key_path = Path(result["node"]["key_path"])
            self.assertTrue(cert_path.exists())
            self.assertTrue(key_path.exists())
            self.assertNotIn("placeholder", cert_path.read_text())


if __name__ == "__main__":
    unittest.main()
