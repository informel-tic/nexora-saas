from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from nexora_node_sdk.state import DEFAULT_STATE
from nexora_saas.enrollment import attest_node, build_attestation_response, consume_enrollment_token, issue_enrollment_token


class EnrollmentTests(unittest.TestCase):
    def test_issue_attest_and_consume_token(self):
        """TASK-3-1-5-1: enrollment tokens are one-time and attestation-gated."""

        state = {**DEFAULT_STATE, "enrollment_tokens": [], "enrollment_events": [], "security_audit": []}
        issued = issue_enrollment_token(state, requested_by="tester", mode="pull", ttl_minutes=10, node_id="node-a")
        response = build_attestation_response(
            challenge=issued["challenge"],
            node_id="node-a",
            token_id=issued["token_id"],
        )
        result = attest_node(
            state,
            token=issued["token"],
            challenge=issued["challenge"],
            challenge_response=response,
            hostname="node-a.example.test",
            node_id="node-a",
            agent_version="2.0.0",
            yunohost_version="12.1.2",
            debian_version="12",
            observed_at=datetime.now(timezone.utc).isoformat(),
            compatibility_matrix_path="compatibility.yaml",
        )
        consumed = consume_enrollment_token(state, issued["token"], node_id="node-a")
        self.assertEqual(result["status"], "attested")
        self.assertEqual(consumed["status"], "consumed")
        self.assertTrue(state["enrollment_events"])

    def test_attestation_rejects_clock_skew(self):
        """TASK-3-1-5-1: attestation rejects stale timestamps."""

        state = {**DEFAULT_STATE, "enrollment_tokens": [], "enrollment_events": [], "security_audit": []}
        issued = issue_enrollment_token(state, requested_by="tester", mode="pull", ttl_minutes=10)
        response = build_attestation_response(
            challenge=issued["challenge"],
            node_id="node-b",
            token_id=issued["token_id"],
        )
        with self.assertRaises(ValueError):
            attest_node(
                state,
                token=issued["token"],
                challenge=issued["challenge"],
                challenge_response=response,
                hostname="node-b.example.test",
                node_id="node-b",
                agent_version="2.0.0",
                yunohost_version="12.1.2",
                debian_version="12",
                observed_at=(datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
                compatibility_matrix_path="compatibility.yaml",
            )

    def test_attestation_rejects_incompatible_versions(self):
        """TASK-3-1-5-1: attestation enforces compatibility matrix."""

        state = {**DEFAULT_STATE, "enrollment_tokens": [], "enrollment_events": [], "security_audit": []}
        issued = issue_enrollment_token(state, requested_by="tester", mode="push", ttl_minutes=10)
        response = build_attestation_response(
            challenge=issued["challenge"],
            node_id="node-c",
            token_id=issued["token_id"],
        )
        with self.assertRaises(ValueError):
            attest_node(
                state,
                token=issued["token"],
                challenge=issued["challenge"],
                challenge_response=response,
                hostname="node-c.example.test",
                node_id="node-c",
                agent_version="2.0.0",
                yunohost_version="12.0.1",
                debian_version="12",
                observed_at=datetime.now(timezone.utc).isoformat(),
                compatibility_matrix_path="compatibility.yaml",
            )


if __name__ == "__main__":
    unittest.main()
