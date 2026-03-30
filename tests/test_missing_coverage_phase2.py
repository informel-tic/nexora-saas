from __future__ import annotations

import importlib
import json
import logging
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))


class AutomationEngineCoverageTests(unittest.TestCase):
    def test_module_imports_without_nexora_core(self):
        module = importlib.import_module("nexora_node_sdk.automation_engine")
        self.assertTrue(hasattr(module, "get_allowed_templates"))

    def test_unknown_tier_falls_back_to_free(self):
        module = importlib.import_module("nexora_node_sdk.automation_engine")
        allowed = module.get_allowed_templates("nonexistent-tier")
        self.assertIsInstance(allowed, list)


class EnrollmentClientCoverageTests(unittest.TestCase):
    def test_attestation_response_is_deterministic(self):
        from nexora_node_sdk.enrollment_client import build_attestation_response

        r1 = build_attestation_response(challenge="abc", node_id="node-1", token_id="tok-1")
        r2 = build_attestation_response(challenge="abc", node_id="node-1", token_id="tok-1")
        self.assertEqual(r1, r2)
        self.assertEqual(len(r1), 64)


class LoggingConfigCoverageTests(unittest.TestCase):
    def test_json_formatter_includes_message_and_level(self):
        from nexora_node_sdk.logging_config import JsonFormatter

        record = logging.LogRecord(
            name="nexora.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello %s",
            args=("world",),
            exc_info=None,
        )
        payload = json.loads(JsonFormatter().format(record))
        self.assertEqual(payload["level"], "INFO")
        self.assertEqual(payload["message"], "hello world")

    def test_setup_logging_returns_root_logger(self):
        from nexora_node_sdk.logging_config import setup_logging

        logger = setup_logging(level="WARNING")
        self.assertEqual(logger.name, "root")
        self.assertGreaterEqual(len(logger.handlers), 1)


class SyncEngineCoverageTests(unittest.TestCase):
    def test_execute_sync_plan_dry_run(self):
        from nexora_node_sdk.sync_engine import execute_sync_plan

        report = execute_sync_plan({"targets": [{"target_node": "n1", "actions": ["a", "b"]}]}, dry_run=True)
        self.assertTrue(report["dry_run"])
        self.assertEqual(report["total_actions"], 2)
        self.assertEqual(report["targets"][0]["actions"][0]["status"], "planned")

    def test_rollback_sync_execution(self):
        from nexora_node_sdk.sync_engine import rollback_sync_execution

        report = rollback_sync_execution({"targets": [{"target_node": "n1", "actions": [{}, {}]}]})
        self.assertTrue(report["rolled_back"])
        self.assertEqual(report["targets"][0]["reverted_actions"], 2)


class OverlayGuardCoverageTests(unittest.TestCase):
    def test_hmac_command_verification_roundtrip(self):
        from nexora_node_sdk import overlay_guard as og

        with tempfile.TemporaryDirectory() as tmp:
            guard_dir = Path(tmp) / "guard"
            secret_path = guard_dir / "saas_shared_secret"
            manifest_sig_path = Path(tmp) / "overlay" / "manifest.sig"
            tamper_path = guard_dir / "tamper_events.jsonl"
            with (
                mock.patch.object(og, "GUARD_DIR", guard_dir),
                mock.patch.object(og, "SAAS_SECRET_PATH", secret_path),
                mock.patch.object(og, "MANIFEST_SIG_PATH", manifest_sig_path),
                mock.patch.object(og, "TAMPER_LOG_PATH", tamper_path),
            ):
                og.store_saas_secret("s" * 64)
                now = datetime.now(timezone.utc).isoformat()
                payload = {"k": "v"}
                digest = og.hashlib.sha256(
                    json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
                ).hexdigest()
                sig = og.compute_command_hmac("s" * 64, action="deploy", timestamp=now, payload_digest=digest)
                ok, reason = og.verify_saas_command(action="deploy", timestamp=now, signature=sig, payload=payload)
                self.assertTrue(ok)
                self.assertEqual(reason, "ok")


class PrivilegedActionsCoverageTests(unittest.TestCase):
    def test_known_privileged_action_has_executor(self):
        from nexora_node_sdk.privileged_actions import build_privileged_execution_plan

        plan = build_privileged_execution_plan("hooks/install", {"tenant_id": "t1"})
        self.assertTrue(plan["requires_privileged_runtime"])
        self.assertEqual(plan["executor"], "control-plane")

    def test_unknown_privileged_action_still_returns_contract(self):
        from nexora_node_sdk.privileged_actions import build_privileged_execution_plan

        plan = build_privileged_execution_plan("unknown/action")
        self.assertEqual(plan["action"], "unknown/action")
        self.assertTrue(plan["requires_privileged_runtime"])


