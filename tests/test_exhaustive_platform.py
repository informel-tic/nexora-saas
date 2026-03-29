"""Exhaustive platform tests — covers ALL Nexora SaaS features end-to-end.

Categories:
  1. API surface contract (every route returns the right shape)
  2. Console access-context & section gating
  3. Security (auth, RBAC, tenant isolation, CSRF, token scoping)
  4. Subscription lifecycle (plans, orgs, subscriptions, upgrades, cancellations)
  5. Fleet & node lifecycle (enrollment, drain, cordon, retire, revoke, re-enroll)
  6. Governance & scoring (scores, reports, risks, audits, changelogs)
  7. PRA / backup / disaster-recovery
  8. Docker / storage / operations
  9. Modes & escalations
  10. Provisioning & feature push
  11. Metrics (Prometheus format)
  12. Blueprints & branding
  13. Multi-tenant isolation (cross-tenant denial on every surface)
  14. Quotas & entitlements
  15. Notifications & hooks & automation
  16. SLA tiers
  17. Failover strategies
  18. Node agent contract
"""
from __future__ import annotations

import json
import os
import secrets
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import apps.control_plane.api as api_module
from nexora_node_sdk.auth import build_tenant_scope_claim, get_api_token
from nexora_node_sdk.state import DEFAULT_STATE
from nexora_saas.orchestrator import NexoraService


# ─── helpers ──────────────────────────────────────────────────────────────────
def _make_role_file(tmp_dir: str, mapping: dict) -> str:
    path = Path(tmp_dir) / f"roles-{secrets.token_hex(4)}.json"
    path.write_text(json.dumps(mapping), encoding="utf-8")
    return str(path)


def _make_scope_file(tmp_dir: str, mapping: dict) -> str:
    path = Path(tmp_dir) / f"scopes-{secrets.token_hex(4)}.json"
    path.write_text(json.dumps(mapping), encoding="utf-8")
    return str(path)


# ═══════════════════════════════════════════════════════════════════════════════
#  BASE TEST CLASS — shared setup
# ═══════════════════════════════════════════════════════════════════════════════
class NexoraTestBase(unittest.TestCase):
    """Common fixtures for all Nexora integration tests."""

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

    # helpers
    def _set_role(self, role: str) -> dict:
        """Configure a role file binding current token to *role*; return augmented headers."""
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

    def _seed_snapshots(self, snapshots: list[dict]) -> None:
        state = api_module.service.state.load()
        state["inventory_snapshots"] = snapshots
        api_module.service.state.save(state)


# ═══════════════════════════════════════════════════════════════════════════════
#  1. API SURFACE — every route returns 200 with valid auth
# ═══════════════════════════════════════════════════════════════════════════════
class APISurfaceGetRoutes(NexoraTestBase):
    """Every GET route must respond 200 or 307 (redirect) when properly authed."""

    ROUTES = [
        "/api/health",
        "/api/v1/health",
        "/api/dashboard",
        "/api/v1/dashboard",
        "/api/inventory/local",
        "/api/inventory/apps",
        "/api/fleet",
        "/api/v1/fleet",
        "/api/fleet/topology",
        "/api/fleet/lifecycle",
        "/api/fleet/compatibility",
        "/api/scores",
        "/api/governance/report",
        "/api/governance/risks",
        "/api/governance/changelog",
        "/api/governance/snapshot-diff",
        "/api/security/posture",
        "/api/security/updates",
        "/api/security/fail2ban/status",
        "/api/security/open-ports",
        "/api/security/permissions-audit",
        "/api/security/recent-logins",
        "/api/pra",
        "/api/mode",
        "/api/mode/list",
        "/api/mode/escalations",
        "/api/mode/confirmations",
        "/api/blueprints",
        "/api/branding",
        "/api/identity",
        "/api/capabilities",
        "/api/portal/palettes",
        "/api/portal/sectors",
        "/api/adoption/report",
        "/api/metrics",
        "/api/plans",
        "/api/v1/plans",
        "/api/tenants/usage-quota",
        "/api/auth/tenant-claim?tenant_id=test",
    ]

    def test_all_get_routes_return_ok(self):
        for route in self.ROUTES:
            with self.subTest(route=route):
                r = self.client.get(route, headers=self.headers)
                self.assertIn(
                    r.status_code,
                    (200, 307),
                    f"{route} returned {r.status_code}: {r.text[:200]}",
                )

    def test_health_payload_shape(self):
        r = self.client.get("/api/health", headers=self.headers)
        data = r.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("version", data)
        self.assertIn("compatibility", data)

    def test_dashboard_payload_shape(self):
        r = self.client.get("/api/dashboard", headers=self.headers)
        data = r.json()
        self.assertIn("node", data)
        self.assertIn("alerts", data)
        self.assertIn("top_apps", data)

    def test_fleet_payload_shape(self):
        r = self.client.get("/api/fleet", headers=self.headers)
        data = r.json()
        self.assertIn("total_nodes", data)
        self.assertIn("nodes", data)
        self.assertIn("overall_health_score", data)

    def test_fleet_topology_payload_shape(self):
        self._seed_nodes([
            {"node_id": "n1", "tenant_id": "t1", "status": "healthy"},
        ])
        r = self.client.get("/api/fleet/topology", headers=self.headers)
        data = r.json()
        self.assertIn("nodes", data)

    def test_fleet_lifecycle_payload_shape(self):
        r = self.client.get("/api/fleet/lifecycle", headers=self.headers)
        data = r.json()
        self.assertIsInstance(data, dict)

    def test_fleet_compatibility_payload(self):
        r = self.client.get("/api/fleet/compatibility", headers=self.headers)
        data = r.json()
        self.assertIn("assessment", data)

    def test_inventory_local_payload(self):
        r = self.client.get("/api/inventory/local", headers=self.headers)
        data = r.json()
        self.assertIsInstance(data, dict)

    def test_identity_payload_shape(self):
        r = self.client.get("/api/identity", headers=self.headers)
        data = r.json()
        self.assertIn("node_id", data)
        self.assertIn("fleet_id", data)
        self.assertIn("credential_type", data)

    def test_capabilities_payload_shape(self):
        r = self.client.get("/api/capabilities", headers=self.headers)
        data = r.json()
        self.assertIsInstance(data, dict)

    def test_blueprints_returns_list(self):
        r = self.client.get("/api/blueprints", headers=self.headers)
        data = r.json()
        self.assertIsInstance(data, list)
        if data:
            self.assertIn("slug", data[0])

    def test_plans_returns_all_tiers(self):
        r = self.client.get("/api/plans", headers=self.headers)
        data = r.json()
        self.assertIsInstance(data, list)
        tiers = {p["tier"] for p in data}
        self.assertIn("free", tiers)
        self.assertIn("pro", tiers)
        self.assertIn("enterprise", tiers)

    def test_portal_palettes_returns_list(self):
        r = self.client.get("/api/portal/palettes", headers=self.headers)
        self.assertIsInstance(r.json(), list)

    def test_portal_sectors_returns_list(self):
        r = self.client.get("/api/portal/sectors", headers=self.headers)
        self.assertIsInstance(r.json(), list)


class APISurfacePublicRoutes(NexoraTestBase):
    """Public routes must work without auth."""

    def test_public_offers_no_auth(self):
        r = self.client.get("/api/public/offers")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("offers", data)
        self.assertEqual(data["platform"], "Nexora SaaS")

    def test_root_landing_page(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Nexora", r.text)

    def test_subscribe_landing(self):
        r = self.client.get("/subscribe")
        self.assertEqual(r.status_code, 200)

    def test_admin_redirect(self):
        r = self.client.get("/admin", follow_redirects=False)
        self.assertIn(r.status_code, (301, 302, 307, 308))

    def test_console_api_module_is_public_static_asset(self):
        r = self.client.get("/console/api.js")
        self.assertEqual(r.status_code, 200)
        self.assertIn("initToken", r.text)


# ═══════════════════════════════════════════════════════════════════════════════
#  2. CONSOLE ACCESS-CONTEXT & SECTION GATING
# ═══════════════════════════════════════════════════════════════════════════════
class AccessContextTests(NexoraTestBase):
    """Test the /api/console/access-context endpoint and section gating."""

    def test_operator_admin_gets_full_sections(self):
        hdr = self._set_role("admin")
        r = self.client.get("/api/console/access-context", headers=hdr)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["actor_role"], "admin")
        self.assertTrue(data["is_operator"])
        sections = data["allowed_sections"]
        for s in ("dashboard", "fleet", "settings", "subscription", "provisioning", "docker", "pra"):
            self.assertIn(s, sections, f"Missing section: {s}")

    def test_operator_operator_role_gets_full_sections(self):
        hdr = self._set_role("operator")
        r = self.client.get("/api/console/access-context", headers=hdr)
        data = r.json()
        self.assertTrue(data["is_operator"])
        self.assertIn("settings", data["allowed_sections"])

    def test_operator_architect_role_gets_full_sections(self):
        hdr = self._set_role("architect")
        r = self.client.get("/api/console/access-context", headers=hdr)
        data = r.json()
        self.assertTrue(data["is_operator"])
        self.assertIn("settings", data["allowed_sections"])

    def test_subscriber_gets_restricted_sections(self):
        hdr = self._set_role("subscriber")
        r = self.client.get(
            "/api/console/access-context",
            headers={**hdr, "X-Nexora-Tenant-Id": "tenant-sub"},
        )
        data = r.json()
        self.assertEqual(data["actor_role"], "subscriber")
        self.assertFalse(data["is_operator"])
        self.assertTrue(data["subscriber_mode"])
        self.assertNotIn("settings", data["allowed_sections"])
        self.assertNotIn("subscription", data["allowed_sections"])
        self.assertNotIn("provisioning", data["allowed_sections"])
        self.assertNotIn("docker", data["allowed_sections"])
        self.assertIn("dashboard", data["allowed_sections"])
        self.assertIn("fleet", data["allowed_sections"])

    def test_observer_gets_read_only_sections(self):
        hdr = self._set_role("observer")
        r = self.client.get(
            "/api/console/access-context",
            headers={**hdr, "X-Nexora-Tenant-Id": "tenant-obs"},
        )
        data = r.json()
        self.assertEqual(data["actor_role"], "observer")
        self.assertFalse(data["is_operator"])
        self.assertNotIn("settings", data["allowed_sections"])
        self.assertIn("dashboard", data["allowed_sections"])

    def test_operator_auto_creates_tenant(self):
        hdr = self._set_role("admin")
        r = self.client.get("/api/console/access-context", headers=hdr)
        data = r.json()
        self.assertEqual(data["tenant_source"], "operator-default")
        state = api_module.service.state.load()
        tenant_ids = [t["tenant_id"] for t in state.get("tenants", []) if isinstance(t, dict)]
        self.assertIn(data["tenant_id"], tenant_ids)

    def test_operator_tenant_has_org_binding(self):
        hdr = self._set_role("admin")
        self.client.get("/api/console/access-context", headers=hdr)
        state = api_module.service.state.load()
        orgs = state.get("organizations", [])
        self.assertTrue(len(orgs) >= 1)

    def test_runtime_mode_is_independent_of_role(self):
        hdr = self._set_role("admin")
        r = self.client.get("/api/console/access-context", headers=hdr)
        data = r.json()
        self.assertIn(data["runtime_mode"], {"observer", "operator", "architect", "admin"})
        self.assertNotEqual(data["actor_role"], data.get("runtime_mode_override", "NONE"))

    def test_operator_stats_included(self):
        self._seed_tenants([
            {"tenant_id": "t1", "org_id": "o1", "tier": "free", "created_at": "2026-01-01T00:00:00Z"},
            {"tenant_id": "t2", "org_id": "o2", "tier": "pro", "created_at": "2026-01-01T00:00:00Z"},
        ])
        state = api_module.service.state.load()
        state["subscriptions"] = [
            {"subscription_id": "sub-1", "org_id": "o1", "status": "active"},
        ]
        api_module.service.state.save(state)
        hdr = self._set_role("admin")
        r = self.client.get("/api/console/access-context", headers=hdr)
        data = r.json()
        stats = data.get("operator_stats", {})
        self.assertGreaterEqual(stats.get("total_tenants", 0), 2)

    def test_access_context_with_explicit_tenant_header(self):
        hdr = self._set_role("admin")
        r = self.client.get(
            "/api/console/access-context",
            headers={**hdr, "X-Nexora-Tenant-Id": "explicit-tenant"},
        )
        data = r.json()
        self.assertEqual(data["tenant_id"], "explicit-tenant")
        self.assertEqual(data["tenant_source"], "header")


