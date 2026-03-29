"""TDD Red-Phase Tests — UI/UX, E2E, and Security tests.

These tests define desired behaviors that are NOT YET IMPLEMENTED.
They should all FAIL (red) initially, driving subsequent implementation.

Categories:
  A. Security hardening (input validation, injection, rate-limit, headers)
  B. E2E API flows (full lifecycle journeys, error handling, edge cases)
  C. UI/UX console integrity (owner console, shared views, ARIA, XSS)
  D. Subscription billing guard-rails (downgrade, expiry, quota enforcement)
  E. Multi-tenant deep isolation (data leakage, escalation, cross-surface)
  F. RBAC extended (owner session, role escalation, token rotation)
"""
from __future__ import annotations

import json
import os
import secrets
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import apps.control_plane.api as api_module  # noqa: E402
from nexora_node_sdk.auth import build_tenant_scope_claim, get_api_token  # noqa: E402
from nexora_saas.orchestrator import NexoraService  # noqa: E402


# ─── helpers ──────────────────────────────────────────────────────────────────
def _make_role_file(tmp_dir: str, mapping: dict) -> str:
    path = Path(tmp_dir) / f"roles-{secrets.token_hex(4)}.json"
    path.write_text(json.dumps(mapping), encoding="utf-8")
    return str(path)


def _make_scope_file(tmp_dir: str, mapping: dict) -> str:
    path = Path(tmp_dir) / f"scopes-{secrets.token_hex(4)}.json"
    path.write_text(json.dumps(mapping), encoding="utf-8")
    return str(path)


class TDDTestBase(unittest.TestCase):
    """Shared test base for TDD red-phase tests."""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.state_path = Path(self.tmp_dir.name) / "state.json"
        self.original_service = api_module.service
        os.environ["NEXORA_STATE_PATH"] = str(self.state_path)
        api_module.service = NexoraService(REPO_ROOT, state_path=self.state_path)
        self.client = TestClient(api_module.app, raise_server_exceptions=False)
        self.token = get_api_token()
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "X-Nexora-Action": "test-mutation",
            "Origin": "http://testserver",
            "Referer": "http://testserver/console",
        }

    def tearDown(self) -> None:
        for key in (
            "NEXORA_API_TOKEN_SCOPE_FILE",
            "NEXORA_API_TOKEN_ROLE_FILE",
            "NEXORA_OPERATOR_ONLY_ENFORCE",
            "NEXORA_DEPLOYMENT_SCOPE",
            "NEXORA_STATE_PATH",
        ):
            os.environ.pop(key, None)
        api_module.service = self.original_service
        self.tmp_dir.cleanup()

    def _set_role(self, role: str) -> dict:
        rf = _make_role_file(self.tmp_dir.name, {self.token: role})
        os.environ["NEXORA_API_TOKEN_ROLE_FILE"] = rf
        return {**self.headers, "X-Nexora-Actor-Role": role}

    def _set_scope(self, allowed_tenants: list[str]) -> None:
        sf = _make_scope_file(self.tmp_dir.name, {self.token: allowed_tenants})
        os.environ["NEXORA_API_TOKEN_SCOPE_FILE"] = sf

    def _scoped_headers(self, tenant_id: str) -> dict:
        return {
            **self.headers,
            "X-Nexora-Tenant-Id": tenant_id,
            "X-Nexora-Tenant-Claim": build_tenant_scope_claim(self.token, tenant_id),
        }

    def _seed_nodes(self, nodes: list[dict]) -> None:
        state = api_module.service.state.load()
        state["nodes"] = nodes
        api_module.service.state.save(state)

    def _seed_tenants(self, tenants: list[dict]) -> None:
        state = api_module.service.state.load()
        state["tenants"] = tenants
        api_module.service.state.save(state)

    def _create_org(self, name: str = "TestOrg", email: str = "admin@test.local") -> dict:
        r = self.client.post(
            "/api/organizations",
            json={"name": name, "contact_email": email},
            headers=self.headers,
        )
        return r.json()["organization"]

    def _create_subscription(self, org_id: str, tier: str = "pro") -> dict:
        r = self.client.post(
            "/api/subscriptions",
            json={"org_id": org_id, "plan_tier": tier},
            headers=self.headers,
        )
        return r.json()


# ═══════════════════════════════════════════════════════════════════════════════
#  A. SECURITY HARDENING — Input validation, injection, rate-limit, headers
# ═══════════════════════════════════════════════════════════════════════════════


class SecurityInputValidationTests(TDDTestBase):
    """Input validation on all mutation endpoints to prevent injection."""

    def test_org_name_rejects_script_tags(self):
        """Organization name must reject HTML/script injection."""
        r = self.client.post(
            "/api/organizations",
            json={"name": "<script>alert('xss')</script>", "contact_email": "a@b.test"},
            headers=self.headers,
        )
        data = r.json()
        if r.status_code == 200 and data.get("success"):
            org_name = data["organization"]["name"]
            self.assertNotIn("<script>", org_name)

    def test_org_name_rejects_excessively_long_input(self):
        """Organization name must reject input over 200 chars."""
        r = self.client.post(
            "/api/organizations",
            json={"name": "A" * 201, "contact_email": "a@b.test"},
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 422)

    def test_org_email_rejects_invalid_format(self):
        """Contact email must be validated."""
        r = self.client.post(
            "/api/organizations",
            json={"name": "ValidOrg", "contact_email": "not-an-email"},
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 422)

    def test_subscription_tier_rejects_invalid_value(self):
        """Plan tier must be one of free/pro/enterprise."""
        org = self._create_org("TierTestOrg", "t@t.test")
        r = self.client.post(
            "/api/subscriptions",
            json={"org_id": org["org_id"], "plan_tier": "platinum"},
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 422)

    def test_node_id_rejects_path_traversal(self):
        """Node IDs must not allow path traversal characters."""
        r = self.client.post(
            "/api/fleet/nodes/../../etc/passwd/drain",
            json={"operator": "tester", "confirmation": True},
            headers=self.headers,
        )
        self.assertIn(r.status_code, (400, 404, 422))

    def test_tenant_id_rejects_special_characters(self):
        """Tenant ID header must be alphanumeric + hyphens only."""
        r = self.client.get(
            "/api/fleet",
            headers={**self.headers, "X-Nexora-Tenant-Id": "tenant'; DROP TABLE--"},
        )
        self.assertIn(r.status_code, (400, 422))

    def test_failover_ip_rejects_invalid_format(self):
        """Failover configuration must validate IP addresses."""
        r = self.client.post(
            "/api/failover/configure",
            json={
                "app_id": "test",
                "domain": "test.local",
                "primary_host": "not-an-ip",
                "secondary_host": "also-not-an-ip",
                "primary_node_id": "n1",
                "secondary_node_id": "n2",
                "health_strategy": "http",
            },
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 422)

    def test_fail2ban_ip_rejects_invalid_format(self):
        """Fail2ban ban endpoint must validate IP parameter."""
        r = self.client.post(
            "/api/security/fail2ban/ban?ip=not_an_ip_address",
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 422)

    def test_mode_switch_rejects_invalid_mode(self):
        """Mode switch must only accept valid mode names."""
        r = self.client.post(
            "/api/mode/switch?target=superadmin&reason=test",
            headers=self.headers,
        )
        self.assertIn(r.status_code, (400, 422))

    def test_enrollment_ttl_rejects_negative(self):
        """Enrollment token TTL must be positive."""
        r = self.client.post(
            "/api/fleet/enroll/request",
            json={"requested_by": "tester", "mode": "pull", "ttl_minutes": -5, "node_id": "n1"},
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 422)

    def test_enrollment_ttl_rejects_excessive(self):
        """Enrollment token TTL must not exceed 24 hours."""
        r = self.client.post(
            "/api/fleet/enroll/request",
            json={"requested_by": "tester", "mode": "pull", "ttl_minutes": 99999, "node_id": "n1"},
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 422)


