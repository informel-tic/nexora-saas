from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys
import json
import os

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import apps.control_plane.api as api_module
from nexora_node_sdk.auth import get_api_token, build_tenant_scope_claim
from nexora_saas.orchestrator import NexoraService


class P8BehavioralTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.repo_root = REPO_ROOT
        self.state_path = Path(self.tmp_dir.name) / "state.json"
        self.original_service = api_module.service
        api_module.service = NexoraService(self.repo_root, state_path=self.state_path)
        self.client = TestClient(api_module.app, raise_server_exceptions=False)
        self.headers = {
            "Authorization": f"Bearer {get_api_token()}",
            "X-Nexora-Action": "test-mutation",
            "Origin": "http://testserver",
            "Referer": "http://testserver/console",
        }

    def tearDown(self) -> None:
        os.environ.pop("NEXORA_API_TOKEN_SCOPE_FILE", None)
        os.environ.pop("NEXORA_API_TOKEN_ROLE_FILE", None)
        os.environ.pop("NEXORA_OPERATOR_ONLY_ENFORCE", None)
        os.environ.pop("NEXORA_DEPLOYMENT_SCOPE", None)
        api_module.service = self.original_service
        self.tmp_dir.cleanup()

    def test_adoption_report_api_happy_path(self):
        response = self.client.get("/api/adoption/report?domain=example.org&path=/nexora", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("safe_to_install", payload)
        self.assertIn("recommended_mode", payload)

    def test_adoption_import_rejects_missing_origin_and_referer(self):
        insecure_headers = {
            "Authorization": f"Bearer {get_api_token()}",
            "X-Nexora-Action": "test-mutation",
        }
        response = self.client.post("/api/adoption/import?domain=example.org&path=/nexora", headers=insecure_headers)
        self.assertEqual(response.status_code, 403)
        self.assertIn("Missing Origin/Referer", response.text)

    def test_adoption_import_is_idempotent_for_same_inputs(self):
        first = self.client.post("/api/adoption/import?domain=example.org&path=/nexora", headers=self.headers)
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.json()["imported"])
        self.assertFalse(first.json().get("idempotent", False))

        second = self.client.post("/api/adoption/import?domain=example.org&path=/nexora", headers=self.headers)
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.json()["imported"])
        self.assertTrue(second.json()["idempotent"])

        state = api_module.service.state.load()
        self.assertEqual(len(state.get("imports", [])), 1)
        adoption_snapshots = [s for s in state.get("inventory_snapshots", []) if s.get("kind") == "adoption-import"]
        self.assertEqual(len(adoption_snapshots), 1)
        self.assertIn("tenant_id", adoption_snapshots[0])

    def test_fleet_topology_filters_nodes_by_tenant_header(self):
        state = api_module.service.state.load()
        state["nodes"] = [
            {"node_id": "node-a-1", "tenant_id": "tenant-a", "status": "healthy"},
            {"node_id": "node-b-1", "tenant_id": "tenant-b", "status": "healthy"},
        ]
        api_module.service.state.save(state)

        response = self.client.get(
            "/api/fleet/topology",
            headers={**self.headers, "X-Nexora-Tenant-Id": "tenant-a"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        node_ids = {node.get("node_id") for node in payload.get("nodes", [])}
        self.assertIn("node-a-1", node_ids)
        self.assertNotIn("node-b-1", node_ids)

    def test_fleet_node_action_denies_cross_tenant_node_access(self):
        state = api_module.service.state.load()
        state["nodes"] = [
            {"node_id": "node-a-1", "tenant_id": "tenant-a", "status": "healthy"},
            {"node_id": "node-b-1", "tenant_id": "tenant-b", "status": "healthy"},
        ]
        api_module.service.state.save(state)

        response = self.client.post(
            "/api/fleet/nodes/node-b-1/action",
            json={"action": "inventory/refresh", "payload": {}},
            headers={**self.headers, "X-Nexora-Tenant-Id": "tenant-a"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("not enrolled under tenant", response.text)

    def test_dedicated_node_action_route_is_tenant_scoped(self):
        state = api_module.service.state.load()
        state["nodes"] = [
            {"node_id": "node-a-1", "tenant_id": "tenant-a", "status": "healthy"},
            {"node_id": "node-b-1", "tenant_id": "tenant-b", "status": "healthy"},
        ]
        api_module.service.state.save(state)

        denied = self.client.post(
            "/api/fleet/nodes/node-b-1/inventory/refresh",
            json={"payload": {}, "dry_run": True},
            headers={**self.headers, "X-Nexora-Tenant-Id": "tenant-a"},
        )
        self.assertEqual(denied.status_code, 403)
        self.assertIn("not enrolled under tenant", denied.text)

        allowed = self.client.post(
            "/api/fleet/nodes/node-a-1/inventory/refresh",
            json={"payload": {}, "dry_run": True},
            headers={**self.headers, "X-Nexora-Tenant-Id": "tenant-a"},
        )
        self.assertEqual(allowed.status_code, 200)
        payload = allowed.json()
        self.assertEqual(payload.get("action"), "inventory/refresh")
        self.assertEqual(payload.get("target_node_id"), "node-a-1")

    def test_lifecycle_route_denies_cross_tenant_node_access(self):
        state = api_module.service.state.load()
        state["nodes"] = [{"node_id": "node-b-1", "tenant_id": "tenant-b", "status": "healthy"}]
        api_module.service.state.save(state)

        response = self.client.post(
            "/api/fleet/nodes/node-b-1/drain",
            json={"operator": "tenant-a-user", "confirmation": True},
            headers={**self.headers, "X-Nexora-Tenant-Id": "tenant-a"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("not enrolled under tenant", response.text)

    def test_tenant_header_must_match_token_scope_when_scope_file_is_configured(self):
        scope_file = Path(self.tmp_dir.name) / "token-scopes.json"
        scope_file.write_text(
            json.dumps({get_api_token(): ["tenant-a"]}),
            encoding="utf-8",
        )
        os.environ["NEXORA_API_TOKEN_SCOPE_FILE"] = str(scope_file)

        denied = self.client.get(
            "/api/fleet",
            headers={**self.headers, "X-Nexora-Tenant-Id": "tenant-b"},
        )
        self.assertEqual(denied.status_code, 403)
        self.assertIn("not authorized for tenant scope", denied.text)

        allowed = self.client.get(
            "/api/fleet",
            headers={
                **self.headers,
                "X-Nexora-Tenant-Id": "tenant-a",
                "X-Nexora-Tenant-Claim": build_tenant_scope_claim(get_api_token(), "tenant-a"),
            },
        )
        self.assertEqual(allowed.status_code, 200)

    def test_snapshot_diff_filters_by_tenant(self):
        state = api_module.service.state.load()
        state["inventory_snapshots"] = [
            {"timestamp": "2026-03-24T00:00:00Z", "kind": "heartbeat", "inventory": {"apps": {"a": 1}}, "tenant_id": "tenant-a"},
            {"timestamp": "2026-03-24T00:01:00Z", "kind": "heartbeat", "inventory": {"apps": {"a": 2}}, "tenant_id": "tenant-a"},
            {"timestamp": "2026-03-24T00:02:00Z", "kind": "heartbeat", "inventory": {"apps": {"b": 1}}, "tenant_id": "tenant-b"},
            {"timestamp": "2026-03-24T00:03:00Z", "kind": "heartbeat", "inventory": {"apps": {"b": 3}}, "tenant_id": "tenant-b"},
        ]
        api_module.service.state.save(state)

        tenant_a = self.client.get("/api/governance/snapshot-diff", headers={**self.headers, "X-Nexora-Tenant-Id": "tenant-a"})
        self.assertEqual(tenant_a.status_code, 200)
        self.assertNotEqual(tenant_a.json().get("diff"), {})

        tenant_c = self.client.get("/api/governance/snapshot-diff", headers={**self.headers, "X-Nexora-Tenant-Id": "tenant-c"})
        self.assertEqual(tenant_c.status_code, 200)
        self.assertEqual(tenant_c.json(), {"diff": {}})

    def test_governance_scores_and_report_include_tenant_scope(self):
        state = api_module.service.state.load()
        state["inventory_snapshots"] = [
            {"timestamp": "2026-03-24T00:00:00Z", "kind": "heartbeat", "inventory": {"apps": {"apps": ["a"]}}, "tenant_id": "tenant-a"},
            {"timestamp": "2026-03-24T00:01:00Z", "kind": "heartbeat", "inventory": {"apps": {"apps": ["b", "c"]}}, "tenant_id": "tenant-b"},
        ]
        api_module.service.state.save(state)

        scores = self.client.get("/api/scores", headers={**self.headers, "X-Nexora-Tenant-Id": "tenant-a"})
        self.assertEqual(scores.status_code, 200)
        self.assertEqual(scores.json().get("tenant_id"), "tenant-a")

        report = self.client.get("/api/governance/report", headers={**self.headers, "X-Nexora-Tenant-Id": "tenant-a"})
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.json().get("tenant_id"), "tenant-a")

        risks = self.client.get("/api/governance/risks", headers={**self.headers, "X-Nexora-Tenant-Id": "tenant-a"})
        self.assertEqual(risks.status_code, 200)
        self.assertEqual(risks.json().get("tenant_id"), "tenant-a")

        posture = self.client.get("/api/security/posture", headers={**self.headers, "X-Nexora-Tenant-Id": "tenant-a"})
        self.assertEqual(posture.status_code, 200)
        self.assertEqual(posture.json().get("tenant_id"), "tenant-a")

        pra = self.client.get("/api/pra", headers={**self.headers, "X-Nexora-Tenant-Id": "tenant-a"})
        self.assertEqual(pra.status_code, 200)
        self.assertEqual(pra.json().get("tenant_id"), "tenant-a")

    def test_token_scope_denial_applies_to_governance_routes(self):
        scope_file = Path(self.tmp_dir.name) / "token-scopes-governance.json"
        scope_file.write_text(json.dumps({get_api_token(): ["tenant-a"]}), encoding="utf-8")
        os.environ["NEXORA_API_TOKEN_SCOPE_FILE"] = str(scope_file)

        denied = self.client.get(
            "/api/governance/risks",
            headers={**self.headers, "X-Nexora-Tenant-Id": "tenant-b"},
        )
        self.assertEqual(denied.status_code, 403)
        self.assertTrue(
            "not authorized for tenant scope" in denied.text
            or "Missing or invalid X-Nexora-Tenant-Claim" in denied.text
        )

    def test_token_scoped_access_requires_valid_tenant_claim(self):
        scope_file = Path(self.tmp_dir.name) / "token-scopes-claim.json"
        scope_file.write_text(json.dumps({get_api_token(): ["tenant-a"]}), encoding="utf-8")
        os.environ["NEXORA_API_TOKEN_SCOPE_FILE"] = str(scope_file)

        missing_claim = self.client.get(
            "/api/fleet",
            headers={**self.headers, "X-Nexora-Tenant-Id": "tenant-a"},
        )
        self.assertEqual(missing_claim.status_code, 403)
        self.assertIn("Missing or invalid X-Nexora-Tenant-Claim", missing_claim.text)

        valid_claim = self.client.get(
            "/api/fleet",
            headers={
                **self.headers,
                "X-Nexora-Tenant-Id": "tenant-a",
                "X-Nexora-Tenant-Claim": build_tenant_scope_claim(get_api_token(), "tenant-a"),
            },
        )
        self.assertEqual(valid_claim.status_code, 200)

    def test_token_scoped_access_requires_tenant_header(self):
        scope_file = Path(self.tmp_dir.name) / "token-scopes-header.json"
        scope_file.write_text(json.dumps({get_api_token(): ["tenant-a"]}), encoding="utf-8")
        os.environ["NEXORA_API_TOKEN_SCOPE_FILE"] = str(scope_file)

        denied = self.client.get("/api/fleet", headers=self.headers)
        self.assertEqual(denied.status_code, 403)
        self.assertIn("Scoped token access requires X-Nexora-Tenant-Id header", denied.text)

        allowed = self.client.get(
            "/api/fleet",
            headers={
                **self.headers,
                "X-Nexora-Tenant-Id": "tenant-a",
                "X-Nexora-Tenant-Claim": build_tenant_scope_claim(get_api_token(), "tenant-a"),
            },
        )
        self.assertEqual(allowed.status_code, 200)

    def test_operator_only_routes_require_trusted_actor_binding(self):
        os.environ["NEXORA_OPERATOR_ONLY_ENFORCE"] = "1"
        denied = self.client.get("/api/persistence", headers=self.headers)
        self.assertEqual(denied.status_code, 403)
        self.assertIn("Operator-only route", denied.text)

        role_file = Path(self.tmp_dir.name) / "token-roles.json"
        role_file.write_text(json.dumps({get_api_token(): "operator"}), encoding="utf-8")
        os.environ["NEXORA_API_TOKEN_ROLE_FILE"] = str(role_file)
        allowed = self.client.get(
            "/api/persistence",
            headers={**self.headers, "X-Nexora-Actor-Role": "operator"},
        )
        self.assertEqual(allowed.status_code, 200)

    def test_operator_only_routes_reject_role_header_spoofing(self):
        os.environ["NEXORA_OPERATOR_ONLY_ENFORCE"] = "1"
        role_file = Path(self.tmp_dir.name) / "token-roles.json"
        role_file.write_text(json.dumps({get_api_token(): "admin"}), encoding="utf-8")
        os.environ["NEXORA_API_TOKEN_ROLE_FILE"] = str(role_file)

        denied = self.client.get(
            "/api/persistence",
            headers={**self.headers, "X-Nexora-Actor-Role": "operator"},
        )
        self.assertEqual(denied.status_code, 403)
        self.assertIn("does not match trusted credentials", denied.text)

    def test_operator_only_enforcement_can_be_disabled(self):
        os.environ["NEXORA_OPERATOR_ONLY_ENFORCE"] = "0"
        response = self.client.get("/api/interface-parity/fleet-lifecycle", headers=self.headers)
        self.assertEqual(response.status_code, 200)

    def test_usage_quota_endpoint_returns_tenant_scoped_payload(self):
        state = api_module.service.state.load()
        state["tenants"] = [
            {"tenant_id": "tenant-a", "org_id": "org-a", "name": "Tenant A", "tier": "free", "created_at": "2026-03-24T00:00:00Z"},
            {"tenant_id": "tenant-b", "org_id": "org-b", "name": "Tenant B", "tier": "pro", "created_at": "2026-03-24T00:00:00Z"},
        ]
        state["nodes"] = [
            {"node_id": "node-a1", "tenant_id": "tenant-a", "apps_count": 4, "storage_gb": 6},
            {"node_id": "node-b1", "tenant_id": "tenant-b", "apps_count": 40, "storage_gb": 80},
        ]
        api_module.service.state.save(state)

        scoped = self.client.get(
            "/api/tenants/usage-quota",
            headers={**self.headers, "X-Nexora-Tenant-Id": "tenant-a"},
        )
        self.assertEqual(scoped.status_code, 200)
        payload = scoped.json()
        self.assertEqual(payload.get("tenant_id"), "tenant-a")
        self.assertEqual(payload.get("limits", {}).get("max_nodes"), 5)
        self.assertEqual(payload.get("usage", {}).get("nodes_count"), 1)
        self.assertFalse(payload.get("exceeded", {}).get("max_nodes"))

    def test_usage_quota_endpoint_reports_unknown_tenant(self):
        state = api_module.service.state.load()
        state["tenants"] = [
            {"tenant_id": "tenant-a", "org_id": "org-a", "name": "Tenant A", "tier": "free", "created_at": "2026-03-24T00:00:00Z"},
        ]
        api_module.service.state.save(state)

        response = self.client.get(
            "/api/tenants/usage-quota",
            headers={**self.headers, "X-Nexora-Tenant-Id": "tenant-missing"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload.get("tenant_id"), "tenant-missing")
        self.assertIn("Unknown tenant_id", payload.get("error", ""))

    def test_security_secondary_routes_are_tenant_scoped(self):
        for route in (
            "/api/security/updates",
            "/api/security/fail2ban/status",
            "/api/security/open-ports",
            "/api/security/permissions-audit",
            "/api/security/recent-logins",
        ):
            response = self.client.get(route, headers={**self.headers, "X-Nexora-Tenant-Id": "tenant-a"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json().get("tenant_id"), "tenant-a")

    def test_fail2ban_mutations_tag_security_audit_with_tenant(self):
        response = self.client.post(
            "/api/security/fail2ban/ban?ip=1.2.3.4",
            headers={**self.headers, "X-Nexora-Tenant-Id": "tenant-a"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("tenant_id"), "tenant-a")

        state = api_module.service.state.load()
        events = state.get("security_audit", [])
        self.assertTrue(events)
        self.assertEqual(events[-1].get("action"), "fail2ban_ban")
        self.assertEqual(events[-1].get("tenant_id"), "tenant-a")

    def test_fail2ban_mutation_requires_valid_tenant_claim_when_scoped(self):
        scope_file = Path(self.tmp_dir.name) / "token-scopes-fail2ban.json"
        scope_file.write_text(json.dumps({get_api_token(): ["tenant-a"]}), encoding="utf-8")
        os.environ["NEXORA_API_TOKEN_SCOPE_FILE"] = str(scope_file)

        denied = self.client.post(
            "/api/security/fail2ban/unban?ip=1.2.3.4",
            headers={**self.headers, "X-Nexora-Tenant-Id": "tenant-a"},
        )
        self.assertEqual(denied.status_code, 403)
        self.assertIn("Missing or invalid X-Nexora-Tenant-Claim", denied.text)

        allowed = self.client.post(
            "/api/security/fail2ban/unban?ip=1.2.3.4",
            headers={
                **self.headers,
                "X-Nexora-Tenant-Id": "tenant-a",
                "X-Nexora-Tenant-Claim": build_tenant_scope_claim(get_api_token(), "tenant-a"),
            },
        )
        self.assertEqual(allowed.status_code, 200)


class PackagingBlockP8ContractTests(unittest.TestCase):
    def test_remove_script_supports_purge_mode_and_audit_report(self):
        script = Path("ynh-package/scripts/remove").read_text(encoding="utf-8")
        self.assertIn('UNINSTALL_MODE="${NEXORA_UNINSTALL_MODE:-preserve}"', script)
        self.assertIn('/var/log/nexora-uninstall-report.json', script)
        self.assertIn('if [ "$UNINSTALL_MODE" = "purge" ]; then', script)

    def test_python_stack_supports_offline_bundle(self):
        script = Path("ynh-package/scripts/_common.sh").read_text(encoding="utf-8")
        self.assertIn('NEXORA_WHEEL_BUNDLE_DIR', script)
        self.assertIn('install --no-index --find-links', script)
        self.assertIn('nexora_platform-*.whl', script)

    def test_bootstrap_supports_offline_bundle_install(self):
        script = Path("deploy/bootstrap-node.sh").read_text(encoding="utf-8")
        self.assertIn('NEXORA_WHEEL_BUNDLE_DIR', script)
        self.assertIn('install --no-index --find-links', script)
        self.assertIn('nexora_platform-*.whl', script)
        self.assertIn('NEXORA_ALLOW_ONLINE_WHEEL_FALLBACK', script)
        self.assertIn('falling back to online install', script)

    def test_offline_bundle_builder_exists(self):
        script = Path("scripts/build_offline_bundle.sh")
        self.assertTrue(script.exists())
        if os.name == "nt":
            # Windows filesystems do not expose POSIX executable bits.
            return
        self.assertTrue(script.stat().st_mode & 0o111)


if __name__ == "__main__":
    unittest.main()