class AuthScopesCoverageTests(unittest.TestCase):
    def test_validate_trusted_actor_role_rejects_invalid(self):
        from nexora_node_sdk.auth._scopes import validate_trusted_actor_role

        with self.assertRaises(ValueError):
            validate_trusted_actor_role("super-admin")

    def test_token_tenant_scope_mapping_enforced(self):
        from nexora_node_sdk.auth import _scopes as scopes

        with tempfile.TemporaryDirectory() as tmp:
            map_path = Path(tmp) / "scopes.json"
            map_path.write_text(json.dumps({"tok1": ["tenant-a"]}), encoding="utf-8")
            old = os.environ.get("NEXORA_API_TOKEN_SCOPE_FILE")
            os.environ["NEXORA_API_TOKEN_SCOPE_FILE"] = str(map_path)
            try:
                self.assertTrue(scopes._enforce_token_tenant_scope("tok1", "tenant-a"))
                self.assertFalse(scopes._enforce_token_tenant_scope("tok1", "tenant-b"))
            finally:
                if old is None:
                    os.environ.pop("NEXORA_API_TOKEN_SCOPE_FILE", None)
                else:
                    os.environ["NEXORA_API_TOKEN_SCOPE_FILE"] = old


class AuthTokenCoverageTests(unittest.TestCase):
    def test_generate_session_token_contains_expected_fields(self):
        from nexora_node_sdk.auth._token import generate_session_token

        payload = generate_session_token(max_age_seconds=123)
        self.assertIn("session_token", payload)
        self.assertEqual(payload["max_age_seconds"], 123)

    def test_validate_session_age_invalid_input(self):
        from nexora_node_sdk.auth._token import validate_session_age

        self.assertFalse(validate_session_age("not-a-timestamp", max_age=10))

    def test_rotate_api_token_writes_file(self):
        from nexora_node_sdk.auth import _token

        with tempfile.TemporaryDirectory() as tmp:
            token_path = Path(tmp) / "api-token"
            token_path.write_text("old-token", encoding="utf-8")
            old_cached = _token._api_token
            _token._api_token = "old-token"
            try:
                result = _token.rotate_api_token(reason="test", token_file=token_path)
                self.assertTrue(result["rotated"])
                self.assertTrue(token_path.exists())
                self.assertNotEqual(token_path.read_text(encoding="utf-8").strip(), "old-token")
            finally:
                _token._api_token = old_cached


class AuthSecretStoreCoverageTests(unittest.TestCase):
    def test_issue_validate_consume_secret(self):
        from nexora_node_sdk.auth._secret_store import SecretStore

        with tempfile.TemporaryDirectory() as tmp:
            store = SecretStore(state_dir=tmp)
            issued = store.issue_scoped_secret("node", "node-1", ["read_inventory"], tenant_id="tenant-a", ttl_seconds=60)
            ok = store.validate_scoped_secret(
                issued["token"],
                "node",
                required_tenant_id="tenant-a",
                required_permission="read_inventory",
            )
            self.assertTrue(ok["valid"])
            store.consume_token(issued["token"])
            replay = store.validate_scoped_secret(issued["token"], "node", required_tenant_id="tenant-a")
            self.assertFalse(replay["valid"])


class OperatorActionsCoverageTests(unittest.TestCase):
    def test_supported_actions_are_sorted(self):
        from nexora_saas.operator_actions import list_supported_agent_actions

        actions = list_supported_agent_actions()
        self.assertEqual(actions, sorted(actions))

    def test_apply_branding_writes_state(self):
        from nexora_saas.operator_actions import apply_branding

        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            result = apply_branding("Nexora", "#112233", state_path=str(state_path))
            self.assertTrue(result["success"])
            payload = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["branding"]["brand_name"], "Nexora")


class NodeActionsCoverageTests(unittest.TestCase):
    def test_sanitize_params_redacts_sensitive_and_large_fields(self):
        from nexora_saas.node_actions import _sanitize_params

        sanitized = _sanitize_params({"token": "secret-value", "config": {"a": 1}, "name": "x" * 500})
        self.assertTrue(sanitized["token"]["redacted"])
        self.assertTrue(sanitized["config"]["redacted"])
        self.assertTrue(sanitized["name"]["truncated"])

    def test_validate_params_detects_missing_and_oversize(self):
        from nexora_saas.node_actions import ActionSpec, _validate_params

        spec = ActionSpec(
            action="test/action",
            handler=None,
            capacity_class="small",
            required_params=("tenant_id",),
            max_payload_bytes=5,
        )
        missing = _validate_params(spec, {}, dry_run=True, trace_id="t1")
        self.assertFalse(missing["success"])

        oversize = _validate_params(spec, {"tenant_id": "abc", "payload": "0123456789"}, dry_run=True, trace_id="t2")
        self.assertFalse(oversize["success"])


class NodeServiceCoverageTests(unittest.TestCase):
    def test_parse_cached_at_handles_invalid_values(self):
        from nexora_node_sdk.node_service import _parse_cached_at

        self.assertIsNone(_parse_cached_at(None))
        self.assertIsNone(_parse_cached_at("not-an-iso"))


if __name__ == "__main__":
    unittest.main()