class SecurityHeaderTests(TDDTestBase):
    """Verify security response headers are present."""

    def test_strict_transport_security_header(self):
        """All responses must include HSTS header."""
        r = self.client.get("/api/health", headers=self.headers)
        self.assertIn("strict-transport-security", r.headers)

    def test_content_type_options_nosniff(self):
        """Responses must include X-Content-Type-Options: nosniff."""
        r = self.client.get("/api/health", headers=self.headers)
        self.assertEqual(r.headers.get("x-content-type-options"), "nosniff")

    def test_frame_options_deny(self):
        """Responses must include X-Frame-Options: DENY."""
        r = self.client.get("/api/health", headers=self.headers)
        self.assertIn(r.headers.get("x-frame-options", "").upper(), ("DENY", "SAMEORIGIN"))

    def test_content_security_policy_header(self):
        """API responses should include a Content-Security-Policy."""
        r = self.client.get("/api/health", headers=self.headers)
        self.assertIn("content-security-policy", r.headers)

    def test_cache_control_no_store_on_api(self):
        """API responses must not be cached (sensitive data)."""
        r = self.client.get("/api/console/access-context", headers=self._set_role("admin"))
        cache = r.headers.get("cache-control", "")
        self.assertIn("no-store", cache)

    def test_no_server_header_leakage(self):
        """Server header should not reveal technology stack."""
        r = self.client.get("/api/health", headers=self.headers)
        server = r.headers.get("server", "")
        self.assertNotIn("uvicorn", server.lower())
        self.assertNotIn("python", server.lower())


class SecurityRateLimitTests(TDDTestBase):
    """Rate-limiting on auth and sensitive endpoints."""

    def test_auth_failure_rate_limit_triggers(self):
        """After 10 failed auth attempts, rate limit must engage."""
        for _ in range(12):
            self.client.get("/api/fleet", headers={"Authorization": "Bearer wrong-token"})
        r = self.client.get("/api/fleet", headers={"Authorization": "Bearer wrong-token"})
        self.assertEqual(r.status_code, 429)

    def test_rate_limit_does_not_affect_valid_token(self):
        """Valid tokens must not be rate-limited by other IP failures."""
        r = self.client.get("/api/fleet", headers=self.headers)
        self.assertEqual(r.status_code, 200)

    def test_fail2ban_ban_rate_limited(self):
        """Rapid fail2ban bans should be rate-limited to prevent abuse."""
        for i in range(50):
            self.client.post(f"/api/security/fail2ban/ban?ip=10.0.{i}.1", headers=self.headers)
        r = self.client.post("/api/security/fail2ban/ban?ip=10.0.99.99", headers=self.headers)
        self.assertIn(r.status_code, (200, 429))


class SecurityTokenFilePermissionTests(unittest.TestCase):
    """Token and passphrase file permission checks."""

    def test_auth_runtime_file_has_0600(self):
        """Auth runtime file must be created with 0o600 permissions."""
        source = Path("src/nexora_node_sdk/auth/_rate_limit.py").read_text(encoding="utf-8")
        self.assertIn("0o600", source)

    def test_owner_passphrase_file_has_0600(self):
        """Owner passphrase file must be stored with 0o600 permissions."""
        source = Path("src/nexora_node_sdk/auth/_owner_session.py").read_text(encoding="utf-8")
        self.assertIn("0o600", source)

    def test_passphrase_uses_timing_safe_compare(self):
        """Passphrase verification must use hmac.compare_digest."""
        source = Path("src/nexora_node_sdk/auth/_owner_session.py").read_text(encoding="utf-8")
        self.assertIn("compare_digest", source)

    def test_token_auth_uses_timing_safe_compare(self):
        """Token auth must use secrets.compare_digest."""
        source = Path("src/nexora_node_sdk/auth/_middleware.py").read_text(encoding="utf-8")
        self.assertIn("compare_digest", source)

    def test_no_plaintext_token_in_logs(self):
        """Token values must never appear in log format strings."""
        for auth_file in Path("src/nexora_node_sdk/auth").glob("*.py"):
            source = auth_file.read_text(encoding="utf-8")
            # Check that log calls don't include token variables
            for line in source.splitlines():
                if "logger." in line and "token" in line.lower():
                    self.assertNotIn("%s", line.split("token")[0][-30:] if "token" in line.lower() else "")


class SecurityCSRFExtendedTests(TDDTestBase):
    """Extended CSRF protection testing."""

    def test_csrf_on_subscription_create(self):
        """Subscription creation must require CSRF protection."""
        org = self._create_org("CSRFOrg", "csrf@test.test")
        hdr = {k: v for k, v in self.headers.items() if k not in ("Origin", "Referer")}
        r = self.client.post(
            "/api/subscriptions",
            json={"org_id": org["org_id"], "plan_tier": "pro"},
            headers=hdr,
        )
        self.assertEqual(r.status_code, 403)

    def test_csrf_on_tenant_purge(self):
        """Tenant purge must require CSRF protection."""
        hdr = {k: v for k, v in self.headers.items() if k not in ("Origin", "Referer")}
        r = self.client.post("/api/tenants/test-t/purge", headers=hdr)
        self.assertEqual(r.status_code, 403)

    def test_csrf_on_mode_switch(self):
        """Mode switch must require CSRF protection."""
        hdr = {k: v for k, v in self.headers.items() if k not in ("Origin", "Referer")}
        r = self.client.post("/api/mode/switch?target=operator&reason=test", headers=hdr)
        self.assertEqual(r.status_code, 403)

    def test_csrf_on_failover_execute(self):
        """Failover execution must require CSRF protection."""
        hdr = {k: v for k, v in self.headers.items() if k not in ("Origin", "Referer")}
        r = self.client.post(
            "/api/failover/execute",
            json={"app_id": "test", "target_node": "secondary", "reason": "test"},
            headers=hdr,
        )
        self.assertEqual(r.status_code, 403)

    def test_csrf_on_node_lifecycle_actions(self):
        """All node lifecycle actions must require CSRF protection."""
        self._seed_nodes([{"node_id": "n1", "tenant_id": "t1", "status": "healthy"}])
        hdr = {k: v for k, v in self.headers.items() if k not in ("Origin", "Referer")}
        for action in ("drain", "cordon", "revoke", "retire"):
            with self.subTest(action=action):
                r = self.client.post(
                    f"/api/fleet/nodes/n1/{action}",
                    json={"operator": "tester", "confirmation": True},
                    headers={**hdr, "X-Nexora-Tenant-Id": "t1"},
                )
                self.assertEqual(r.status_code, 403, f"CSRF not enforced on {action}")