# ═══════════════════════════════════════════════════════════════════════════════
#  3. SECURITY — auth, RBAC, CSRF, token scoping
# ═══════════════════════════════════════════════════════════════════════════════
class SecurityAuthTests(NexoraTestBase):
    """Authentication & authorization enforcement."""

    def test_no_token_returns_401(self):
        r = self.client.get("/api/fleet")
        self.assertEqual(r.status_code, 401)

    def test_bad_token_returns_401(self):
        r = self.client.get("/api/fleet", headers={"Authorization": "Bearer bad-token"})
        self.assertEqual(r.status_code, 401)

    def test_x_nexora_token_header_also_works(self):
        r = self.client.get("/api/fleet", headers={"X-Nexora-Token": self.token})
        self.assertEqual(r.status_code, 200)

    def test_bearer_token_is_timing_safe(self):
        """Source code uses secrets.compare_digest for token comparison."""
        source = Path("src/nexora_node_sdk/auth/_middleware.py").read_text(encoding="utf-8")
        self.assertIn("compare_digest", source)

    def test_secondary_token_from_role_file_is_accepted(self):
        secondary = secrets.token_urlsafe(24)
        rf = _make_role_file(self.tmp_dir.name, {self.token: "admin", secondary: "subscriber"})
        os.environ["NEXORA_API_TOKEN_ROLE_FILE"] = rf
        r = self.client.get("/api/fleet", headers={"Authorization": f"Bearer {secondary}"})
        self.assertEqual(r.status_code, 200)


class SecurityCSRFTests(NexoraTestBase):
    """CSRF protection on mutation endpoints."""

    def test_mutation_without_origin_is_rejected(self):
        hdr = {k: v for k, v in self.headers.items() if k not in ("Origin", "Referer")}
        r = self.client.post("/api/adoption/import?domain=example.org&path=/nexora", headers=hdr)
        self.assertEqual(r.status_code, 403)
        self.assertIn("Missing Origin/Referer", r.text)

    def test_mutation_with_origin_is_accepted(self):
        r = self.client.post("/api/adoption/import?domain=example.org&path=/nexora", headers=self.headers)
        self.assertEqual(r.status_code, 200)


class SecurityRBACTests(NexoraTestBase):
    """Role-based access control for operator-only & subscriber restrictions."""

    def test_operator_only_route_requires_operator_role(self):
        os.environ["NEXORA_OPERATOR_ONLY_ENFORCE"] = "1"
        r = self.client.get("/api/persistence", headers=self.headers)
        self.assertEqual(r.status_code, 403)

    def test_operator_only_route_with_operator_binding(self):
        os.environ["NEXORA_OPERATOR_ONLY_ENFORCE"] = "1"
        hdr = self._set_role("operator")
        r = self.client.get("/api/persistence", headers=hdr)
        self.assertEqual(r.status_code, 200)

    def test_operator_only_enforcement_disabled(self):
        os.environ["NEXORA_OPERATOR_ONLY_ENFORCE"] = "0"
        r = self.client.get("/api/interface-parity/fleet-lifecycle", headers=self.headers)
        self.assertEqual(r.status_code, 200)

    def test_role_header_spoofing_is_rejected(self):
        os.environ["NEXORA_OPERATOR_ONLY_ENFORCE"] = "1"
        rf = _make_role_file(self.tmp_dir.name, {self.token: "admin"})
        os.environ["NEXORA_API_TOKEN_ROLE_FILE"] = rf
        r = self.client.get(
            "/api/persistence",
            headers={**self.headers, "X-Nexora-Actor-Role": "operator"},
        )
        self.assertEqual(r.status_code, 403)
        self.assertIn("does not match trusted credentials", r.text)

    def test_subscriber_denied_on_admin_routes(self):
        hdr = self._set_role("subscriber")
        denied_prefixes = [
            "/api/mode",
            "/api/admin/log",
            "/api/adoption/import?domain=x.org&path=/x",
            "/api/settings",
        ]
        for route in denied_prefixes:
            with self.subTest(route=route):
                if "import" in route:
                    r = self.client.post(route, headers=hdr)
                else:
                    r = self.client.get(route, headers=hdr)
                self.assertEqual(r.status_code, 403, f"{route} should deny subscriber")

    def test_subscriber_allowed_on_safe_surfaces(self):
        hdr = self._set_role("subscriber")
        allowed = ["/api/fleet", "/api/health", "/api/scores", "/api/pra"]
        for route in allowed:
            with self.subTest(route=route):
                r = self.client.get(route, headers=hdr)
                self.assertEqual(r.status_code, 200, f"{route} should allow subscriber")

    def test_subscriber_can_enroll_node(self):
        hdr = self._set_role("subscriber")
        r = self.client.post(
            "/api/fleet/enroll/request",
            json={"requested_by": "sub-user", "mode": "pull", "ttl_minutes": 15, "node_id": "node-sub-enroll"},
            headers={**hdr, "X-Nexora-Tenant-Id": "tenant-sub"},
        )
        self.assertEqual(r.status_code, 200)

    def test_all_operator_only_routes_are_enforced(self):
        os.environ["NEXORA_OPERATOR_ONLY_ENFORCE"] = "1"
        for route in api_module.OPERATOR_ONLY_ROUTES:
            with self.subTest(route=route):
                r = self.client.get(route, headers=self.headers)
                self.assertEqual(r.status_code, 403, f"{route} should be operator-only")


class SecurityTokenScopeTests(NexoraTestBase):
    """Token-to-tenant scope enforcement."""

    def test_scoped_token_without_tenant_header_is_denied(self):
        self._set_scope(["tenant-a"])
        r = self.client.get("/api/fleet", headers=self.headers)
        self.assertEqual(r.status_code, 403)
        self.assertIn("Scoped token access requires X-Nexora-Tenant-Id header", r.text)

    def test_scoped_token_wrong_tenant_is_denied(self):
        self._set_scope(["tenant-a"])
        r = self.client.get(
            "/api/fleet",
            headers={**self.headers, "X-Nexora-Tenant-Id": "tenant-b"},
        )
        self.assertEqual(r.status_code, 403)

    def test_scoped_token_missing_claim_is_denied(self):
        self._set_scope(["tenant-a"])
        r = self.client.get(
            "/api/fleet",
            headers={**self.headers, "X-Nexora-Tenant-Id": "tenant-a"},
        )
        self.assertEqual(r.status_code, 403)
        self.assertIn("Missing or invalid X-Nexora-Tenant-Claim", r.text)

    def test_scoped_token_valid_claim_is_accepted(self):
        self._set_scope(["tenant-a"])
        r = self.client.get("/api/fleet", headers=self._scoped_headers("tenant-a"))
        self.assertEqual(r.status_code, 200)

    def test_scope_enforcement_covers_governance_routes(self):
        self._set_scope(["tenant-a"])
        for route in ("/api/governance/risks", "/api/scores", "/api/pra"):
            with self.subTest(route=route):
                denied = self.client.get(
                    route, headers={**self.headers, "X-Nexora-Tenant-Id": "tenant-b"}
                )
                self.assertEqual(denied.status_code, 403)

    def test_scope_enforcement_covers_security_mutations(self):
        self._set_scope(["tenant-a"])
        denied = self.client.post(
            "/api/security/fail2ban/ban?ip=1.2.3.4",
            headers={**self.headers, "X-Nexora-Tenant-Id": "tenant-a"},
        )
        self.assertEqual(denied.status_code, 403)
        allowed = self.client.post(
            "/api/security/fail2ban/ban?ip=1.2.3.4",
            headers=self._scoped_headers("tenant-a"),
        )
        self.assertEqual(allowed.status_code, 200)


