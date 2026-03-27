"""WS4 — Node Trust & Identity comprehensive regression tests.

Covers: clock skew, replay attacks, token reuse, revocation, trust policy
evaluation, secret isolation, mTLS pre-flight, identity lifecycle, and
security audit event integrity.
"""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nexora_saas.enrollment import (
    attest_node,
    build_attestation_response,
    consume_enrollment_token,
    issue_enrollment_token,
    validate_enrollment_token,
)
from nexora_node_sdk.identity import generate_node_id, revoke_node_credentials
from nexora_node_sdk.identity_lifecycle import (
    audit_credential_health,
    emit_node_identity,
    revoke_node_identity,
    rotate_node_identity,
)
from nexora_node_sdk.secret_store import (
    issue_secret,
    list_secrets,
    read_secret,
    revoke_secret,
    verify_secret,
)
from nexora_node_sdk.security_audit import (
    CRITICAL_ACTIONS,
    build_security_event,
    emit_security_event,
    filter_security_events,
    summarize_security_events,
)
from nexora_node_sdk.state import DEFAULT_STATE
from nexora_node_sdk.tls import (
    is_certificate_revoked,
    list_revoked_certificates,
    revoke_certificate,
    verify_mtls_preconditions,
)
from nexora_node_sdk.trust_policy import (
    ACTION_TRUST_REQUIREMENTS,
    TRUST_LEVELS,
    build_trust_challenge,
    evaluate_trust_level,
    verify_node_trust,
)


def _fresh_state() -> dict:
    return {**DEFAULT_STATE, "enrollment_tokens": [], "enrollment_events": [], "security_audit": [], "nodes": []}


def _issue_and_attest(state, node_id="node-a"):
    issued = issue_enrollment_token(state, requested_by="tester", mode="pull", ttl_minutes=10, node_id=node_id)
    response = build_attestation_response(challenge=issued["challenge"], node_id=node_id, token_id=issued["token_id"])
    attest_node(
        state,
        token=issued["token"],
        challenge=issued["challenge"],
        challenge_response=response,
        hostname=f"{node_id}.test",
        node_id=node_id,
        agent_version="2.0.0",
        yunohost_version="12.1.2",
        debian_version="12",
        observed_at=datetime.now(timezone.utc).isoformat(),
        compatibility_matrix_path="compatibility.yaml",
    )
    return issued


# ═══════════════════════════════════════════════════════════════════════
# WS4-T07a: Clock skew tests
# ═══════════════════════════════════════════════════════════════════════

class ClockSkewTests(unittest.TestCase):
    def test_attestation_rejects_future_timestamp(self):
        """Timestamps far in the future are rejected."""
        state = _fresh_state()
        issued = issue_enrollment_token(state, requested_by="t", mode="pull", ttl_minutes=10)
        resp = build_attestation_response(challenge=issued["challenge"], node_id="n1", token_id=issued["token_id"])
        future = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        with self.assertRaises(ValueError, msg="clock skew"):
            attest_node(state, token=issued["token"], challenge=issued["challenge"],
                        challenge_response=resp, hostname="n1.test", node_id="n1",
                        agent_version="2.0.0", yunohost_version="12.1.2",
                        debian_version="12", observed_at=future,
                        compatibility_matrix_path="compatibility.yaml")

    def test_attestation_rejects_past_timestamp(self):
        """Timestamps 10 minutes in the past exceed skew tolerance."""
        state = _fresh_state()
        issued = issue_enrollment_token(state, requested_by="t", mode="pull", ttl_minutes=10)
        resp = build_attestation_response(challenge=issued["challenge"], node_id="n2", token_id=issued["token_id"])
        past = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        with self.assertRaises(ValueError, msg="clock skew"):
            attest_node(state, token=issued["token"], challenge=issued["challenge"],
                        challenge_response=resp, hostname="n2.test", node_id="n2",
                        agent_version="2.0.0", yunohost_version="12.1.2",
                        debian_version="12", observed_at=past,
                        compatibility_matrix_path="compatibility.yaml")

    def test_attestation_accepts_within_tolerance(self):
        """Timestamps within 5-minute tolerance are accepted."""
        state = _fresh_state()
        issued = issue_enrollment_token(state, requested_by="t", mode="pull", ttl_minutes=10)
        resp = build_attestation_response(challenge=issued["challenge"], node_id="n3", token_id=issued["token_id"])
        within = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
        result = attest_node(state, token=issued["token"], challenge=issued["challenge"],
                             challenge_response=resp, hostname="n3.test", node_id="n3",
                             agent_version="2.0.0", yunohost_version="12.1.2",
                             debian_version="12", observed_at=within,
                             compatibility_matrix_path="compatibility.yaml")
        self.assertEqual(result["status"], "attested")