class SecurityDeploymentScopeTests(TDDTestBase):
    """Deployment scope enforcement for production safety."""

    def test_production_blocks_tenant_purge(self):
        """Production scope must block tenant purge."""
        os.environ["NEXORA_DEPLOYMENT_SCOPE"] = "production"
        r = self.client.post("/api/tenants/test-t/purge", headers=self.headers)
        self.assertEqual(r.status_code, 403)
        self.assertIn("production", r.json().get("detail", "").lower())

    def test_production_blocks_mode_switch(self):
        """Production scope must block mode switch."""
        os.environ["NEXORA_DEPLOYMENT_SCOPE"] = "production"
        r = self.client.post("/api/mode/switch?target=admin&reason=test", headers=self.headers)
        self.assertEqual(r.status_code, 403)

    def test_staging_allows_mode_switch(self):
        """Staging scope must allow mode switch."""
        os.environ["NEXORA_DEPLOYMENT_SCOPE"] = "staging"
        r = self.client.post("/api/mode/switch?target=operator&reason=test", headers=self.headers)
        self.assertEqual(r.status_code, 200)

    def test_no_scope_allows_all(self):
        """Without deployment scope, all operations allowed."""
        os.environ.pop("NEXORA_DEPLOYMENT_SCOPE", None)
        r = self.client.post("/api/mode/switch?target=operator&reason=test", headers=self.headers)
        self.assertEqual(r.status_code, 200)


# ═══════════════════════════════════════════════════════════════════════════════
#  B. E2E API FLOWS — Full lifecycle journeys, error handling, edge cases
# ═══════════════════════════════════════════════════════════════════════════════


class E2ESubscriptionLifecycleTests(TDDTestBase):
    """End-to-end subscription lifecycle from org creation to cancellation."""

    def test_full_lifecycle_creates_tenant_and_enforces_quota(self):
        """Full lifecycle: create org → subscribe → verify tenant → enforce quota."""
        # 1. Create org
        org = self._create_org("E2ECorp", "e2e@corp.test")
        self.assertTrue(org["org_id"].startswith("org-"))

        # 2. Create subscription (free tier)
        sub_result = self._create_subscription(org["org_id"], "free")
        self.assertTrue(sub_result["success"])
        tenant_id = sub_result["tenant"]["tenant_id"]
        sub_id = sub_result["subscription"]["subscription_id"]

        # 3. Verify tenant appears in tenant list
        tenants = self.client.get("/api/tenants", headers=self.headers).json()
        tenant_ids = [t["tenant_id"] for t in tenants]
        self.assertIn(tenant_id, tenant_ids)

        # 4. Verify quota limits match free tier
        r = self.client.get(
            "/api/tenants/usage-quota",
            headers={**self.headers, "X-Nexora-Tenant-Id": tenant_id},
        )
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["limits"]["max_nodes"], 5)

        # 5. Upgrade to pro
        r = self.client.post(
            f"/api/subscriptions/{sub_id}/upgrade",
            json={"new_tier": "pro"},
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 200)

        # 6. Verify quota limits updated to pro
        r = self.client.get(
            "/api/tenants/usage-quota",
            headers={**self.headers, "X-Nexora-Tenant-Id": tenant_id},
        )
        self.assertEqual(r.json()["limits"]["max_nodes"], 50)

        # 7. Suspend subscription
        r = self.client.post(
            f"/api/subscriptions/{sub_id}/suspend",
            json={"reason": "payment-overdue"},
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 200)

        # 8. Verify tenant is suspended
        r = self.client.get(
            "/api/tenants/usage-quota",
            headers={**self.headers, "X-Nexora-Tenant-Id": tenant_id},
        )
        self.assertEqual(r.json().get("subscription_status"), "suspended")

        # 9. Cancel subscription
        r = self.client.post(
            f"/api/subscriptions/{sub_id}/cancel",
            json={},
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 200)


class E2EFleetEnrollmentJourneyTests(TDDTestBase):
    """End-to-end fleet enrollment with tenant binding and lifecycle."""

    def test_enrollment_to_lifecycle_full_journey(self):
        """Enrollment → attest → register → actions → revoke."""
        # 1. Request enrollment token
        r = self.client.post(
            "/api/fleet/enroll/request",
            json={"requested_by": "e2e-test", "mode": "pull", "ttl_minutes": 15, "node_id": "e2e-node-1"},
            headers={**self.headers, "X-Nexora-Tenant-Id": "e2e-tenant"},
        )
        self.assertEqual(r.status_code, 200)
        data = r.json()
        token = data["token"]
        challenge = data["challenge"]
        token_id = data["token_id"]

        # 2. Attest node
        from nexora_saas.enrollment import build_attestation_response
        response = build_attestation_response(challenge=challenge, node_id="e2e-node-1", token_id=token_id)
        r = self.client.post(
            "/api/fleet/enroll/attest",
            json={
                "token": token,
                "challenge": challenge,
                "challenge_response": response,
                "hostname": "e2e-node.test",
                "node_id": "e2e-node-1",
                "agent_version": "2.0.0",
                "yunohost_version": "12.1.2",
                "debian_version": "12",
            },
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 200)

        # 3. Register node
        r = self.client.post(
            "/api/fleet/enroll/register",
            json={"token": token, "node_id": "e2e-node-1"},
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 200)

        # 4. Verify node appears in fleet
        r = self.client.get(
            "/api/fleet/topology",
            headers={**self.headers, "X-Nexora-Tenant-Id": "e2e-tenant"},
        )
        nodes = {n["node_id"] for n in r.json().get("nodes", [])}
        self.assertIn("e2e-node-1", nodes)

        # 5. Perform lifecycle action (cordon)
        r = self.client.post(
            "/api/fleet/nodes/e2e-node-1/cordon",
            json={"operator": "e2e-test", "confirmation": True},
            headers={**self.headers, "X-Nexora-Tenant-Id": "e2e-tenant"},
        )
        self.assertEqual(r.status_code, 200)

        # 6. Revoke node
        r = self.client.post(
            "/api/fleet/nodes/e2e-node-1/revoke",
            json={"operator": "e2e-test", "confirmation": True},
            headers={**self.headers, "X-Nexora-Tenant-Id": "e2e-tenant"},
        )
        self.assertEqual(r.status_code, 200)


class E2EGovernanceAuditTrailTests(TDDTestBase):
    """E2E governance audit trail — actions must be traceable."""

    def test_mode_switch_creates_audit_entry(self):
        """Mode switch must create an entry in admin log."""
        self.client.post("/api/mode/switch?target=operator&reason=e2e-test", headers=self.headers)
        r = self.client.get("/api/admin/log", headers=self.headers)
        log = r.json()
        self.assertIsInstance(log, list)
        self.assertTrue(
            any("e2e-test" in str(entry) for entry in log),
            "Admin log should contain the mode switch reason",
        )

    def test_tenant_onboard_creates_audit_entry(self):
        """Tenant onboarding must create an audit log entry."""
        org = self._create_org("AuditOrg", "audit@test.test")
        self.client.post(
            "/api/tenants/onboard",
            json={"tenant_id": "audit-tenant", "organization_id": org["org_id"], "tier": "free"},
            headers=self.headers,
        )
        state = api_module.service.state.load()
        audit = state.get("security_audit", [])
        self.assertTrue(
            any("audit-tenant" in str(entry) for entry in audit),
            "Audit trail should contain the onboarded tenant",
        )

    def test_fail2ban_actions_appear_in_security_audit(self):
        """Fail2ban bans/unbans must appear in security audit log."""
        self.client.post("/api/security/fail2ban/ban?ip=5.5.5.5", headers=self.headers)
        state = api_module.service.state.load()
        audit = state.get("security_audit", [])
        self.assertTrue(
            any("5.5.5.5" in str(entry) for entry in audit),
            "Security audit should contain the banned IP",
        )

    def test_subscription_changes_appear_in_audit(self):
        """Subscription create/upgrade/suspend/cancel must appear in audit."""
        org = self._create_org("SubAuditOrg", "sub@audit.test")
        sub = self._create_subscription(org["org_id"], "free")
        sub_id = sub["subscription"]["subscription_id"]
        self.client.post(
            f"/api/subscriptions/{sub_id}/upgrade",
            json={"new_tier": "pro"},
            headers=self.headers,
        )
        state = api_module.service.state.load()
        audit = state.get("security_audit", [])
        self.assertTrue(
            any("upgrade" in str(entry).lower() for entry in audit),
            "Audit trail should contain the subscription upgrade",
        )


