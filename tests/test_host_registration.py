"""Tests: host self-registration and node agent persistent state."""
from __future__ import annotations

import unittest
from pathlib import Path


class HostSelfRegistrationTests(unittest.TestCase):
    """Verify control plane auto-registers the host node on startup."""

    @classmethod
    def setUpClass(cls):
        cls.api_source = Path("apps/control_plane/api.py").read_text(encoding="utf-8")

    def test_startup_event_exists(self):
        self.assertIn('@app.on_event("startup")', self.api_source)

    def test_startup_calls_local_node_summary(self):
        self.assertIn("local_node_summary()", self.api_source)

    def test_startup_uses_normalize_node_record(self):
        self.assertIn("normalize_node_record", self.api_source)

    def test_startup_uses_transition_node_status(self):
        self.assertIn("transition_node_status", self.api_source)

    def test_host_node_role_is_host(self):
        self.assertIn('"role": "host"', self.api_source)

    def test_host_added_to_managed_nodes(self):
        self.assertIn("managed_nodes", self.api_source)


class NodeAgentPersistentStateTests(unittest.TestCase):
    """Verify the node agent has a proper persistent state backend."""

    @classmethod
    def setUpClass(cls):
        cls.source = Path("apps/node_agent/api.py").read_text(encoding="utf-8")

    def test_state_file_path_configured(self):
        self.assertIn("NEXORA_NODE_STATE_PATH", self.source)
        self.assertIn("node-agent-state.json", self.source)

    def test_load_persistent_state_function(self):
        self.assertIn("def _load_persistent_state()", self.source)

    def test_save_persistent_state_function(self):
        self.assertIn("def _save_persistent_state()", self.source)

    def test_restore_state_function(self):
        self.assertIn("def _restore_state()", self.source)

    def test_restore_called_on_module_load(self):
        self.assertIn("_restore_state()", self.source)

    def test_save_called_after_enroll(self):
        """The enroll handler must persist state after enrollment."""
        # Find the enroll function body and check it calls save
        idx_enroll = self.source.index("def enroll(")
        idx_next = self.source.index("def attest(")
        enroll_body = self.source[idx_enroll:idx_next]
        self.assertIn("_save_persistent_state()", enroll_body)

    def test_save_called_after_revoke(self):
        idx_revoke = self.source.index("def revoke()")
        # Find next function boundary
        after_revoke = self.source[idx_revoke:idx_revoke + 500]
        self.assertIn("_save_persistent_state()", after_revoke)

    def test_save_called_after_install_component(self):
        idx = self.source.index("def _install_component(")
        body = self.source[idx:idx + 800]
        self.assertIn("_save_persistent_state()", body)

    def test_save_called_after_remove_component(self):
        idx = self.source.index("def _remove_component(")
        body = self.source[idx:idx + 800]
        self.assertIn("_save_persistent_state()", body)

    def test_save_called_after_heartbeat(self):
        idx = self.source.index("def post_heartbeat(")
        body = self.source[idx:idx + 1000]
        self.assertIn("_save_persistent_state()", body)

    def test_state_file_permissions_0o600(self):
        self.assertIn("0o600", self.source)

    def test_atomic_write_via_tmp_replace(self):
        """State file should use tmp+replace for atomic writes."""
        self.assertIn(".with_suffix(\".tmp\")", self.source)
        self.assertIn("tmp.replace(", self.source)

    def test_tamper_events_capped(self):
        """Tamper events should be capped to prevent unbounded growth."""
        self.assertIn("_tamper_events[-100:]", self.source)


if __name__ == "__main__":
    unittest.main()