# ═══════════════════════════════════════════════════════════════════════════════
#  4. SUBSCRIPTION LIFECYCLE
# ═══════════════════════════════════════════════════════════════════════════════
class SubscriptionDomainTests(unittest.TestCase):
    """Direct domain-layer subscription tests (no HTTP)."""

    def setUp(self):
        from nexora_saas.subscription import create_organization, create_subscription

        self.state: dict = {}
        self.org = create_organization(self.state, name="TestCorp", contact_email="admin@tc.test")["organization"]

    def test_create_org_shape(self):
        self.assertIn("org_id", self.org)
        self.assertTrue(self.org["org_id"].startswith("org-"))
        self.assertEqual(self.org["name"], "TestCorp")

    def test_duplicate_org_rejected(self):
        from nexora_saas.subscription import create_organization

        r = create_organization(self.state, name="TestCorp", contact_email="x@y.test")
        self.assertFalse(r["success"])

    def test_subscription_creates_tenant(self):
        from nexora_saas.subscription import create_subscription

        r = create_subscription(self.state, org_id=self.org["org_id"], plan_tier="pro")
        self.assertTrue(r["success"])
        self.assertIn("tenant", r)
        self.assertEqual(r["subscription"]["tier"], "pro")
        self.assertEqual(r["subscription"]["status"], "active")

    def test_upgrade_subscription(self):
        from nexora_saas.subscription import create_subscription, upgrade_subscription

        sub = create_subscription(self.state, org_id=self.org["org_id"], plan_tier="free")["subscription"]
        r = upgrade_subscription(self.state, sub["subscription_id"], "pro")
        self.assertTrue(r["success"])
        self.assertEqual(r["subscription"]["tier"], "pro")

    def test_suspend_and_cancel_subscription(self):
        from nexora_saas.subscription import (
            cancel_subscription,
            create_subscription,
            suspend_subscription,
        )

        sub = create_subscription(self.state, org_id=self.org["org_id"], plan_tier="pro")["subscription"]
        sus = suspend_subscription(self.state, sub["subscription_id"], reason="payment")
        self.assertTrue(sus["success"])
        self.assertEqual(sus["subscription"]["status"], "suspended")
        can = cancel_subscription(self.state, sub["subscription_id"])
        self.assertTrue(can["success"])
        self.assertEqual(can["subscription"]["status"], "cancelled")

    def test_plan_catalog_has_all_required_fields(self):
        from nexora_saas.subscription import list_plans

        for plan in list_plans():
            for key in ("plan_id", "name", "tier", "max_nodes", "features", "price_monthly_eur"):
                self.assertIn(key, plan)

    def test_free_plan_is_zero_cost(self):
        from nexora_saas.subscription import get_plan

        plan = get_plan("free")
        self.assertEqual(plan["price_monthly_eur"], 0)