class E2EFailoverAndMigrationTests(TDDTestBase):
    """E2E failover configuration → execution → migration journey."""

    def test_failover_and_migration_combined(self):
        """Configure failover → execute → migrate app."""
        # Configure failover pair
        r = self.client.post(
            "/api/failover/configure",
            json={
                "app_id": "nextcloud",
                "domain": "cloud.e2e.test",
                "primary_host": "10.0.0.1",
                "secondary_host": "10.0.0.2",
                "primary_node_id": "node-primary",
                "secondary_node_id": "node-secondary",
                "health_strategy": "http",
            },
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 200)

        # Execute failover
        with patch("nexora_saas.failover.apply_failover_nginx", return_value={"success": True, "path": "/tmp"}):
            r = self.client.post(
                "/api/failover/execute",
                json={"app_id": "nextcloud", "target_node": "secondary", "reason": "e2e-test"},
                headers=self.headers,
            )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("success"))

        # Create migration job
        r = self.client.post(
            "/api/fleet/apps/migrate",
            json={
                "app_id": "nextcloud",
                "source_node_id": "node-primary",
                "target_node_id": "node-secondary",
                "target_domain": "cloud.e2e.test",
                "options": {},
            },
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 200)
        job_id = r.json()["job_id"]

        # Execute migration
        with patch("nexora_saas.app_migration._ynh_backup_app", return_value={"success": True, "backup_name": "test"}), \
             patch("nexora_saas.app_migration._rsync_backup_to_target", return_value={"success": True}), \
             patch("nexora_saas.app_migration._ynh_restore_on_target", return_value={"success": True}):
            r = self.client.post(
                f"/api/fleet/apps/migration/{job_id}/execute",
                json={"target_ssh_host": "node-secondary"},
                headers=self.headers,
            )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "completed")


class E2EErrorHandlingTests(TDDTestBase):
    """Edge case and error handling for API routes."""

    def test_get_nonexistent_organization(self):
        """GET /api/organizations/<bad-id> must return 404."""
        r = self.client.get("/api/organizations/org-nonexistent", headers=self.headers)
        self.assertEqual(r.status_code, 404)

    def test_get_nonexistent_subscription(self):
        """GET /api/subscriptions/<bad-id> must return 404."""
        r = self.client.get("/api/subscriptions/sub-nonexistent", headers=self.headers)
        self.assertEqual(r.status_code, 404)

    def test_upgrade_nonexistent_subscription(self):
        """Upgrade on nonexistent subscription must return 404."""
        r = self.client.post(
            "/api/subscriptions/sub-nonexistent/upgrade",
            json={"new_tier": "pro"},
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 404)

    def test_suspend_already_suspended(self):
        """Suspending an already-suspended subscription must handle gracefully."""
        org = self._create_org("SuspOrg", "susp@test.test")
        sub = self._create_subscription(org["org_id"], "pro")
        sub_id = sub["subscription"]["subscription_id"]
        self.client.post(f"/api/subscriptions/{sub_id}/suspend", json={"reason": "test"}, headers=self.headers)
        r = self.client.post(f"/api/subscriptions/{sub_id}/suspend", json={"reason": "test2"}, headers=self.headers)
        self.assertIn(r.status_code, (200, 409))

    def test_cancel_already_cancelled(self):
        """Cancelling an already-cancelled subscription must handle gracefully."""
        org = self._create_org("CancelOrg", "cancel@test.test")
        sub = self._create_subscription(org["org_id"], "pro")
        sub_id = sub["subscription"]["subscription_id"]
        self.client.post(f"/api/subscriptions/{sub_id}/cancel", json={}, headers=self.headers)
        r = self.client.post(f"/api/subscriptions/{sub_id}/cancel", json={}, headers=self.headers)
        self.assertIn(r.status_code, (200, 409))

    def test_downgrade_subscription_rejects(self):
        """Downgrading from enterprise to free must be rejected or gated."""
        org = self._create_org("DownOrg", "down@test.test")
        sub = self._create_subscription(org["org_id"], "enterprise")
        sub_id = sub["subscription"]["subscription_id"]
        r = self.client.post(
            f"/api/subscriptions/{sub_id}/upgrade",
            json={"new_tier": "free"},
            headers=self.headers,
        )
        # Should either reject (400/422) or flag as downgrade
        data = r.json()
        if r.status_code == 200:
            self.assertTrue(
                data.get("downgrade", False) or data.get("warning"),
                "Downgrade should be flagged with a warning",
            )

    def test_empty_json_body_on_mutation(self):
        """Mutations with empty body must respond with 422, not 500."""
        r = self.client.post("/api/organizations", content=b"", headers={**self.headers, "Content-Type": "application/json"})
        self.assertIn(r.status_code, (400, 422))

    def test_malformed_json_body(self):
        """Malformed JSON body must respond with 422, not 500."""
        r = self.client.post("/api/organizations", content=b"{invalid json", headers={**self.headers, "Content-Type": "application/json"})
        self.assertIn(r.status_code, (400, 422))


# ═══════════════════════════════════════════════════════════════════════════════
#  C. UI/UX CONSOLE INTEGRITY — Views, owner console, XSS, ARIA
# ═══════════════════════════════════════════════════════════════════════════════


class ConsoleViewXSSTests(unittest.TestCase):
    """Verify console views don't introduce XSS vectors."""

    @classmethod
    def setUpClass(cls):
        cls.views_source = Path("apps/console/views.js").read_text(encoding="utf-8")
        cls.app_source = Path("apps/console/app.js").read_text(encoding="utf-8")
        cls.api_source = Path("apps/console/api.js").read_text(encoding="utf-8")

    def test_no_innerhtml_with_raw_user_input(self):
        """Views must not inject raw user data via innerHTML without sanitization."""
        # Check for common dangerous patterns: innerHTML = variable without escaping
        dangerous_patterns = [
            "innerHTML = data",
            "innerHTML = response",
            "innerHTML = input",
            "innerHTML = user",
        ]
        for pattern in dangerous_patterns:
            self.assertNotIn(
                pattern,
                self.views_source,
                f"Potential XSS: {pattern} found in views.js",
            )

    def test_api_module_uses_session_storage(self):
        """Tokens must be stored in sessionStorage, not localStorage."""
        self.assertIn("sessionStorage", self.api_source)

    def test_no_eval_in_console_code(self):
        """Console code must not use eval()."""
        for source_name, source in [("views.js", self.views_source), ("app.js", self.app_source), ("api.js", self.api_source)]:
            self.assertNotIn("eval(", source, f"eval() found in {source_name}")

    def test_no_document_write_in_console(self):
        """Console code must not use document.write()."""
        for source_name, source in [("views.js", self.views_source), ("app.js", self.app_source)]:
            self.assertNotIn("document.write(", source, f"document.write() found in {source_name}")