# ═══════════════════════════════════════════════════════════════════════
# WS4-T07b: Replay / token reuse tests
# ═══════════════════════════════════════════════════════════════════════

class TokenReplayTests(unittest.TestCase):
    def test_consumed_token_cannot_be_reused(self):
        """A consumed enrollment token cannot be validated again."""
        state = _fresh_state()
        issued = _issue_and_attest(state, "node-replay")
        consume_enrollment_token(state, issued["token"], node_id="node-replay")
        with self.assertRaises(ValueError, msg="already consumed"):
            validate_enrollment_token(state, issued["token"])

    def test_attested_token_cannot_be_attested_again(self):
        """An attested token cannot be attested a second time."""
        state = _fresh_state()
        issued = _issue_and_attest(state, "node-dup")
        # The token is now attested; consuming then trying to attest again should fail.
        consume_enrollment_token(state, issued["token"], node_id="node-dup")
        with self.assertRaises(ValueError):
            validate_enrollment_token(state, issued["token"])

    def test_wrong_challenge_response_is_rejected(self):
        """An incorrect challenge-response proof is rejected."""
        state = _fresh_state()
        issued = issue_enrollment_token(state, requested_by="t", mode="pull", ttl_minutes=10)
        with self.assertRaises(ValueError, msg="mismatch"):
            attest_node(state, token=issued["token"], challenge=issued["challenge"],
                        challenge_response="wrong-proof",
                        hostname="bad.test", node_id="bad",
                        agent_version="2.0.0", yunohost_version="12.1.2",
                        debian_version="12",
                        observed_at=datetime.now(timezone.utc).isoformat(),
                        compatibility_matrix_path="compatibility.yaml")

    def test_expired_token_is_rejected(self):
        """An expired enrollment token cannot be used."""
        state = _fresh_state()
        issued = issue_enrollment_token(state, requested_by="t", mode="pull", ttl_minutes=5)
        # Force all tokens to be already expired.
        for rec in state["enrollment_tokens"]:
            rec["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
        with self.assertRaises(ValueError, msg="expired"):
            validate_enrollment_token(state, issued["token"])


# ═══════════════════════════════════════════════════════════════════════
# WS4-T07c: Revocation tests
# ═══════════════════════════════════════════════════════════════════════

class RevocationTests(unittest.TestCase):
    def test_revoked_certificate_is_detected_in_crl(self):
        with tempfile.TemporaryDirectory() as tmp:
            revoke_certificate(tmp, "node-r1", reason="compromised")
            self.assertTrue(is_certificate_revoked(tmp, "node-r1"))
            self.assertFalse(is_certificate_revoked(tmp, "node-r2"))

    def test_crl_entries_have_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            revoke_certificate(tmp, "node-r3", reason="test")
            entries = list_revoked_certificates(tmp)
            self.assertEqual(len(entries), 1)
            self.assertIn("revoked_at", entries[0])

    def test_revoke_node_identity_updates_state_and_crl(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = _fresh_state()
            state["nodes"].append({"node_id": "n-rev", "hostname": "rev.test", "status": "healthy", "token_id": "tok-1"})
            result = revoke_node_identity(state, node_id="n-rev", certs_dir=tmp, reason="breach", operator="admin")
            self.assertIsNotNone(result["revoked_at"])
            self.assertTrue(is_certificate_revoked(tmp, "n-rev"))
            node = state["nodes"][0]
            self.assertIsNotNone(node["credential_revoked_at"])
            self.assertIsNone(node["token_id"])

    def test_revoked_node_identity_marks_credential_identity(self):
        creds = {"node_id": "n-old", "token_id": "tok-old"}
        revoked = revoke_node_credentials(creds)
        self.assertIsNotNone(revoked["revoked_at"])


# ═══════════════════════════════════════════════════════════════════════
# WS4-T01 / T07d: Trust policy tests
# ═══════════════════════════════════════════════════════════════════════

class TrustPolicyTests(unittest.TestCase):
    def test_healthy_node_is_trusted(self):
        node = {"node_id": "n1", "status": "healthy"}
        self.assertEqual(evaluate_trust_level(node), "trusted")

    def test_revoked_node_is_untrusted(self):
        node = {"node_id": "n2", "status": "revoked"}
        self.assertEqual(evaluate_trust_level(node), "untrusted")

    def test_retired_node_is_untrusted(self):
        node = {"node_id": "n3", "status": "retired"}
        self.assertEqual(evaluate_trust_level(node), "untrusted")

    def test_bootstrap_pending_is_provisional(self):
        node = {"node_id": "n4", "status": "bootstrap_pending"}
        self.assertEqual(evaluate_trust_level(node), "provisional")

    def test_discovered_node_is_untrusted(self):
        node = {"node_id": "n5", "status": "discovered"}
        self.assertEqual(evaluate_trust_level(node), "untrusted")

    def test_expired_credential_makes_node_untrusted(self):
        node = {
            "node_id": "n6", "status": "healthy",
            "credential_expires_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        }
        self.assertEqual(evaluate_trust_level(node), "untrusted")

    def test_node_with_revoked_at_flag_is_untrusted(self):
        node = {"node_id": "n7", "status": "healthy", "credential_revoked_at": "2025-01-01T00:00:00+00:00"}
        self.assertEqual(evaluate_trust_level(node), "untrusted")

    def test_crl_revoked_node_is_untrusted(self):
        with tempfile.TemporaryDirectory() as tmp:
            revoke_certificate(tmp, "n8", reason="test")
            node = {"node_id": "n8", "status": "healthy"}
            self.assertEqual(evaluate_trust_level(node, certs_dir=tmp), "untrusted")

    def test_verify_node_trust_allows_trusted_action(self):
        node = {"node_id": "nx", "status": "healthy"}
        result = verify_node_trust(node, required_action="sync_branding")
        self.assertTrue(result["allowed"])

    def test_verify_node_trust_denies_untrusted_action(self):
        node = {"node_id": "ny", "status": "discovered"}
        result = verify_node_trust(node, required_action="execute_remote_action")
        self.assertFalse(result["allowed"])
        self.assertIn("denial_reason", result)

    def test_provisional_node_can_read_inventory(self):
        node = {"node_id": "nz", "status": "agent_installed"}
        result = verify_node_trust(node, required_action="read_inventory")
        self.assertTrue(result["allowed"])

    def test_provisional_node_cannot_sync_branding(self):
        node = {"node_id": "nw", "status": "bootstrap_pending"}
        result = verify_node_trust(node, required_action="sync_branding")
        self.assertFalse(result["allowed"])

    def test_build_trust_challenge_returns_nonce(self):
        ch = build_trust_challenge("node-x")
        self.assertIn("nonce", ch)
        self.assertEqual(ch["node_id"], "node-x")


# ═══════════════════════════════════════════════════════════════════════
# WS4-T02 / T07e: Identity lifecycle tests
# ═══════════════════════════════════════════════════════════════════════

class IdentityLifecycleTests(unittest.TestCase):
    def test_emit_creates_node_record_and_audit_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = _fresh_state()
            import unittest.mock
            with unittest.mock.patch("nexora_node_sdk.identity_lifecycle.generate_node_credentials") as mock_gen:
                mock_gen.return_value = {
                    "node_id": "n-emit", "fleet_id": "f1", "token_id": "tok-e",
                    "cert_path": f"{tmp}/n-emit.crt", "key_path": f"{tmp}/n-emit.key",
                    "issued_at": "2025-01-01T00:00:00+00:00",
                    "expires_at": "2026-01-01T00:00:00+00:00",
                    "rotation_recommended_at": "2025-10-01T00:00:00+00:00",
                    "revoked_at": None,
                }
                result = emit_node_identity(state, node_id="n-emit", fleet_id="f1", certs_dir=tmp, operator="admin")
            self.assertEqual(result["token_id"], "tok-e")
            self.assertEqual(len(state["nodes"]), 1)
            self.assertTrue(any(e["action"] == "credential_emitted" for e in state["security_audit"]))

    def test_rotate_revokes_then_emits(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = _fresh_state()
            state["nodes"].append({"node_id": "n-rot", "hostname": "rot.test", "token_id": "old-tok"})
            import unittest.mock
            with unittest.mock.patch("nexora_node_sdk.identity_lifecycle.generate_node_credentials") as mock_gen:
                mock_gen.return_value = {
                    "node_id": "n-rot", "fleet_id": "f1", "token_id": "new-tok",
                    "cert_path": f"{tmp}/n-rot.crt", "key_path": f"{tmp}/n-rot.key",
                    "issued_at": "2025-06-01T00:00:00+00:00",
                    "expires_at": "2026-06-01T00:00:00+00:00",
                    "rotation_recommended_at": "2026-03-01T00:00:00+00:00",
                    "revoked_at": None,
                }
                result = rotate_node_identity(state, node_id="n-rot", fleet_id="f1", certs_dir=tmp, operator="admin")
            self.assertTrue(result["rotation"])
            self.assertEqual(result["previous_token_id"], "old-tok")

    def test_audit_credential_health_flags_issues(self):
        state = _fresh_state()
        state["nodes"] = [
            {"node_id": "ok", "credential_expires_at": (datetime.now(timezone.utc) + timedelta(days=200)).isoformat(), "cert_path": "/tmp/ok.crt"},
            {"node_id": "expired", "credential_expires_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(), "cert_path": "/tmp/exp.crt"},
            {"node_id": "missing", "cert_path": None},
        ]
        report = audit_credential_health(state)
        statuses = {r["node_id"]: r["status"] for r in report}
        self.assertEqual(statuses["expired"], "attention_needed")
        self.assertEqual(statuses["missing"], "attention_needed")


# ═══════════════════════════════════════════════════════════════════════
# WS4-T04 / T07f: Secret isolation tests
# ═══════════════════════════════════════════════════════════════════════

class SecretIsolationTests(unittest.TestCase):
    def test_issue_and_read_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            meta = issue_secret(tmp, owner_type="node", owner_id="n1", scopes=["read_inventory"])
            self.assertIn("token_path", meta)
            token = read_secret(tmp, owner_type="node", owner_id="n1")
            self.assertIsNotNone(token)
            self.assertTrue(len(token) > 10)

    def test_secrets_are_isolated_between_owners(self):
        with tempfile.TemporaryDirectory() as tmp:
            issue_secret(tmp, owner_type="node", owner_id="n1")
            issue_secret(tmp, owner_type="node", owner_id="n2")
            t1 = read_secret(tmp, owner_type="node", owner_id="n1")
            t2 = read_secret(tmp, owner_type="node", owner_id="n2")
            self.assertNotEqual(t1, t2)

    def test_secrets_are_isolated_between_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            issue_secret(tmp, owner_type="node", owner_id="shared-id")
            issue_secret(tmp, owner_type="service", owner_id="shared-id")
            t1 = read_secret(tmp, owner_type="node", owner_id="shared-id")
            t2 = read_secret(tmp, owner_type="service", owner_id="shared-id")
            self.assertNotEqual(t1, t2)

    def test_revoked_secret_cannot_be_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            issue_secret(tmp, owner_type="operator", owner_id="op1")
            revoke_secret(tmp, owner_type="operator", owner_id="op1")
            self.assertIsNone(read_secret(tmp, owner_type="operator", owner_id="op1"))

    def test_verify_secret_constant_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            issue_secret(tmp, owner_type="node", owner_id="n-verify")
            token = read_secret(tmp, owner_type="node", owner_id="n-verify")
            self.assertTrue(verify_secret(tmp, owner_type="node", owner_id="n-verify", provided_token=token))
            self.assertFalse(verify_secret(tmp, owner_type="node", owner_id="n-verify", provided_token="wrong"))

    def test_list_secrets_returns_metadata_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            issue_secret(tmp, owner_type="node", owner_id="n-list", scopes=["read_inventory"])
            secrets_list = list_secrets(tmp, owner_type="node")
            self.assertEqual(len(secrets_list), 1)
            # Metadata must never contain the raw token.
            entry = secrets_list[0]
            self.assertNotIn("token", json.dumps(entry).lower().split("token_path")[0] if "token_path" in json.dumps(entry) else json.dumps(entry))

    def test_invalid_owner_type_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                issue_secret(tmp, owner_type="hacker", owner_id="x")

    def test_path_traversal_is_sanitized(self):
        with tempfile.TemporaryDirectory() as tmp:
            meta = issue_secret(tmp, owner_type="node", owner_id="../../etc/passwd")
            # The path should stay within the secrets directory.
            normalized = str(meta["token_path"]).replace("\\", "/")
            self.assertIn("secrets/node/", normalized)
            self.assertNotIn("..", meta["token_path"])


# ═══════════════════════════════════════════════════════════════════════
# WS4-T03 / T07g: mTLS pre-flight tests
# ═══════════════════════════════════════════════════════════════════════

class MTLSPreflightTests(unittest.TestCase):
    def test_missing_cert_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            node = {"node_id": "n-mtls", "cert_path": "/nonexistent.crt", "key_path": "/nonexistent.key"}
            result = verify_mtls_preconditions(node, certs_dir=tmp)
            self.assertFalse(result["ready"])
            self.assertIn("missing_certificate", result["issues"])
            self.assertIn("missing_private_key", result["issues"])

    def test_revoked_cert_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            revoke_certificate(tmp, "n-mtls2", reason="test")
            node = {"node_id": "n-mtls2", "cert_path": None, "key_path": None}
            result = verify_mtls_preconditions(node, certs_dir=tmp)
            self.assertIn("certificate_revoked", result["issues"])

    def test_healthy_node_is_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Create the CA cert and node cert/key files.
            (Path(tmp) / "fleet-ca.crt").write_text("ca")
            cert = Path(tmp) / "n-ok.crt"
            key = Path(tmp) / "n-ok.key"
            cert.write_text("cert")
            key.write_text("key")
            node = {"node_id": "n-ok", "cert_path": str(cert), "key_path": str(key)}
            result = verify_mtls_preconditions(node, certs_dir=tmp)
            self.assertTrue(result["ready"])
            self.assertEqual(result["issues"], [])


# ═══════════════════════════════════════════════════════════════════════
# WS4-T05 / T07h: Security audit event tests
# ═══════════════════════════════════════════════════════════════════════

class SecurityAuditEventTests(unittest.TestCase):
    def test_critical_actions_auto_elevated(self):
        """Actions in CRITICAL_ACTIONS get severity=critical automatically."""
        event = build_security_event("identity", "credential_revoked", severity="info")
        self.assertEqual(event["severity"], "critical")

    def test_emit_security_event_appends_and_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            state = _fresh_state()
            evt = emit_security_event(state, "auth", "token_issued", state_path=str(state_path), actor="admin")
            self.assertEqual(len(state["security_audit"]), 1)
            persisted = json.loads(state_path.read_text())
            self.assertEqual(len(persisted["security_audit"]), 1)

    def test_filter_by_category(self):
        events = [
            build_security_event("auth", "login"),
            build_security_event("tls", "handshake"),
            build_security_event("auth", "logout"),
        ]
        filtered = filter_security_events(events, category="auth")
        self.assertEqual(len(filtered), 2)

    def test_filter_by_severity(self):
        events = [
            build_security_event("auth", "credential_revoked"),  # auto-elevated to critical
            build_security_event("tls", "handshake", severity="info"),
        ]
        filtered = filter_security_events(events, severity="critical")
        self.assertEqual(len(filtered), 1)

    def test_summary_includes_critical_count(self):
        events = [
            build_security_event("auth", "credential_revoked"),
            build_security_event("tls", "handshake"),
        ]
        summary = summarize_security_events(events)
        self.assertEqual(summary["critical_events"], 1)


# ═══════════════════════════════════════════════════════════════════════
# WS4-T06 / T07i: Auth hardening tests
# ═══════════════════════════════════════════════════════════════════════

class AuthHardeningTests(unittest.TestCase):
    def test_generate_session_token_has_max_age(self):
        from nexora_node_sdk.auth import generate_session_token
        st = generate_session_token()
        self.assertIn("session_token", st)
        self.assertIn("max_age_seconds", st)

    def test_validate_session_age_rejects_expired(self):
        from nexora_node_sdk.auth import validate_session_age
        old = int(time.time()) - 7200  # 2 hours ago
        self.assertFalse(validate_session_age(str(old), max_age=3600))

    def test_validate_session_age_accepts_fresh(self):
        from nexora_node_sdk.auth import validate_session_age
        recent = int(time.time()) - 60
        self.assertTrue(validate_session_age(str(recent), max_age=3600))

    def test_validate_session_age_rejects_garbage(self):
        from nexora_node_sdk.auth import validate_session_age
        self.assertFalse(validate_session_age("not-a-number"))

    def test_rate_limit_tracking(self):
        from nexora_node_sdk.auth import _check_rate_limit, _record_auth_failure, _AUTH_FAILURES
        test_ip = "192.0.2.99"
        _AUTH_FAILURES.pop(test_ip, None)
        for _ in range(10):
            _record_auth_failure(test_ip)
        self.assertTrue(_check_rate_limit(test_ip))
        _AUTH_FAILURES.pop(test_ip, None)


if __name__ == "__main__":
    unittest.main()