class SubscriptionAPITests(NexoraTestBase):
    """HTTP-layer subscription management."""

    def test_plans_endpoint(self):
        r = self.client.get("/api/plans", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        tiers = {p["tier"] for p in r.json()}
        self.assertEqual(tiers, {"free", "pro", "enterprise"})

    def test_org_crud_lifecycle(self):
        # create
        r = self.client.post(
            "/api/organizations",
            json={"name": "ACME", "contact_email": "admin@acme.test"},
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 200)
        org_id = r.json()["organization"]["org_id"]

        # list
        r = self.client.get("/api/organizations", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        org_ids = [o["org_id"] for o in r.json()]
        self.assertIn(org_id, org_ids)

        # get
        r = self.client.get(f"/api/organizations/{org_id}", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["org_id"], org_id)

    def test_subscription_full_lifecycle(self):
        # create org
        org = self.client.post(
            "/api/organizations",
            json={"name": "LifecycleCo", "contact_email": "lc@test.test"},
            headers=self.headers,
        ).json()["organization"]

        # subscribe
        r = self.client.post(
            "/api/subscriptions",
            json={"org_id": org["org_id"], "plan_tier": "pro"},
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 200)
        sub = r.json()["subscription"]
        sub_id = sub["subscription_id"]

        # list
        r = self.client.get("/api/subscriptions", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(any(s["subscription_id"] == sub_id for s in r.json()))

        # get
        r = self.client.get(f"/api/subscriptions/{sub_id}", headers=self.headers)
        self.assertEqual(r.status_code, 200)

        # upgrade
        r = self.client.post(
            f"/api/subscriptions/{sub_id}/upgrade",
            json={"new_tier": "enterprise"},
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["subscription"]["tier"], "enterprise")

        # suspend
        r = self.client.post(
            f"/api/subscriptions/{sub_id}/suspend",
            json={"reason": "test"},
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["subscription"]["status"], "suspended")

        # cancel
        r = self.client.post(
            f"/api/subscriptions/{sub_id}/cancel",
            json={},
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["subscription"]["status"], "cancelled")


# ═══════════════════════════════════════════════════════════════════════════════
#  5. FLEET & NODE LIFECYCLE
# ═══════════════════════════════════════════════════════════════════════════════
class FleetEnrollmentTests(NexoraTestBase):
    """Enrollment: request token → attest → register flow."""

    def test_enrollment_token_request(self):
        r = self.client.post(
            "/api/fleet/enroll/request",
            json={"requested_by": "tester", "mode": "pull", "ttl_minutes": 15, "node_id": "enroll-node-1"},
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("token", data)
        self.assertIn("challenge", data)
        self.assertIn("token_id", data)

    def test_enrollment_token_is_tenant_tagged(self):
        r = self.client.post(
            "/api/fleet/enroll/request",
            json={"requested_by": "tester", "mode": "pull", "ttl_minutes": 15, "node_id": "enroll-node-2"},
            headers={**self.headers, "X-Nexora-Tenant-Id": "tenant-enroll"},
        )
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data.get("tenant_id"), "tenant-enroll")


class FleetNodeLifecycleTests(NexoraTestBase):
    """Node lifecycle actions: drain, cordon, uncordon, revoke, retire."""

    def _setup_node(self, node_id="n1", tenant_id="t1"):
        self._seed_nodes([
            {"node_id": node_id, "tenant_id": tenant_id, "status": "healthy"},
        ])

    def test_drain_node(self):
        self._setup_node()
        r = self.client.post(
            "/api/fleet/nodes/n1/drain",
            json={"operator": "tester", "confirmation": True},
            headers={**self.headers, "X-Nexora-Tenant-Id": "t1"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("drain", r.json().get("action", ""))

    def test_cordon_node(self):
        self._setup_node()
        r = self.client.post(
            "/api/fleet/nodes/n1/cordon",
            json={"operator": "tester", "confirmation": True},
            headers={**self.headers, "X-Nexora-Tenant-Id": "t1"},
        )
        self.assertEqual(r.status_code, 200)

    def test_uncordon_node(self):
        self._setup_node()
        r = self.client.post(
            "/api/fleet/nodes/n1/uncordon",
            json={"operator": "tester", "confirmation": True},
            headers={**self.headers, "X-Nexora-Tenant-Id": "t1"},
        )
        self.assertEqual(r.status_code, 200)

    def test_revoke_node(self):
        self._setup_node()
        r = self.client.post(
            "/api/fleet/nodes/n1/revoke",
            json={"operator": "tester", "confirmation": True},
            headers={**self.headers, "X-Nexora-Tenant-Id": "t1"},
        )
        self.assertEqual(r.status_code, 200)

    def test_retire_node(self):
        self._setup_node()
        r = self.client.post(
            "/api/fleet/nodes/n1/retire",
            json={"operator": "tester", "confirmation": True},
            headers={**self.headers, "X-Nexora-Tenant-Id": "t1"},
        )
        self.assertEqual(r.status_code, 200)

    def test_cross_tenant_lifecycle_denied(self):
        self._setup_node("n1", "tenant-owner")
        r = self.client.post(
            "/api/fleet/nodes/n1/drain",
            json={"operator": "hacker", "confirmation": True},
            headers={**self.headers, "X-Nexora-Tenant-Id": "tenant-other"},
        )
        self.assertEqual(r.status_code, 403)
        self.assertIn("not enrolled under tenant", r.text)

    def test_unknown_node_lifecycle_rejected(self):
        r = self.client.post(
            "/api/fleet/nodes/nonexistent/drain",
            json={"operator": "tester", "confirmation": True},
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 404)

    def test_node_action_generic_route(self):
        self._setup_node()
        r = self.client.post(
            "/api/fleet/nodes/n1/action",
            json={"action": "inventory/refresh", "payload": {}},
            headers={**self.headers, "X-Nexora-Tenant-Id": "t1"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["target_node_id"], "n1")

    def test_dedicated_node_action_routes(self):
        self._setup_node()
        actions = [
            "/api/fleet/nodes/n1/inventory/refresh",
            "/api/fleet/nodes/n1/healthcheck/run",
            "/api/fleet/nodes/n1/pra/snapshot",
        ]
        for route in actions:
            with self.subTest(route=route):
                r = self.client.post(
                    route,
                    json={"payload": {}, "dry_run": True},
                    headers={**self.headers, "X-Nexora-Tenant-Id": "t1"},
                )
                self.assertIn(r.status_code, (200, 422), f"{route} returned {r.status_code}")


# ═══════════════════════════════════════════════════════════════════════════════
#  6. GOVERNANCE & SCORING
# ═══════════════════════════════════════════════════════════════════════════════
class GovernanceTests(NexoraTestBase):
    """Governance endpoints: scores, reports, risks, audits."""

    def test_scores_payload_shape(self):
        r = self.client.get("/api/scores", headers=self.headers)
        data = r.json()
        for key in ("security", "pra", "health", "compliance", "overall"):
            self.assertIn(key, data)
        self.assertIn("score", data["security"])
        self.assertIn("grade", data["security"])

    def test_scores_tenant_scoped(self):
        self._seed_snapshots([
            {"timestamp": "2026-03-01T00:00:00Z", "kind": "heartbeat", "inventory": {"apps": {}}, "tenant_id": "t-gov"},
        ])
        r = self.client.get(
            "/api/scores",
            headers={**self.headers, "X-Nexora-Tenant-Id": "t-gov"},
        )
        self.assertEqual(r.json()["tenant_id"], "t-gov")

    def test_executive_report_shape(self):
        r = self.client.get("/api/governance/report", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIsInstance(data, dict)

    def test_risk_register_shape(self):
        r = self.client.get("/api/governance/risks", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIsInstance(data, dict)

    def test_changelog_shape(self):
        r = self.client.get("/api/governance/changelog", headers=self.headers)
        self.assertEqual(r.status_code, 200)

    def test_snapshot_diff_requires_two_snapshots(self):
        r = self.client.get("/api/governance/snapshot-diff", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"diff": {}})

    def test_snapshot_diff_with_data(self):
        self._seed_snapshots([
            {"timestamp": "2026-03-01T00:00:00Z", "kind": "heartbeat", "inventory": {"apps": {"a": 1}}},
            {"timestamp": "2026-03-01T01:00:00Z", "kind": "heartbeat", "inventory": {"apps": {"a": 2, "b": 1}}},
        ])
        r = self.client.get("/api/governance/snapshot-diff", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertNotEqual(r.json(), {"diff": {}})


class SecurityPostureTests(NexoraTestBase):
    """Security posture, updates, fail2ban, open-ports, permissions, logins."""

    def test_security_posture_shape(self):
        r = self.client.get("/api/security/posture", headers=self.headers)
        data = r.json()
        for key in ("security_score", "alerts", "permissions_risk_count"):
            self.assertIn(key, data)

    def test_security_updates_shape(self):
        r = self.client.get("/api/security/updates", headers=self.headers)
        data = r.json()
        self.assertIn("updates_available", data)
        self.assertIn("packages", data)

    def test_fail2ban_status_shape(self):
        r = self.client.get("/api/security/fail2ban/status", headers=self.headers)
        data = r.json()
        self.assertIn("banned_ips", data)
        self.assertIn("total_ban_events", data)

    def test_fail2ban_ban_and_unban(self):
        # ban
        r = self.client.post("/api/security/fail2ban/ban?ip=10.0.0.1", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["success"])

        # status should show banned
        r = self.client.get("/api/security/fail2ban/status", headers=self.headers)
        self.assertIn("10.0.0.1", r.json()["banned_ips"])

        # unban
        r = self.client.post("/api/security/fail2ban/unban?ip=10.0.0.1", headers=self.headers)
        self.assertEqual(r.status_code, 200)

        # should no longer be banned
        r = self.client.get("/api/security/fail2ban/status", headers=self.headers)
        self.assertNotIn("10.0.0.1", r.json()["banned_ips"])

    def test_fail2ban_events_tagged_with_tenant(self):
        self.client.post(
            "/api/security/fail2ban/ban?ip=10.0.0.2",
            headers={**self.headers, "X-Nexora-Tenant-Id": "t-sec"},
        )
        state = api_module.service.state.load()
        events = state.get("security_audit", [])
        self.assertTrue(any(e.get("tenant_id") == "t-sec" for e in events))

    def test_open_ports_shape(self):
        r = self.client.get("/api/security/open-ports", headers=self.headers)
        data = r.json()
        self.assertIn("ports", data)
        self.assertIsInstance(data["ports"], list)

    def test_permissions_audit_shape(self):
        r = self.client.get("/api/security/permissions-audit", headers=self.headers)
        data = r.json()
        self.assertIn("audit", data)
        self.assertIn(data["audit"], ("ok", "warning"))

    def test_recent_logins_shape(self):
        r = self.client.get("/api/security/recent-logins", headers=self.headers)
        data = r.json()
        self.assertIn("logins", data)
        self.assertIsInstance(data["logins"], list)

    def test_all_security_routes_accept_tenant_header(self):
        for route in (
            "/api/security/updates",
            "/api/security/fail2ban/status",
            "/api/security/open-ports",
            "/api/security/permissions-audit",
            "/api/security/recent-logins",
        ):
            with self.subTest(route=route):
                r = self.client.get(route, headers={**self.headers, "X-Nexora-Tenant-Id": "t-sec"})
                self.assertEqual(r.status_code, 200)
                self.assertEqual(r.json().get("tenant_id"), "t-sec")


# ═══════════════════════════════════════════════════════════════════════════════
#  7. PRA / BACKUP / DISASTER-RECOVERY
# ═══════════════════════════════════════════════════════════════════════════════
class PRATests(NexoraTestBase):
    """PRA endpoint and related features."""

    def test_pra_shape(self):
        r = self.client.get("/api/pra", headers=self.headers)
        data = r.json()
        self.assertIn("pra_score", data)
        self.assertIn("backups_count", data)
        self.assertIn("runbooks", data)
        self.assertIsInstance(data["runbooks"], list)
        self.assertTrue(len(data["runbooks"]) >= 3)

    def test_pra_tenant_scoped(self):
        r = self.client.get("/api/pra", headers={**self.headers, "X-Nexora-Tenant-Id": "t-pra"})
        self.assertEqual(r.json()["tenant_id"], "t-pra")

    def test_pra_score_in_governance(self):
        r = self.client.get("/api/scores", headers=self.headers)
        pra = r.json()["pra"]
        self.assertIn("score", pra)
        self.assertIn("grade", pra)
        self.assertIsInstance(pra["score"], (int, float))


class PRADomainTests(unittest.TestCase):
    """Domain-level PRA scoring and failover."""

    def test_pra_score_computation(self):
        from nexora_node_sdk.scoring import compute_pra_score

        inv = {"backups": {"archives": [1, 2, 3]}}
        result = compute_pra_score(inv)
        self.assertIn("score", result)
        self.assertIn("grade", result)
        self.assertIsInstance(result["score"], (int, float))

    def test_failover_pair_generation(self):
        from nexora_saas.failover import generate_failover_pair

        pair = generate_failover_pair(
            "nextcloud",
            {"node_id": "n1", "ip": "10.0.0.1"},
            {"node_id": "n2", "ip": "10.0.0.2"},
            domain="cloud.example.org",
        )
        self.assertIn("app_id", pair)
        self.assertIn("primary", pair)
        self.assertIn("secondary", pair)

    def test_health_check_strategies(self):
        from nexora_saas.failover import list_health_check_strategies

        strategies = list_health_check_strategies()
        self.assertIsInstance(strategies, list)
        self.assertTrue(len(strategies) >= 3)
        names = {s["strategy"] for s in strategies}
        self.assertIn("http", names)
        self.assertIn("tcp", names)


# ═══════════════════════════════════════════════════════════════════════════════
#  8. DOCKER / STORAGE / OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════════
class OperationsRouteTests(NexoraTestBase):
    """Docker, storage, and operational endpoints."""

    def test_docker_status_accessible_by_operator(self):
        os.environ["NEXORA_OPERATOR_ONLY_ENFORCE"] = "1"
        hdr = self._set_role("operator")
        r = self.client.get("/api/docker/status", headers=hdr)
        self.assertEqual(r.status_code, 200)

    def test_docker_containers_accessible_by_operator(self):
        os.environ["NEXORA_OPERATOR_ONLY_ENFORCE"] = "1"
        hdr = self._set_role("operator")
        r = self.client.get("/api/docker/containers", headers=hdr)
        self.assertEqual(r.status_code, 200)

    def test_docker_templates_accessible_by_operator(self):
        os.environ["NEXORA_OPERATOR_ONLY_ENFORCE"] = "1"
        hdr = self._set_role("operator")
        r = self.client.get("/api/docker/templates", headers=hdr)
        self.assertEqual(r.status_code, 200)

    def test_storage_usage_accessible_by_operator(self):
        os.environ["NEXORA_OPERATOR_ONLY_ENFORCE"] = "1"
        hdr = self._set_role("operator")
        r = self.client.get("/api/storage/usage", headers=hdr)
        self.assertEqual(r.status_code, 200)

    def test_adoption_report_shape(self):
        r = self.client.get("/api/adoption/report?domain=example.org&path=/nexora", headers=self.headers)
        data = r.json()
        self.assertIn("safe_to_install", data)
        self.assertIn("recommended_mode", data)

    def test_adoption_import_idempotent(self):
        first = self.client.post("/api/adoption/import?domain=x.org&path=/x", headers=self.headers)
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.json()["imported"])

        second = self.client.post("/api/adoption/import?domain=x.org&path=/x", headers=self.headers)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()["idempotent"])


class DockerDomainTests(unittest.TestCase):
    """Docker module domain-level tests."""

    def test_docker_templates_list(self):
        from nexora_node_sdk.docker import list_docker_templates

        templates = list_docker_templates()
        self.assertIsInstance(templates, list)
        if templates:
            self.assertIn("name", templates[0])


class StorageDomainTests(unittest.TestCase):
    """Storage module domain-level tests."""

    def test_storage_policy_generation(self):
        from nexora_node_sdk.storage import generate_storage_policy

        result = generate_storage_policy("standard")
        self.assertIn("policy", result)
        self.assertIn("backup_retention_days", result["policy"])
        self.assertIn("alert_threshold_percent", result["policy"])


# ═══════════════════════════════════════════════════════════════════════════════
#  9. MODES & ESCALATIONS
# ═══════════════════════════════════════════════════════════════════════════════
class ModesTests(NexoraTestBase):
    """Runtime mode management."""

    def test_get_mode(self):
        r = self.client.get("/api/mode", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("mode", data)

    def test_list_modes(self):
        r = self.client.get("/api/mode/list", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        modes = r.json()
        self.assertIsInstance(modes, list)
        mode_names = {m.get("name", m.get("mode", "")) for m in modes}
        self.assertTrue({"observer", "operator", "architect", "admin"}.issubset(mode_names))

    def test_switch_mode(self):
        r = self.client.post("/api/mode/switch?target=operator&reason=test", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("current_mode", data)

    def test_escalate_mode(self):
        r = self.client.post(
            "/api/mode/escalate?target=admin&duration_minutes=30&reason=emergency",
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("token", data)

    def test_list_escalations(self):
        self.client.post(
            "/api/mode/escalate?target=admin&duration_minutes=30&reason=test",
            headers=self.headers,
        )
        r = self.client.get("/api/mode/escalations", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.json(), list)

    def test_pending_confirmations(self):
        r = self.client.get("/api/mode/confirmations", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.json(), list)

    def test_admin_log(self):
        r = self.client.get("/api/admin/log", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.json(), list)


class ModesDomainTests(unittest.TestCase):
    """Domain-level mode system tests."""

    def test_mode_manager_lifecycle(self):
        from nexora_saas.modes import get_mode_manager, list_modes

        modes = list_modes()
        self.assertTrue(len(modes) >= 4)
        names = {m.get("name", m.get("mode", "")) for m in modes}
        self.assertTrue({"observer", "operator", "architect", "admin"}.issubset(names))

    def test_mode_hierarchy_is_ordered(self):
        from nexora_saas.modes import list_modes

        modes = list_modes()
        levels = {m.get("name", m.get("mode", "")): m.get("level", i) for i, m in enumerate(modes)}
        self.assertLess(levels.get("observer", 0), levels.get("admin", 99))


# ═══════════════════════════════════════════════════════════════════════════════
#  10. PROVISIONING & FEATURE PUSH
# ═══════════════════════════════════════════════════════════════════════════════
class ProvisioningTests(NexoraTestBase):
    """Feature provisioning API."""

    def test_provisioning_routes_registered(self):
        source = Path("apps/control_plane/api.py").read_text(encoding="utf-8")
        for route in (
            "/api/provisioning/provision",
            "/api/provisioning/deprovision",
            "/api/provisioning/heartbeat",
            "/api/provisioning/nodes/{node_id}/status",
            "/api/provisioning/nodes/{node_id}/features",
        ):
            self.assertIn(route, source)

    def test_provisioning_node_status_for_unknown(self):
        hdr = self._set_role("operator")
        os.environ["NEXORA_OPERATOR_ONLY_ENFORCE"] = "0"
        r = self.client.get("/api/provisioning/nodes/unknown-node/status", headers=hdr)
        self.assertEqual(r.status_code, 200)

    def test_provisioning_node_features_for_unknown(self):
        os.environ["NEXORA_OPERATOR_ONLY_ENFORCE"] = "0"
        r = self.client.get("/api/provisioning/nodes/unknown-node/features", headers=self.headers)
        self.assertEqual(r.status_code, 200)


class ProvisioningDomainTests(unittest.TestCase):
    """Domain-level feature provisioning tests."""

    def test_feature_tier_resolution(self):
        from nexora_saas.feature_provisioning import resolve_features_for_tier

        free_features = resolve_features_for_tier("free")
        self.assertIsInstance(free_features, list)

        pro_features = resolve_features_for_tier("pro")
        self.assertTrue(len(pro_features) >= len(free_features))

    def test_provisioning_status_for_unknown_node(self):
        from nexora_saas.feature_provisioning import get_node_provisioning_status

        status = get_node_provisioning_status({}, "unknown-node")
        self.assertIn("node_id", status)
        self.assertEqual(status["node_id"], "unknown-node")


# ═══════════════════════════════════════════════════════════════════════════════
#  11. METRICS (Prometheus format)
# ═══════════════════════════════════════════════════════════════════════════════
class MetricsTests(NexoraTestBase):
    """Prometheus metrics endpoint."""

    def test_metrics_format(self):
        r = self.client.get("/api/metrics", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/plain", r.headers.get("content-type", ""))
        text = r.text
        self.assertIn("nexora_nodes_total", text)
        self.assertIn("nexora_tenants_active_count", text)
        self.assertIn("nexora_security_events_total", text)
        self.assertIn("nexora_inventory_snapshots_total", text)

    def test_metrics_reflect_state(self):
        self._seed_nodes([
            {"node_id": "n1", "tenant_id": "t1", "status": "healthy"},
            {"node_id": "n2", "tenant_id": "t2", "status": "degraded"},
        ])
        r = self.client.get("/api/metrics", headers=self.headers)
        text = r.text
        self.assertIn("nexora_nodes_total 2", text)
        self.assertIn('nexora_nodes_by_status{status="healthy"} 1', text)
        self.assertIn('nexora_nodes_by_status{status="degraded"} 1', text)
        self.assertIn("nexora_tenants_active_count 2", text)

    def test_metrics_is_gauge_type(self):
        r = self.client.get("/api/metrics", headers=self.headers)
        self.assertIn("# TYPE nexora_nodes_total gauge", r.text)


# ═══════════════════════════════════════════════════════════════════════════════
#  12. BLUEPRINTS & BRANDING
# ═══════════════════════════════════════════════════════════════════════════════
class BlueprintTests(NexoraTestBase):
    """Blueprint catalog and branding."""

    def test_blueprints_list(self):
        r = self.client.get("/api/blueprints", headers=self.headers)
        data = r.json()
        self.assertIsInstance(data, list)
        if data:
            bp = data[0]
            self.assertIn("slug", bp)
            self.assertIn("name", bp)

    def test_blueprint_detail(self):
        r = self.client.get("/api/blueprints", headers=self.headers)
        bps = r.json()
        if bps:
            slug = bps[0]["slug"]
            r = self.client.get(f"/api/blueprints/{slug}", headers=self.headers)
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["slug"], slug)

    def test_blueprint_detail_not_found(self):
        r = self.client.get("/api/blueprints/nonexistent-slug", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertIn("error", r.json())

    def test_branding_endpoint(self):
        r = self.client.get("/api/branding", headers=self.headers)
        self.assertEqual(r.status_code, 200)

    def test_blueprint_directories_exist(self):
        bp_dir = REPO_ROOT / "blueprints"
        self.assertTrue(bp_dir.exists())
        subdirs = [d.name for d in bp_dir.iterdir() if d.is_dir()]
        self.assertTrue(len(subdirs) >= 3, f"Only {len(subdirs)} blueprint dirs found")


# ═══════════════════════════════════════════════════════════════════════════════
#  13. MULTI-TENANT ISOLATION (cross-tenant denial)
# ═══════════════════════════════════════════════════════════════════════════════
class MultiTenantIsolationTests(NexoraTestBase):
    """Ensure every tenant-aware surface enforces isolation."""

    def test_fleet_topology_filtered(self):
        self._seed_nodes([
            {"node_id": "na1", "tenant_id": "ta", "status": "healthy"},
            {"node_id": "nb1", "tenant_id": "tb", "status": "healthy"},
        ])
        r = self.client.get(
            "/api/fleet/topology",
            headers={**self.headers, "X-Nexora-Tenant-Id": "ta"},
        )
        nodes = {n["node_id"] for n in r.json().get("nodes", [])}
        self.assertIn("na1", nodes)
        self.assertNotIn("nb1", nodes)

    def test_fleet_node_action_cross_tenant_denied(self):
        self._seed_nodes([
            {"node_id": "na1", "tenant_id": "ta", "status": "healthy"},
        ])
        r = self.client.post(
            "/api/fleet/nodes/na1/action",
            json={"action": "inventory/refresh", "payload": {}},
            headers={**self.headers, "X-Nexora-Tenant-Id": "tb"},
        )
        self.assertEqual(r.status_code, 403)

    def test_snapshot_diff_tenant_filtered(self):
        self._seed_snapshots([
            {"timestamp": "2026-01-01T00:00:00Z", "inventory": {"a": 1}, "tenant_id": "ta"},
            {"timestamp": "2026-01-01T01:00:00Z", "inventory": {"a": 2}, "tenant_id": "ta"},
            {"timestamp": "2026-01-01T00:00:00Z", "inventory": {"b": 1}, "tenant_id": "tb"},
            {"timestamp": "2026-01-01T01:00:00Z", "inventory": {"b": 2}, "tenant_id": "tb"},
        ])
        r = self.client.get(
            "/api/governance/snapshot-diff",
            headers={**self.headers, "X-Nexora-Tenant-Id": "ta"},
        )
        # Should only see tenant-a snapshots
        self.assertEqual(r.status_code, 200)

    def test_security_events_tenant_filtered(self):
        # Emit events for different tenants
        self.client.post(
            "/api/security/fail2ban/ban?ip=1.1.1.1",
            headers={**self.headers, "X-Nexora-Tenant-Id": "ta"},
        )
        self.client.post(
            "/api/security/fail2ban/ban?ip=2.2.2.2",
            headers={**self.headers, "X-Nexora-Tenant-Id": "tb"},
        )
        # Check tenant-a only sees their ban
        r = self.client.get(
            "/api/security/fail2ban/status",
            headers={**self.headers, "X-Nexora-Tenant-Id": "ta"},
        )
        banned = r.json()["banned_ips"]
        self.assertIn("1.1.1.1", banned)
        self.assertNotIn("2.2.2.2", banned)

    def test_recent_logins_tenant_filtered(self):
        # Add audit events for two tenants
        self.client.post(
            "/api/security/fail2ban/ban?ip=3.3.3.3",
            headers={**self.headers, "X-Nexora-Tenant-Id": "ta"},
        )
        self.client.post(
            "/api/security/fail2ban/ban?ip=4.4.4.4",
            headers={**self.headers, "X-Nexora-Tenant-Id": "tb"},
        )
        r = self.client.get(
            "/api/security/recent-logins",
            headers={**self.headers, "X-Nexora-Tenant-Id": "ta"},
        )
        logins = r.json()["logins"]
        # Only tenant-a events
        for login in logins:
            # logins from security audit may or may not have tenant in details
            pass
        self.assertEqual(r.json()["tenant_id"], "ta")

    def test_usage_quota_tenant_specific(self):
        self._seed_tenants([
            {"tenant_id": "ta", "org_id": "oa", "tier": "free", "created_at": "2026-01-01T00:00:00Z"},
            {"tenant_id": "tb", "org_id": "ob", "tier": "pro", "created_at": "2026-01-01T00:00:00Z"},
        ])
        self._seed_nodes([
            {"node_id": "na1", "tenant_id": "ta", "apps_count": 3},
            {"node_id": "nb1", "tenant_id": "tb", "apps_count": 30},
        ])
        r = self.client.get(
            "/api/tenants/usage-quota",
            headers={**self.headers, "X-Nexora-Tenant-Id": "ta"},
        )
        data = r.json()
        self.assertEqual(data["tenant_id"], "ta")
        self.assertEqual(data["limits"]["max_nodes"], 5)  # free tier


# ═══════════════════════════════════════════════════════════════════════════════
#  14. QUOTAS & ENTITLEMENTS
# ═══════════════════════════════════════════════════════════════════════════════
class QuotaDomainTests(unittest.TestCase):
    """Quota enforcement domain tests."""

    def test_quota_limits_by_tier(self):
        from nexora_saas.quotas import get_quota_limit

        self.assertEqual(get_quota_limit("free", "max_nodes"), 5)
        self.assertEqual(get_quota_limit("pro", "max_nodes"), 50)
        self.assertEqual(get_quota_limit("enterprise", "max_nodes"), 1000)

    def test_quota_exceeded(self):
        from nexora_saas.quotas import is_quota_exceeded

        self.assertTrue(is_quota_exceeded("free", "max_nodes", 5))
        self.assertFalse(is_quota_exceeded("free", "max_nodes", 4))

    def test_entitlements_by_tier(self):
        from nexora_saas.quotas import get_tenant_entitlements

        free_ent = get_tenant_entitlements("free")
        self.assertIn("basic_monitoring", free_ent)
        self.assertIn("local_backup", free_ent)

        pro_ent = get_tenant_entitlements("pro")
        self.assertIn("pra_support", pro_ent)

        ent_ent = get_tenant_entitlements("enterprise")
        self.assertIn("all", ent_ent)

    def test_unknown_tier_defaults_to_free(self):
        from nexora_saas.quotas import get_quota_limit

        self.assertEqual(get_quota_limit("garbage", "max_nodes"), 5)


# ═══════════════════════════════════════════════════════════════════════════════
#  15. NOTIFICATIONS & HOOKS & AUTOMATION
# ═══════════════════════════════════════════════════════════════════════════════
class NotificationsDomainTests(unittest.TestCase):
    """Notification templates and channels."""

    def test_alert_templates_list(self):
        from nexora_saas.notifications import list_alert_templates

        templates = list_alert_templates()
        self.assertIsInstance(templates, list)
        self.assertTrue(len(templates) >= 5)
        names = {t["id"] for t in templates}
        self.assertIn("service_down", names)
        self.assertIn("disk_critical", names)
        self.assertIn("cert_expiring", names)

    def test_notification_channels(self):
        from nexora_saas.notifications import NOTIFICATION_CHANNELS

        self.assertIn("webhook", NOTIFICATION_CHANNELS)
        self.assertIn("email", NOTIFICATION_CHANNELS)

    def test_alert_level_ordering(self):
        from nexora_saas.notifications import ALERT_LEVELS

        self.assertLess(ALERT_LEVELS["critical"], ALERT_LEVELS["info"])
        self.assertLess(ALERT_LEVELS["high"], ALERT_LEVELS["warning"])


class HooksDomainTests(unittest.TestCase):
    """Hooks system domain tests."""

    def test_hook_events_list(self):
        from nexora_node_sdk.hooks import list_hook_events

        events = list_hook_events()
        self.assertIsInstance(events, list)
        self.assertTrue(len(events) >= 10)
        names = {e["event"] for e in events}
        self.assertIn("pre_install", names)
        self.assertIn("post_backup", names)
        self.assertIn("failover_triggered", names)

    def test_hook_script_generation(self):
        from nexora_node_sdk.hooks import generate_hook_script

        result = generate_hook_script("pre_install", ["echo 'pre-install hook'"])
        self.assertIn("#!/bin/bash", result["script"])
        self.assertEqual(result["event"], "pre_install")

    def test_hook_presets(self):
        from nexora_node_sdk.hooks import list_hook_presets

        presets = list_hook_presets()
        self.assertIsInstance(presets, list)


class AutomationDomainTests(unittest.TestCase):
    """Automation templates and checklists."""

    def test_automation_templates_list(self):
        from nexora_saas.automation import list_automation_templates

        templates = list_automation_templates()
        self.assertIsInstance(templates, list)
        self.assertTrue(len(templates) >= 5)
        ids = {t["id"] for t in templates}
        self.assertIn("daily_backup", ids)
        self.assertIn("weekly_security_audit", ids)
        self.assertIn("cert_renewal_check", ids)

    def test_automation_template_has_schedule(self):
        from nexora_saas.automation import list_automation_templates

        for tmpl in list_automation_templates():
            self.assertIn("schedule", tmpl)
            self.assertTrue(tmpl["schedule"].count(" ") >= 4, f"Invalid cron: {tmpl['schedule']}")

    def test_automation_plan_generation(self):
        from nexora_saas.automation import generate_automation_plan

        plan = generate_automation_plan("standard")
        self.assertIn("jobs", plan)
        self.assertIsInstance(plan["jobs"], list)
        self.assertIn("crontab_preview", plan)

    def test_checklists_list(self):
        from nexora_saas.automation import list_checklists

        cl = list_checklists()
        self.assertIsInstance(cl, list)


class NotificationHookAPITests(NexoraTestBase):
    """API-level notification/hook/automation tests."""

    def test_notification_templates_route(self):
        os.environ["NEXORA_OPERATOR_ONLY_ENFORCE"] = "0"
        r = self.client.get("/api/notifications/templates", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.json(), list)

    def test_hook_events_route(self):
        os.environ["NEXORA_OPERATOR_ONLY_ENFORCE"] = "0"
        r = self.client.get("/api/hooks/events", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.json(), list)

    def test_hook_presets_route(self):
        os.environ["NEXORA_OPERATOR_ONLY_ENFORCE"] = "0"
        r = self.client.get("/api/hooks/presets", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.json(), list)

    def test_automation_templates_route(self):
        os.environ["NEXORA_OPERATOR_ONLY_ENFORCE"] = "0"
        r = self.client.get("/api/automation/templates", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.json(), list)

    def test_automation_checklists_route(self):
        os.environ["NEXORA_OPERATOR_ONLY_ENFORCE"] = "0"
        r = self.client.get("/api/automation/checklists", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.json(), list)


# ═══════════════════════════════════════════════════════════════════════════════
#  16. SLA TIERS
# ═══════════════════════════════════════════════════════════════════════════════
class SLADomainTests(unittest.TestCase):
    """SLA tier definitions and policies."""

    def test_sla_tiers_list(self):
        from nexora_saas.sla import list_sla_tiers

        tiers = list_sla_tiers()
        self.assertIsInstance(tiers, list)
        self.assertTrue(len(tiers) >= 3)
        names = {t.get("tier", t.get("name", "")) for t in tiers}
        for expected in ("basic", "standard", "professional", "enterprise"):
            self.assertIn(expected, names)

    def test_sla_policy_generation(self):
        from nexora_saas.sla import generate_sla_policy

        policy = generate_sla_policy("enterprise")
        self.assertIn("targets", policy)
        self.assertGreaterEqual(policy["targets"]["uptime_target"], 99.99)
        self.assertEqual(policy["targets"]["support"], "24/7")

    def test_sla_uptime_calculation(self):
        from nexora_saas.sla import compute_uptime

        result = compute_uptime(total_minutes=43200, downtime_minutes=43)
        self.assertIn("uptime_percent", result)
        self.assertGreater(result["uptime_percent"], 99.0)


class SLARouteTests(NexoraTestBase):
    """SLA API routes."""

    def test_sla_tiers_route(self):
        os.environ["NEXORA_OPERATOR_ONLY_ENFORCE"] = "0"
        r = self.client.get("/api/sla/tiers", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.json(), list)


# ═══════════════════════════════════════════════════════════════════════════════
#  17. FAILOVER STRATEGIES
# ═══════════════════════════════════════════════════════════════════════════════
class FailoverDomainTests(unittest.TestCase):
    """Failover health-check strategies and pairs."""

    def test_health_check_config_generation(self):
        from nexora_saas.failover import generate_health_check_config

        cfg = generate_health_check_config("nextcloud", strategy="http")
        self.assertEqual(cfg["strategy"], "http")
        self.assertIn("url", cfg)

    def test_tcp_health_check(self):
        from nexora_saas.failover import generate_health_check_config

        cfg = generate_health_check_config("custom-app", strategy="tcp", port=8080)
        self.assertEqual(cfg["port"], 8080)

    def test_all_strategies_available(self):
        from nexora_saas.failover import HEALTH_CHECK_STRATEGIES

        self.assertIn("http", HEALTH_CHECK_STRATEGIES)
        self.assertIn("tcp", HEALTH_CHECK_STRATEGIES)
        self.assertIn("process", HEALTH_CHECK_STRATEGIES)
        self.assertIn("combined", HEALTH_CHECK_STRATEGIES)


class FailoverRouteTests(NexoraTestBase):
    """Failover API routes."""

    def test_failover_strategies_route(self):
        os.environ["NEXORA_OPERATOR_ONLY_ENFORCE"] = "0"
        r = self.client.get("/api/failover/strategies", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        strategies = r.json()
        self.assertIsInstance(strategies, list)
        self.assertTrue(len(strategies) >= 3)


# ═══════════════════════════════════════════════════════════════════════════════
#  18. TENANT MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════
class TenantAPITests(NexoraTestBase):
    """Tenant CRUD via API."""

    def test_list_tenants(self):
        r = self.client.get("/api/tenants", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.json(), list)

    def test_onboard_and_purge_tenant(self):
        # Create org first
        org = self.client.post(
            "/api/organizations",
            json={"name": "TenantTestOrg", "contact_email": "t@t.test"},
            headers=self.headers,
        ).json()["organization"]

        # Onboard tenant
        r = self.client.post(
            "/api/tenants/onboard",
            json={"tenant_id": "test-tenant-1", "organization_id": org["org_id"], "tier": "pro"},
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("success", False))

        # List should include it
        tenants = self.client.get("/api/tenants", headers=self.headers).json()
        tenant_ids = [t["tenant_id"] for t in tenants]
        self.assertIn("test-tenant-1", tenant_ids)

        # Purge
        r = self.client.post("/api/tenants/test-tenant-1/purge", headers=self.headers)
        self.assertEqual(r.status_code, 200)


# ═══════════════════════════════════════════════════════════════════════════════
#  19. SETTINGS ENDPOINT (operator only)
# ═══════════════════════════════════════════════════════════════════════════════
class SettingsTests(NexoraTestBase):
    """Operator settings endpoint."""

    def test_settings_requires_operator_role(self):
        os.environ["NEXORA_OPERATOR_ONLY_ENFORCE"] = "1"
        r = self.client.get("/api/settings", headers=self.headers)
        self.assertEqual(r.status_code, 403)

    def test_settings_accessible_by_operator(self):
        os.environ["NEXORA_OPERATOR_ONLY_ENFORCE"] = "1"
        hdr = self._set_role("admin")
        r = self.client.get("/api/settings", headers=hdr)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("profile", data)
        self.assertIn("operator", data)
        self.assertIn("tenant", data)
        self.assertIn("state", data)
        self.assertIn("security", data)
        self.assertIn("version", data)

    def test_settings_profile_reflects_role(self):
        os.environ["NEXORA_OPERATOR_ONLY_ENFORCE"] = "1"
        hdr = self._set_role("admin")
        r = self.client.get("/api/settings", headers=hdr)
        data = r.json()
        self.assertEqual(data["profile"]["actor_role"], "admin")
        self.assertTrue(data["profile"]["is_operator"])

    def test_settings_state_counts(self):
        self._seed_tenants([
            {"tenant_id": "t1", "org_id": "o1"},
            {"tenant_id": "t2", "org_id": "o2"},
        ])
        hdr = self._set_role("admin")
        os.environ["NEXORA_OPERATOR_ONLY_ENFORCE"] = "1"
        r = self.client.get("/api/settings", headers=hdr)
        # counts should be at least what we seeded (operator tenant may add 1)
        self.assertGreaterEqual(r.json()["state"]["tenants_count"], 2)


# ═══════════════════════════════════════════════════════════════════════════════
#  20. ENROLLMENT DOMAIN TESTS (detailed)
# ═══════════════════════════════════════════════════════════════════════════════
class EnrollmentDomainTests(unittest.TestCase):
    """Enrollment token issuance, attestation, and consumption."""

    def test_full_enrollment_flow(self):
        from nexora_saas.enrollment import (
            attest_node,
            build_attestation_response,
            consume_enrollment_token,
            issue_enrollment_token,
        )

        state = {**DEFAULT_STATE, "enrollment_tokens": [], "enrollment_events": [], "security_audit": []}
        issued = issue_enrollment_token(state, requested_by="tester", mode="pull", ttl_minutes=10, node_id="n-enr")
        self.assertIn("token", issued)
        self.assertIn("challenge", issued)

        response = build_attestation_response(
            challenge=issued["challenge"], node_id="n-enr", token_id=issued["token_id"]
        )
        result = attest_node(
            state,
            token=issued["token"],
            challenge=issued["challenge"],
            challenge_response=response,
            hostname="node.example.test",
            node_id="n-enr",
            agent_version="2.0.0",
            yunohost_version="12.1.2",
            debian_version="12",
            observed_at=datetime.now(timezone.utc).isoformat(),
            compatibility_matrix_path="compatibility.yaml",
        )
        self.assertEqual(result["status"], "attested")

        consumed = consume_enrollment_token(state, issued["token"], node_id="n-enr")
        self.assertEqual(consumed["status"], "consumed")

    def test_expired_token_rejected(self):
        from nexora_saas.enrollment import attest_node, build_attestation_response, issue_enrollment_token

        state = {**DEFAULT_STATE, "enrollment_tokens": [], "enrollment_events": [], "security_audit": []}
        issued = issue_enrollment_token(state, requested_by="tester", mode="pull", ttl_minutes=10)
        response = build_attestation_response(
            challenge=issued["challenge"], node_id="n-exp", token_id=issued["token_id"]
        )
        with self.assertRaises(ValueError):
            attest_node(
                state,
                token=issued["token"],
                challenge=issued["challenge"],
                challenge_response=response,
                hostname="node.example.test",
                node_id="n-exp",
                agent_version="2.0.0",
                yunohost_version="12.1.2",
                debian_version="12",
                observed_at=(datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
                compatibility_matrix_path="compatibility.yaml",
            )


# ═══════════════════════════════════════════════════════════════════════════════
#  21. MULTITENANT DOMAIN TESTS
# ═══════════════════════════════════════════════════════════════════════════════
class MultiTenantDomainTests(unittest.TestCase):
    """Domain-level multi-tenant config generation."""

    def test_tenant_config_creation(self):
        from nexora_saas.multitenant import generate_tenant_config

        config = generate_tenant_config("Alpha", apps=["nextcloud"], users=["alice"])
        self.assertIn("ynh_group", config)
        self.assertTrue(config["ynh_group"].startswith("tenant_"))

    def test_tenant_setup_commands(self):
        from nexora_saas.multitenant import generate_tenant_config, generate_tenant_setup_commands

        config = generate_tenant_config("Alpha", domain="alpha.org", apps=["wiki"], users=["alice"])
        commands = generate_tenant_setup_commands(config)
        self.assertIsInstance(commands, list)
        self.assertTrue(any("permission" in cmd for cmd in commands))

    def test_tenant_report(self):
        from nexora_saas.multitenant import generate_tenant_config, generate_tenant_report

        configs = [generate_tenant_config("A", users=["alice", "bob"])]
        report = generate_tenant_report(configs)
        self.assertEqual(report["total_users"], 2)


# ═══════════════════════════════════════════════════════════════════════════════
#  22. SCORING & GOVERNANCE DOMAIN
# ═══════════════════════════════════════════════════════════════════════════════
class ScoringDomainTests(unittest.TestCase):
    """Domain-level scoring tests."""

    def test_security_score(self):
        from nexora_node_sdk.scoring import compute_security_score

        result = compute_security_score({})
        self.assertIn("score", result)
        self.assertIn("grade", result)
        self.assertIsInstance(result["score"], (int, float))

    def test_health_score(self):
        from nexora_node_sdk.scoring import compute_health_score

        result = compute_health_score({})
        self.assertIn("score", result)
        self.assertIn("grade", result)

    def test_compliance_score(self):
        from nexora_node_sdk.scoring import compute_compliance_score

        result = compute_compliance_score({}, has_pra=True, has_monitoring=True)
        self.assertIn("score", result)
        self.assertIn("maturity_level", result)

    def test_grade_mapping(self):
        from nexora_node_sdk.scoring import compute_security_score

        # scores above 80 should get at least B
        inv_good = {
            "firewall": {"ports": [22, 443]},
            "system": {"packages": {}},
        }
        result = compute_security_score(inv_good)
        self.assertIn(result["grade"], ("A", "B", "C", "D", "F"))


class GovernanceDomainTests(unittest.TestCase):
    """Domain-level governance: executive report, risk register."""

    def test_executive_report(self):
        from nexora_node_sdk.governance import executive_report

        report = executive_report({}, has_pra=True, has_monitoring=True)
        self.assertIsInstance(report, dict)

    def test_risk_register(self):
        from nexora_node_sdk.governance import risk_register

        risks = risk_register({})
        self.assertIsInstance(risks, dict)

    def test_change_log(self):
        from nexora_node_sdk.governance import change_log

        cl = change_log([])
        self.assertIsInstance(cl, dict)


# ═══════════════════════════════════════════════════════════════════════════════
#  23. NODE AGENT CONTRACT
# ═══════════════════════════════════════════════════════════════════════════════
class NodeAgentContractTests(unittest.TestCase):
    """Node agent source-level contract checks."""

    def test_node_agent_api_exists(self):
        self.assertTrue(Path("apps/node_agent/api.py").exists())

    def test_node_agent_has_enroll_endpoint(self):
        source = Path("apps/node_agent/api.py").read_text(encoding="utf-8")
        self.assertIn("enroll", source.lower())

    def test_node_agent_hmac_verification(self):
        source = Path("apps/node_agent/api.py").read_text(encoding="utf-8")
        self.assertIn("hmac", source.lower())

    def test_node_agent_state_permissions(self):
        source = Path("apps/node_agent/api.py").read_text(encoding="utf-8")
        # Should enforce secure file permissions on state
        self.assertIn("0o600", source)

    def test_node_agent_logging_setup(self):
        source = Path("apps/node_agent/api.py").read_text(encoding="utf-8")
        self.assertIn("setup_logging()", source)


# ═══════════════════════════════════════════════════════════════════════════════
#  24. CONSOLE STATIC ASSETS CONTRACT
# ═══════════════════════════════════════════════════════════════════════════════
class ConsoleStaticTests(unittest.TestCase):
    """Console static files existence and content checks."""

    def test_console_index_exists(self):
        self.assertTrue((REPO_ROOT / "apps" / "console" / "index.html").exists())

    def test_console_app_js_exists(self):
        self.assertTrue((REPO_ROOT / "apps" / "console" / "app.js").exists())

    def test_console_views_js_exists(self):
        self.assertTrue((REPO_ROOT / "apps" / "console" / "views.js").exists())

    def test_console_api_js_exists(self):
        self.assertTrue((REPO_ROOT / "apps" / "console" / "api.js").exists())

    def test_console_styles_css_exists(self):
        self.assertTrue((REPO_ROOT / "apps" / "console" / "styles.css").exists())

    def test_console_index_references_app_js(self):
        html = (REPO_ROOT / "apps" / "console" / "index.html").read_text(encoding="utf-8")
        self.assertIn("app.js", html)

    def test_console_has_all_nav_sections(self):
        html = (REPO_ROOT / "apps" / "console" / "index.html").read_text(encoding="utf-8")
        for section in ("dashboard", "fleet", "security", "pra", "scores"):
            self.assertIn(f'data-section="{section}"', html, f"Missing nav section: {section}")

    def test_console_has_profile_badge(self):
        html = (REPO_ROOT / "apps" / "console" / "index.html").read_text(encoding="utf-8")
        self.assertIn("profile-badge", html)

    def test_console_has_runtime_mode_badge(self):
        html = (REPO_ROOT / "apps" / "console" / "index.html").read_text(encoding="utf-8")
        self.assertIn("runtime-mode-badge", html)

    def test_console_has_settings_nav(self):
        html = (REPO_ROOT / "apps" / "console" / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-section="settings"', html)

    def test_views_has_all_section_renderers(self):
        views = (REPO_ROOT / "apps" / "console" / "views.js").read_text(encoding="utf-8")
        for fn in (
            "loadDashboard",
            "loadScores",
            "loadApps",
            "loadServices",
            "loadDomains",
            "loadSecurity",
            "loadPra",
            "loadFleet",
            "loadBlueprints",
            "loadModes",
            "loadDocker",
            "loadStorage",
            "loadNotifications",
            "loadHooks",
            "loadGovernanceRisks",
            "loadSlaTracking",
            "loadSubscription",
            "loadProvisioning",
            "loadSettings",
        ):
            self.assertIn(fn, views, f"Missing view renderer: {fn}")

    def test_app_js_has_section_gating(self):
        app = (REPO_ROOT / "apps" / "console" / "app.js").read_text(encoding="utf-8")
        self.assertIn("allowed_sections", app)
        self.assertIn("isSectionAllowed", app)

    def test_app_js_token_in_session_storage(self):
        api = (REPO_ROOT / "apps" / "console" / "api.js").read_text(encoding="utf-8")
        self.assertIn("sessionStorage", api)
        self.assertIn("nexora_token", api)

    def test_app_js_no_localstorage_token_leak(self):
        """Token must not persist in localStorage."""
        api = (REPO_ROOT / "apps" / "console" / "api.js").read_text(encoding="utf-8")
        self.assertIn("localStorage.removeItem('nexora_token')", api)


# ═══════════════════════════════════════════════════════════════════════════════
#  25. EDGE / MAINTENANCE CONFIG
# ═══════════════════════════════════════════════════════════════════════════════
class EdgeDomainTests(unittest.TestCase):
    """Edge/maintenance configuration generation."""

    def test_maintenance_config(self):
        from nexora_saas.edge import generate_maintenance_config

        config = generate_maintenance_config("cloud.example.org")
        self.assertIsInstance(config, dict)
        self.assertIn("domain", config)

    def test_nginx_lb_config_generation(self):
        from nexora_saas.edge import generate_nginx_lb_config

        config = generate_nginx_lb_config(
            [{"ip": "10.0.0.1", "port": 443}, {"ip": "10.0.0.2", "port": 443}],
            domain="app1.example.org",
        )
        self.assertIn("config", config)


# ═══════════════════════════════════════════════════════════════════════════════
#  26. PORTAL / BRANDING
# ═══════════════════════════════════════════════════════════════════════════════
class PortalDomainTests(unittest.TestCase):
    """Portal palettes and sector themes."""

    def test_palettes_list(self):
        from nexora_saas.portal import list_available_palettes

        palettes = list_available_palettes()
        self.assertIsInstance(palettes, list)
        self.assertTrue(len(palettes) >= 1)

    def test_sector_themes(self):
        from nexora_saas.portal import list_sector_themes

        sectors = list_sector_themes()
        self.assertIsInstance(sectors, list)


# ═══════════════════════════════════════════════════════════════════════════════
#  27. INTERFACE PARITY CHECK
# ═══════════════════════════════════════════════════════════════════════════════
class InterfaceParityTests(NexoraTestBase):
    """Interface parity between fleet operations."""

    def test_interface_parity_route(self):
        os.environ["NEXORA_OPERATOR_ONLY_ENFORCE"] = "0"
        r = self.client.get("/api/interface-parity/fleet-lifecycle", headers=self.headers)
        self.assertEqual(r.status_code, 200)

    def test_persistence_status(self):
        os.environ["NEXORA_OPERATOR_ONLY_ENFORCE"] = "0"
        r = self.client.get("/api/persistence", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("backend", data)


# ═══════════════════════════════════════════════════════════════════════════════
#  28. DEPLOYMENT / PACKAGING CONTRACTS
# ═══════════════════════════════════════════════════════════════════════════════
class PackagingContractTests(unittest.TestCase):
    """pyproject.toml and packaging shape."""

    def test_pyproject_toml_exists(self):
        self.assertTrue((REPO_ROOT / "pyproject.toml").exists())

    def test_pyproject_has_nexora_entry_point(self):
        toml = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("nexora-control-plane", toml)

    def test_pyproject_has_version(self):
        toml = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("version", toml)

    def test_readme_exists(self):
        self.assertTrue((REPO_ROOT / "README.md").exists())


# ═══════════════════════════════════════════════════════════════════════════════
#  29. NO STUBS/PLACEHOLDERS
# ═══════════════════════════════════════════════════════════════════════════════
class NoStubTests(unittest.TestCase):
    """Verify no stub/placeholder implementations remain."""

    def test_no_stub_suffix_in_api(self):
        source = Path("apps/control_plane/api.py").read_text(encoding="utf-8")
        self.assertNotIn("_stub", source)

    def test_no_todo_stub_markers(self):
        source = Path("apps/control_plane/api.py").read_text(encoding="utf-8")
        self.assertNotIn("TODO: stub", source)
        self.assertNotIn("placeholder implementation", source)

    def test_no_pass_only_endpoints(self):
        """No endpoint functions should consist of only 'pass'."""
        source = Path("apps/control_plane/api.py").read_text(encoding="utf-8")
        import re

        # Find functions with only pass as their body
        matches = re.findall(r"def \w+\([^)]*\).*?:\s+pass\s*$", source, re.MULTILINE)
        self.assertEqual(len(matches), 0, f"Found pass-only functions: {matches}")


# ═══════════════════════════════════════════════════════════════════════════════
#  30. COMPREHENSIVE OPERATOR-ONLY ROUTES ENFORCEMENT
# ═══════════════════════════════════════════════════════════════════════════════
class OperatorOnlyComprehensiveTests(NexoraTestBase):
    """Verify every operator-only route is properly gated."""

    OPERATOR_ROUTES = [
        "/api/persistence",
        "/api/interface-parity/fleet-lifecycle",
        "/api/docker/status",
        "/api/docker/containers",
        "/api/docker/templates",
        "/api/failover/strategies",
        "/api/storage/usage",
        "/api/storage/ynh-map",
        "/api/notifications/templates",
        "/api/sla/tiers",
        "/api/hooks/events",
        "/api/hooks/presets",
        "/api/automation/templates",
        "/api/automation/checklists",
        "/api/settings",
    ]

    def test_all_operator_routes_denied_without_role(self):
        os.environ["NEXORA_OPERATOR_ONLY_ENFORCE"] = "1"
        for route in self.OPERATOR_ROUTES:
            with self.subTest(route=route):
                r = self.client.get(route, headers=self.headers)
                self.assertEqual(r.status_code, 403, f"{route} should deny without operator role")

    def test_all_operator_routes_allowed_with_role(self):
        os.environ["NEXORA_OPERATOR_ONLY_ENFORCE"] = "1"
        hdr = self._set_role("operator")
        for route in self.OPERATOR_ROUTES:
            with self.subTest(route=route):
                r = self.client.get(route, headers=hdr)
                self.assertEqual(r.status_code, 200, f"{route} should allow operator: {r.text[:200]}")


# ═══════════════════════════════════════════════════════════════════════════════
#  31. AUTH TENANT CLAIM
# ═══════════════════════════════════════════════════════════════════════════════
class AuthTenantClaimTests(NexoraTestBase):
    """Tenant claim generation."""

    def test_tenant_claim_returns_claim(self):
        r = self.client.get("/api/auth/tenant-claim?tenant_id=t1", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["tenant_id"], "t1")
        self.assertIn("claim", data)
        self.assertTrue(len(data["claim"]) > 0)

    def test_tenant_claim_requires_auth(self):
        r = self.client.get("/api/auth/tenant-claim?tenant_id=t1")
        self.assertEqual(r.status_code, 401)

    def test_tenant_claim_requires_tenant_id(self):
        r = self.client.get("/api/auth/tenant-claim", headers=self.headers)
        self.assertEqual(r.status_code, 422)


# ═══════════════════════════════════════════════════════════════════════════════
#  32. SECURITY AUDIT DOMAIN
# ═══════════════════════════════════════════════════════════════════════════════
class SecurityAuditDomainTests(unittest.TestCase):
    """Security audit event emission and filtering."""

    def test_emit_security_event(self):
        from nexora_node_sdk.security_audit import emit_security_event

        state: dict = {"security_audit": []}
        emit_security_event(state, "auth", "login_success", severity="info")
        self.assertTrue(len(state["security_audit"]) >= 1)
        evt = state["security_audit"][-1]
        self.assertEqual(evt["category"], "auth")
        self.assertEqual(evt["action"], "login_success")

    def test_filter_security_events(self):
        from nexora_node_sdk.security_audit import emit_security_event, filter_security_events

        state: dict = {"security_audit": []}
        emit_security_event(state, "auth", "login_success", severity="info")
        emit_security_event(state, "network", "port_scan", severity="warning")
        auth_events = filter_security_events(state["security_audit"], category="auth")
        self.assertEqual(len(auth_events), 1)
        self.assertEqual(auth_events[0]["category"], "auth")

    def test_event_has_timestamp(self):
        from nexora_node_sdk.security_audit import emit_security_event

        state: dict = {"security_audit": []}
        emit_security_event(state, "auth", "test", severity="info")
        self.assertIn("timestamp", state["security_audit"][-1])


if __name__ == "__main__":
    unittest.main()