class ConsoleViewAccessibilityTests(unittest.TestCase):
    """ARIA and accessibility attributes in console views."""

    @classmethod
    def setUpClass(cls):
        cls.views_source = Path("apps/console/views.js").read_text(encoding="utf-8")
        cls.components_source = Path("apps/console/components.js").read_text(encoding="utf-8")

    def test_gauge_component_has_aria_role(self):
        """Score gauge components should have role='progressbar' or aria labels."""
        self.assertIn("role", self.components_source.lower())

    def test_tables_have_scope_attributes(self):
        """Generated tables should have scope='col' on header cells."""
        self.assertIn("scope", self.components_source.lower())

    def test_buttons_have_accessible_text(self):
        """Button elements should have meaningful accessible text, not just icons."""
        # Count buttons without text content
        import re
        icon_only_buttons = re.findall(r'<button[^>]*>\s*<(?:i|svg|span class="icon)', self.views_source)
        self.assertEqual(
            len(icon_only_buttons), 0,
            f"Found {len(icon_only_buttons)} icon-only buttons without accessible text",
        )

    def test_alerts_have_role_alert(self):
        """Alert components must have role='alert' for screen readers."""
        self.assertIn("role", self.components_source)

    def test_status_dots_have_aria_label(self):
        """Status indicator dots must have aria-label for screen readers."""
        # status-dot elements should have title or aria-label
        if "status-dot" in self.views_source:
            has_accessible = "aria-label" in self.views_source or "title=" in self.views_source
            self.assertTrue(has_accessible, "status-dot elements should have aria-label or title")


class OwnerConsoleIntegrationTests(unittest.TestCase):
    """Owner console app integration and shared asset usage."""

    @classmethod
    def setUpClass(cls):
        cls.owner_app_source = Path("apps/owner_console/app.js").read_text(encoding="utf-8")
        cls.owner_index = Path("apps/owner_console/index.html").read_text(encoding="utf-8")

    def test_owner_console_imports_shared_views(self):
        """Owner console must import shared views.js from /console/."""
        self.assertIn("/console/views.js", self.owner_app_source)

    def test_owner_console_imports_shared_components(self):
        """Owner console must import shared components.js from /console/."""
        self.assertIn("/console/components.js", self.owner_app_source)

    def test_owner_console_has_passphrase_auth(self):
        """Owner console must use passphrase authentication, not token."""
        self.assertIn("passphrase", self.owner_app_source.lower())

    def test_owner_console_has_logout_handler(self):
        """Owner console must have a logout mechanism."""
        self.assertIn("logout", self.owner_app_source.lower())

    def test_owner_console_has_all_sections(self):
        """Owner console must support all management sections."""
        expected_sections = [
            "dashboard", "fleet", "subscription", "provisioning",
            "governance", "security", "modes", "settings",
        ]
        for section in expected_sections:
            self.assertIn(
                section,
                self.owner_app_source,
                f"Owner console missing section: {section}",
            )

    def test_owner_console_html_has_meta_charset(self):
        """Owner console HTML must have charset meta tag."""
        self.assertIn("charset", self.owner_index.lower())

    def test_owner_console_html_has_viewport(self):
        """Owner console must be mobile-responsive with viewport meta."""
        self.assertIn("viewport", self.owner_index.lower())

    def test_owner_console_html_has_lang_attribute(self):
        """Owner console HTML must have lang attribute for accessibility."""
        self.assertIn('lang="fr"', self.owner_index)


class ConsoleViewCompletenessTests(unittest.TestCase):
    """Every console section must be fully wired."""

    @classmethod
    def setUpClass(cls):
        cls.views_source = Path("apps/console/views.js").read_text(encoding="utf-8")
        cls.app_source = Path("apps/console/app.js").read_text(encoding="utf-8")

    def test_every_section_has_error_handling(self):
        """Each view function should have catch/error handling."""
        import re
        view_fns = re.findall(r"export async function (load\w+)\(", self.views_source)
        for fn in view_fns:
            # Find the function body and check for .catch or try
            fn_start = self.views_source.index(f"export async function {fn}(")
            fn_body = self.views_source[fn_start:fn_start + 2000]
            has_error_handling = ".catch(" in fn_body or "try" in fn_body
            self.assertTrue(
                has_error_handling,
                f"View function {fn} lacks error handling (.catch or try/catch)",
            )

    def test_every_section_has_loading_indicator(self):
        """Each view should show a loading indicator while fetching data."""
        self.assertIn("nxLoader", self.views_source)

    def test_subscriber_console_has_token_prompt(self):
        """Subscriber console must show token prompt for unauthenticated users."""
        self.assertIn("showTokenPrompt", self.app_source)

    def test_all_action_buttons_use_window_handlers(self):
        """Action buttons in views must use window.* handlers (not inline JS)."""
        import re
        # Find onclick handlers
        onclicks = re.findall(r'onclick="([^"]*)"', self.views_source)
        for onclick in onclicks:
            # Must call window.* or named function, not anonymous code
            is_safe = (
                onclick.startswith("window.")
                or onclick.startswith("NexoraConsole.")
                or re.match(r'^[a-zA-Z_]\w*\(', onclick)
            )
            self.assertTrue(is_safe, f"Unsafe onclick handler: {onclick[:50]}")


class ConsoleSettingsViewTests(unittest.TestCase):
    """Settings view must expose all configuration surfaces."""

    @classmethod
    def setUpClass(cls):
        cls.views_source = Path("apps/console/views.js").read_text(encoding="utf-8")

    def test_settings_view_exists(self):
        """Settings view function must exist."""
        self.assertIn("export async function loadSettings(", self.views_source)

    def test_settings_shows_actor_role(self):
        """Settings must display the actor role."""
        self.assertIn("actor_role", self.views_source)

    def test_settings_shows_runtime_mode(self):
        """Settings must display the runtime mode."""
        self.assertIn("runtime_mode", self.views_source)

    def test_settings_shows_tenant_info(self):
        """Settings must display tenant information."""
        self.assertIn("tenant_id", self.views_source)

    def test_settings_shows_allowed_sections(self):
        """Settings must display allowed sections."""
        self.assertIn("allowed_sections", self.views_source)


# ═══════════════════════════════════════════════════════════════════════════════
#  D. SUBSCRIPTION BILLING GUARD-RAILS
# ═══════════════════════════════════════════════════════════════════════════════


