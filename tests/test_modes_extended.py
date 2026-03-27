from __future__ import annotations

import unittest

from nexora_saas.modes import (
    classify_tool_name,
    create_bound_confirmation,
    get_required_mode_for_tool,
    validate_authorization_matrix,
    validate_bound_confirmation,
)


class ModesExtendedTests(unittest.TestCase):
    def test_authorization_matrix_is_exhaustive(self):
        """TASK-3-7-2-1: every MCP tool is classified in the auth matrix."""

        report = validate_authorization_matrix()
        self.assertEqual(report["missing_tools"], [])
        self.assertGreater(report["classified_tools"], 0)

    def test_confirmation_tokens_are_bound_to_payload_hash(self):
        """TASK-3-7-3-1: confirmations are bound to action, target and params."""

        token = create_bound_confirmation("retire", "node-a", {"force": True}, operator="alice")
        self.assertTrue(validate_bound_confirmation(token, "retire", "node-a", {"force": True}, operator="alice"))
        # Token is consumed after successful validation and cannot be replayed.
        self.assertFalse(validate_bound_confirmation(token, "retire", "node-a", {"force": True}, operator="alice"))

    def test_tool_classification_defaults_to_safe_mode(self):
        """TASK-3-7-1-1: runtime classification resolves an explicit required mode."""

        tool = classify_tool_name("ynh_fleet_status")
        self.assertEqual(get_required_mode_for_tool(tool), "observer")


if __name__ == "__main__":
    unittest.main()