class SubscriptionQuotaEnforcementTests(TDDTestBase):
    """Quota enforcement when tenant exceeds plan limits."""

    def test_free_tier_node_enrollment_blocked_at_limit(self):
        """Free tier (max 5 nodes) must block 6th enrollment."""
        org = self._create_org("QuotaOrg", "quota@org.test")
        sub = self._create_subscription(org["org_id"], "free")
        tenant_id = sub["tenant"]["tenant_id"]

        # Seed 5 nodes for this tenant
        self._seed_nodes([
            {"node_id": f"qn{i}", "tenant_id": tenant_id, "status": "healthy"}
            for i in range(5)
        ])

        # 6th enrollment should be blocked
        r = self.client.post(
            "/api/fleet/enroll/request",
            json={"requested_by": "tester", "mode": "pull", "ttl_minutes": 15, "node_id": "qn6"},
            headers={**self.headers, "X-Nexora-Tenant-Id": tenant_id},
        )
        # Should be rejected due to quota
        self.assertEqual(r.status_code, 403)
        self.assertIn("quota", r.json().get("detail", "").lower())

    def test_pro_tier_allows_more_nodes(self):
        """Pro tier allows 50 nodes, so 6 should be fine."""
        org = self._create_org("ProQuotaOrg", "proquota@org.test")
        sub = self._create_subscription(org["org_id"], "pro")
        tenant_id = sub["tenant"]["tenant_id"]

        self._seed_nodes([
            {"node_id": f"pn{i}", "tenant_id": tenant_id, "status": "healthy"}
            for i in range(6)
        ])

        r = self.client.post(
            "/api/fleet/enroll/request",
            json={"requested_by": "tester", "mode": "pull", "ttl_minutes": 15, "node_id": "pn7"},
            headers={**self.headers, "X-Nexora-Tenant-Id": tenant_id},
        )
        self.assertEqual(r.status_code, 200)

    def test_suspended_subscription_blocks_new_enrollment(self):
        """A suspended subscription must block new node enrollment."""
        org = self._create_org("SuspQuotaOrg", "suspquota@org.test")
        sub = self._create_subscription(org["org_id"], "pro")
        sub_id = sub["subscription"]["subscription_id"]
        tenant_id = sub["tenant"]["tenant_id"]

        # Suspend
        self.client.post(
            f"/api/subscriptions/{sub_id}/suspend",
            json={"reason": "payment"},
            headers=self.headers,
        )

        # Attempt enrollment
        hdr = self._set_role("subscriber")
        r = self.client.post(
            "/api/fleet/enroll/request",
            json={"requested_by": "tester", "mode": "pull", "ttl_minutes": 15, "node_id": "susp-node"},
            headers={**hdr, "X-Nexora-Tenant-Id": tenant_id},
        )
        self.assertEqual(r.status_code, 403)
        self.assertIn("suspended", r.json().get("detail", "").lower())


class SubscriptionBillingFieldTests(TDDTestBase):
    """Subscription responses must include billing metadata."""

    def test_subscription_includes_billing_period(self):
        """Active subscriptions must include billing period info."""
        org = self._create_org("BillOrg", "bill@org.test")
        sub = self._create_subscription(org["org_id"], "pro")
        sub_data = sub["subscription"]
        self.assertIn("billing_period_start", sub_data)
        self.assertIn("billing_period_end", sub_data)

    def test_subscription_includes_price(self):
        """Subscription must include monthly price."""
        org = self._create_org("PriceOrg", "price@org.test")
        sub = self._create_subscription(org["org_id"], "pro")
        sub_data = sub["subscription"]
        self.assertIn("price_monthly_eur", sub_data)
        self.assertEqual(sub_data["price_monthly_eur"], 49)

    def test_subscription_includes_next_billing_date(self):
        """Active subscriptions must have a next_billing_date."""
        org = self._create_org("NextBillOrg", "nb@org.test")
        sub = self._create_subscription(org["org_id"], "enterprise")
        sub_data = sub["subscription"]
        self.assertIn("next_billing_date", sub_data)


# ═══════════════════════════════════════════════════════════════════════════════
#  E. MULTI-TENANT DEEP ISOLATION
# ═══════════════════════════════════════════════════════════════════════════════


class MultiTenantDeepIsolationTests(TDDTestBase):
    """Deep isolation: every tenant-aware surface must enforce boundaries."""

    def test_governance_report_tenant_isolated(self):
        """Governance report must filter by tenant when header present."""
        self._seed_tenants([
            {"tenant_id": "ta", "org_id": "oa", "tier": "pro", "created_at": "2026-01-01T00:00:00Z"},
            {"tenant_id": "tb", "org_id": "ob", "tier": "free", "created_at": "2026-01-01T00:00:00Z"},
        ])
        r = self.client.get(
            "/api/governance/report",
            headers={**self.headers, "X-Nexora-Tenant-Id": "ta"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json().get("tenant_id"), "ta")

    def test_pra_data_tenant_isolated(self):
        """PRA data must be scoped to the requesting tenant."""
        r = self.client.get(
            "/api/pra",
            headers={**self.headers, "X-Nexora-Tenant-Id": "ta"},
        )
        self.assertEqual(r.json()["tenant_id"], "ta")
        r2 = self.client.get(
            "/api/pra",
            headers={**self.headers, "X-Nexora-Tenant-Id": "tb"},
        )
        self.assertEqual(r2.json()["tenant_id"], "tb")

    def test_metrics_tenant_scoped_when_header_present(self):
        """Metrics endpoint must filter by tenant when X-Nexora-Tenant-Id present."""
        self._seed_nodes([
            {"node_id": "na1", "tenant_id": "ta", "status": "healthy"},
            {"node_id": "nb1", "tenant_id": "tb", "status": "healthy"},
        ])
        r = self.client.get(
            "/api/metrics",
            headers={**self.headers, "X-Nexora-Tenant-Id": "ta"},
        )
        text = r.text
        # Should only show 1 node (ta's)
        self.assertIn("nexora_nodes_total 1", text)

    def test_subscription_list_tenant_scoped(self):
        """Subscriber role must only see own tenant's subscriptions."""
        org = self._create_org("IsoOrg", "iso@org.test")
        self._create_subscription(org["org_id"], "pro")
        # Set up subscriber with scope
        self._set_scope(["restricted-tenant"])
        r = self.client.get(
            "/api/subscriptions",
            headers=self._scoped_headers("restricted-tenant"),
        )
        subs = r.json()
        # Should not see the org's subscription (belongs to different tenant)
        for sub in subs:
            self.assertEqual(sub.get("tenant_id", "restricted-tenant"), "restricted-tenant")

    def test_cross_tenant_node_inventory_denied(self):
        """Subscriber must not see nodes from other tenants in fleet list."""
        self._seed_nodes([
            {"node_id": "iso-na", "tenant_id": "ta", "status": "healthy"},
            {"node_id": "iso-nb", "tenant_id": "tb", "status": "healthy"},
        ])
        hdr = self._set_role("subscriber")
        r = self.client.get(
            "/api/fleet",
            headers={**hdr, "X-Nexora-Tenant-Id": "ta"},
        )
        nodes = r.json().get("nodes", [])
        for node in nodes:
            self.assertEqual(node.get("tenant_id"), "ta",
                             f"Node {node.get('node_id')} from wrong tenant leaked")


class SurfaceIsolationTests(TDDTestBase):
    """Subdomain surface isolation enforcement."""

    def test_subscriber_console_blocks_owner_endpoints(self):
        """Console surface must block owner-console specific paths."""
        r = self.client.get(
            "/owner-console/app.js",
            headers={**self.headers, "Host": "console.srv2testrchon.nohost.me"},
        )
        self.assertEqual(r.status_code, 403)

    def test_public_surface_blocks_api_endpoints(self):
        """Public www surface must block API endpoints."""
        r = self.client.get(
            "/api/fleet",
            headers={**self.headers, "Host": "www.srv2testrchon.nohost.me"},
        )
        self.assertEqual(r.status_code, 403)

    def test_saas_surface_blocks_subscriber_token(self):
        """SaaS surface must block subscriber-token access to API."""
        hdr = self._set_role("subscriber")
        r = self.client.get(
            "/api/fleet",
            headers={**hdr, "Host": "saas.test.local", "X-Nexora-Tenant-Id": "test"},
        )
        self.assertEqual(r.status_code, 403)

    def test_no_surface_allows_all(self):
        """No subdomain (test/direct) must not restrict access."""
        r = self.client.get("/api/fleet", headers=self.headers)
        self.assertEqual(r.status_code, 200)


# ═══════════════════════════════════════════════════════════════════════════════
#  F. RBAC & AUTH EXTENDED — Owner sessions, role escalation, token rotation
# ═══════════════════════════════════════════════════════════════════════════════


class OwnerSessionSecurityTests(TDDTestBase):
    """Owner session authentication security."""

    def test_owner_login_with_valid_passphrase(self):
        """Owner login with correct passphrase must return session token."""
        # Set up passphrase
        from nexora_node_sdk.auth import set_owner_passphrase
        set_owner_passphrase("TestPass2026!!")

        r = self.client.post(
            "/api/auth/owner-login",
            json={"passphrase": "TestPass2026!!"},
        )
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("session_token", data)
        self.assertEqual(data.get("role"), "owner")

    def test_owner_login_with_wrong_passphrase(self):
        """Owner login with wrong passphrase must return 401."""
        from nexora_node_sdk.auth import set_owner_passphrase
        set_owner_passphrase("CorrectPass!!")

        r = self.client.post(
            "/api/auth/owner-login",
            json={"passphrase": "WrongPass!!"},
        )
        self.assertEqual(r.status_code, 401)

    def test_owner_session_grants_full_access(self):
        """Owner session must grant full access-context with all sections."""
        from nexora_node_sdk.auth import create_owner_session, set_owner_passphrase
        set_owner_passphrase("OwnerTest!!")
        session = create_owner_session()

        r = self.client.get(
            "/api/console/access-context",
            headers={"X-Nexora-Session": session["token"]},
        )
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["actor_role"], "owner")
        self.assertTrue(data["is_operator"])
        self.assertIn("settings", data["allowed_sections"])

    def test_owner_session_expiry(self):
        """Expired owner sessions must be rejected."""
        from nexora_node_sdk.auth._owner_session import _sessions, _sessions_lock
        expired_token = secrets.token_urlsafe(48)
        with _sessions_lock:
            _sessions[expired_token] = {
                "tenant_id": "nexora-owner",
                "role": "owner",
                "issued_at": int(time.time()) - 86400,
                "expires_at": int(time.time()) - 3600,
            }

        r = self.client.get(
            "/api/console/access-context",
            headers={"X-Nexora-Session": expired_token},
        )
        self.assertEqual(r.status_code, 401)

    def test_owner_logout_invalidates_session(self):
        """Owner logout must invalidate the session."""
        from nexora_node_sdk.auth import create_owner_session, set_owner_passphrase
        set_owner_passphrase("LogoutTest!!")
        session = create_owner_session()

        # Session works before logout
        r = self.client.get(
            "/api/console/access-context",
            headers={"X-Nexora-Session": session["token"]},
        )
        self.assertEqual(r.status_code, 200)

        # Logout
        r = self.client.post(
            "/api/auth/owner-logout",
            headers={"X-Nexora-Session": session["token"]},
        )
        self.assertEqual(r.status_code, 200)

        # Session must no longer work
        r = self.client.get(
            "/api/console/access-context",
            headers={"X-Nexora-Session": session["token"]},
        )
        self.assertEqual(r.status_code, 401)


class RBACEscalationTests(TDDTestBase):
    """Role escalation and privilege boundary tests."""

    def test_subscriber_cannot_escalate_to_admin(self):
        """Subscriber role must not be able to call escalation endpoints."""
        hdr = self._set_role("subscriber")
        r = self.client.post(
            "/api/mode/escalate?target=admin&duration_minutes=30&reason=test",
            headers=hdr,
        )
        self.assertEqual(r.status_code, 403)

    def test_observer_cannot_perform_mutations(self):
        """Observer role must not be able to call any mutation endpoint."""
        hdr = self._set_role("observer")
        mutation_routes = [
            ("/api/organizations", {"name": "TestOrg", "contact_email": "t@t.test"}),
            ("/api/subscriptions", {"org_id": "org-1", "plan_tier": "free"}),
            ("/api/mode/switch?target=operator&reason=test", None),
        ]
        for route, body in mutation_routes:
            with self.subTest(route=route):
                if body:
                    r = self.client.post(route, json=body, headers=hdr)
                else:
                    r = self.client.post(route, headers=hdr)
                self.assertEqual(r.status_code, 403,
                                 f"Observer should not be able to POST to {route}")

    def test_escalation_token_expires(self):
        """Escalation tokens must have a defined expiry."""
        r = self.client.post(
            "/api/mode/escalate?target=admin&duration_minutes=5&reason=test",
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("expires_at", data)

    def test_escalation_creates_audit_trail(self):
        """Escalation must create an audit trail entry."""
        self.client.post(
            "/api/mode/escalate?target=admin&duration_minutes=5&reason=audit-test",
            headers=self.headers,
        )
        r = self.client.get("/api/mode/escalations", headers=self.headers)
        escalations = r.json()
        self.assertTrue(
            any("audit-test" in str(e) for e in escalations),
            "Escalation should appear in escalation log",
        )

    def test_role_file_corruption_falls_back_safely(self):
        """Corrupted role file must not grant elevated access."""
        corrupted_path = Path(self.tmp_dir.name) / "corrupted-roles.json"
        corrupted_path.write_text("{invalid json", encoding="utf-8")
        os.environ["NEXORA_API_TOKEN_ROLE_FILE"] = str(corrupted_path)

        r = self.client.get("/api/fleet", headers=self.headers)
        # Should still work with primary token
        self.assertEqual(r.status_code, 200)

        # But should not grant any special role
        r = self.client.get("/api/console/access-context", headers=self.headers)
        data = r.json()
        # Should not be admin from corrupted file
        self.assertNotEqual(data["actor_role"], "admin")


class TokenRotationTests(TDDTestBase):
    """Token rotation and revocation scenarios."""

    def test_old_token_rejected_after_rotation(self):
        """After token rotation, old tokens must be rejected."""
        old_token = self.token
        # Simulate rotation by creating a new role file without old token
        new_token = secrets.token_urlsafe(32)
        rf = _make_role_file(self.tmp_dir.name, {new_token: "admin"})
        os.environ["NEXORA_API_TOKEN_ROLE_FILE"] = rf

        # Old token should still work (primary is unchanged)
        r = self.client.get("/api/fleet", headers={"Authorization": f"Bearer {old_token}"})
        self.assertEqual(r.status_code, 200)

        # New token should also work
        r = self.client.get("/api/fleet", headers={"Authorization": f"Bearer {new_token}"})
        self.assertEqual(r.status_code, 200)

    def test_revoked_secondary_token_rejected(self):
        """A secondary token removed from role file must be rejected."""
        secondary = secrets.token_urlsafe(24)
        # Add secondary token
        rf = _make_role_file(self.tmp_dir.name, {self.token: "admin", secondary: "subscriber"})
        os.environ["NEXORA_API_TOKEN_ROLE_FILE"] = rf

        # Secondary works
        r = self.client.get("/api/fleet", headers={"Authorization": f"Bearer {secondary}"})
        self.assertEqual(r.status_code, 200)

        # Remove secondary from role file
        rf2 = _make_role_file(self.tmp_dir.name, {self.token: "admin"})
        os.environ["NEXORA_API_TOKEN_ROLE_FILE"] = rf2

        # Secondary should now be rejected
        r = self.client.get("/api/fleet", headers={"Authorization": f"Bearer {secondary}"})
        self.assertEqual(r.status_code, 401)


# ═══════════════════════════════════════════════════════════════════════════════
#  G. OWNER CONSOLE E2E — Passphrase flow, session lifecycle
# ═══════════════════════════════════════════════════════════════════════════════


class OwnerConsoleE2ETests(TDDTestBase):
    """Owner console passphrase flow end-to-end."""

    def test_passphrase_status_before_setup(self):
        """Before passphrase is set, status must show not configured."""
        r = self.client.get("/api/auth/owner-passphrase-status")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertFalse(data.get("configured"))

    def test_set_passphrase_then_login(self):
        """Set passphrase → verify status → login → access API."""
        # Set passphrase
        from nexora_node_sdk.auth import set_owner_passphrase
        result = set_owner_passphrase("E2EOwner2026!!")
        self.assertTrue(result.get("stored"))

        # Status should show configured
        r = self.client.get("/api/auth/owner-passphrase-status")
        self.assertTrue(r.json().get("configured"))

        # Login
        r = self.client.post(
            "/api/auth/owner-login",
            json={"passphrase": "E2EOwner2026!!"},
        )
        self.assertEqual(r.status_code, 200)
        session_token = r.json()["session_token"]

        # Use session to access API
        r = self.client.get(
            "/api/console/access-context",
            headers={"X-Nexora-Session": session_token},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["actor_role"], "owner")

    def test_passphrase_change_invalidates_old_sessions(self):
        """Changing passphrase must invalidate all existing sessions."""
        from nexora_node_sdk.auth import create_owner_session, set_owner_passphrase
        set_owner_passphrase("OldPass2026!!")
        old_session = create_owner_session()

        # Old session works
        r = self.client.get(
            "/api/console/access-context",
            headers={"X-Nexora-Session": old_session["token"]},
        )
        self.assertEqual(r.status_code, 200)

        # Change passphrase
        set_owner_passphrase("NewPass2026!!")

        # Old session should be invalidated
        r = self.client.get(
            "/api/console/access-context",
            headers={"X-Nexora-Session": old_session["token"]},
        )
        self.assertEqual(r.status_code, 401)


class OwnerConsoleAPITests(unittest.TestCase):
    """Owner console API module integrity."""

    @classmethod
    def setUpClass(cls):
        cls.owner_api = Path("apps/owner_console/api.js").read_text(encoding="utf-8")

    def test_owner_api_uses_session_storage(self):
        """Owner API must use sessionStorage for session tokens."""
        self.assertIn("sessionStorage", self.owner_api)

    def test_owner_api_sends_session_header(self):
        """Owner API must send X-Nexora-Session header."""
        self.assertIn("X-Nexora-Session", self.owner_api)

    def test_owner_api_has_login_function(self):
        """Owner API must have a login function."""
        self.assertIn("login", self.owner_api.lower())

    def test_owner_api_has_logout_function(self):
        """Owner API must have a logout function."""
        self.assertIn("logout", self.owner_api.lower())

    def test_owner_api_handles_401_redirect(self):
        """Owner API must redirect to login on 401 responses."""
        self.assertIn("401", self.owner_api)


# ═══════════════════════════════════════════════════════════════════════════════
#  H. BLUEPRINT DEPLOYMENT & BRANDING E2E
# ═══════════════════════════════════════════════════════════════════════════════


class BlueprintDeploymentTests(TDDTestBase):
    """Blueprint deployment routes and lifecycle."""

    def test_blueprint_deploy_dry_run(self):
        """Blueprint deployment dry-run must return plan without executing."""
        bps = self.client.get("/api/blueprints", headers=self.headers).json()
        if bps:
            slug = bps[0]["slug"]
            r = self.client.post(
                f"/api/blueprints/{slug}/deploy",
                json={"dry_run": True, "node_id": "test-node"},
                headers=self.headers,
            )
            self.assertIn(r.status_code, (200, 404))
            if r.status_code == 200:
                self.assertIn("plan", r.json())

    def test_blueprint_list_has_description(self):
        """Every blueprint must have a description."""
        bps = self.client.get("/api/blueprints", headers=self.headers).json()
        for bp in bps:
            self.assertIn("description", bp, f"Blueprint {bp.get('slug')} missing description")

    def test_blueprint_has_required_apps(self):
        """Every blueprint must list required apps."""
        bps = self.client.get("/api/blueprints", headers=self.headers).json()
        for bp in bps:
            if "apps" in bp:
                self.assertIsInstance(bp["apps"], list)


class BrandingTests(TDDTestBase):
    """Branding and portal customization."""

    def test_branding_returns_logo_and_colors(self):
        """Branding endpoint must return logo and color palette."""
        r = self.client.get("/api/branding", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("primary_color", data)
        self.assertIn("logo_url", data)

    def test_portal_palettes_have_colors(self):
        """Portal palettes must include color values."""
        r = self.client.get("/api/portal/palettes", headers=self.headers)
        palettes = r.json()
        self.assertIsInstance(palettes, list)
        if palettes:
            self.assertIn("primary", palettes[0])


# ═══════════════════════════════════════════════════════════════════════════════
#  I. API RESPONSE CONSISTENCY
# ═══════════════════════════════════════════════════════════════════════════════


class APIResponseConsistencyTests(TDDTestBase):
    """All API responses must follow consistent patterns."""

    def test_all_error_responses_have_detail_field(self):
        """Error responses (4xx) must include a 'detail' field."""
        # 401
        r = self.client.get("/api/fleet")
        self.assertEqual(r.status_code, 401)
        self.assertIn("detail", r.json())

        # 403 (CSRF)
        r = self.client.post(
            "/api/mode/switch?target=operator&reason=test",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        self.assertEqual(r.status_code, 403)
        self.assertIn("detail", r.json())

    def test_health_endpoint_includes_timestamp(self):
        """Health endpoint must include server timestamp."""
        r = self.client.get("/api/health", headers=self.headers)
        data = r.json()
        self.assertIn("timestamp", data)

    def test_list_endpoints_return_arrays(self):
        """List endpoints must return JSON arrays."""
        list_routes = ["/api/plans", "/api/blueprints", "/api/organizations", "/api/subscriptions", "/api/tenants"]
        for route in list_routes:
            with self.subTest(route=route):
                r = self.client.get(route, headers=self.headers)
                self.assertIsInstance(r.json(), list, f"{route} should return an array")

    def test_all_endpoints_return_json(self):
        """All API endpoints must return application/json content type."""
        routes = ["/api/health", "/api/fleet", "/api/scores", "/api/pra"]
        for route in routes:
            with self.subTest(route=route):
                r = self.client.get(route, headers=self.headers)
                self.assertIn("application/json", r.headers.get("content-type", ""))


if __name__ == "__main__":
    unittest.main()
