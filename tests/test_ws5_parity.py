"""WS5 — REST / MCP / Console Convergence parity tests."""

from __future__ import annotations

import unittest

from nexora_node_sdk.surface_registry import SurfaceRegistry
from nexora_saas.interface_parity import (
    ALL_PARITY_DEFINITIONS,
    fleet_lifecycle_parity_payload,
    full_parity_payload,
    governance_parity_payload,
    mode_management_parity_payload,
    security_audit_parity_payload,
)


class SurfaceRegistryLoadTests(unittest.TestCase):
    """SurfaceRegistry loads all capabilities from YAML."""

    def setUp(self):
        self.registry = SurfaceRegistry()

    def test_loads_all_capabilities(self):
        caps = self.registry.list_all()
        self.assertGreaterEqual(len(caps), 15, "Expected at least 15 capabilities in catalog")

    def test_every_capability_has_id_and_domain(self):
        for cap in self.registry.list_all():
            self.assertIn("id", cap, f"Capability missing 'id': {cap}")
            self.assertIn("domain", cap, f"Capability missing 'domain': {cap}")

    def test_every_capability_has_surfaces_dict(self):
        for cap in self.registry.list_all():
            surfaces = cap.get("surfaces")
            self.assertIsInstance(surfaces, dict, f"Capability {cap.get('id')} has no surfaces dict")

    def test_every_capability_has_at_least_one_surface(self):
        for cap in self.registry.list_all():
            cap_id = cap.get("id", "unknown")
            surfaces = cap.get("surfaces", {})
            has_any = any(
                isinstance(surfaces.get(s), list) and len(surfaces.get(s)) > 0
                for s in ("rest", "mcp", "console", "node")
            )
            self.assertTrue(has_any, f"Capability {cap_id} has no surface entries at all")

    def test_get_capability_by_id(self):
        cap = self.registry.get_capability("fleet.lifecycle")
        self.assertIsNotNone(cap)
        self.assertEqual(cap["domain"], "fleet")

    def test_get_capability_unknown_returns_none(self):
        self.assertIsNone(self.registry.get_capability("nonexistent.capability"))


class SurfaceRegistryListBySurfaceTests(unittest.TestCase):
    """list_by_surface returns correct subsets."""

    def setUp(self):
        self.registry = SurfaceRegistry()

    def test_rest_surface_returns_capabilities(self):
        rest_caps = self.registry.list_by_surface("rest")
        self.assertGreaterEqual(len(rest_caps), 10, "Expected many capabilities on REST surface")

    def test_mcp_surface_returns_capabilities(self):
        mcp_caps = self.registry.list_by_surface("mcp")
        self.assertGreaterEqual(len(mcp_caps), 10, "Expected many capabilities on MCP surface")

    def test_console_surface_returns_capabilities(self):
        console_caps = self.registry.list_by_surface("console")
        self.assertGreaterEqual(len(console_caps), 5, "Expected some capabilities on Console surface")

    def test_unknown_surface_returns_empty(self):
        caps = self.registry.list_by_surface("graphql")
        self.assertEqual(len(caps), 0)

    def test_rest_includes_fleet_enrollment(self):
        rest_ids = {c["id"] for c in self.registry.list_by_surface("rest")}
        self.assertIn("fleet.enrollment", rest_ids)

    def test_mcp_includes_governance_scoring(self):
        mcp_ids = {c["id"] for c in self.registry.list_by_surface("mcp")}
        self.assertIn("governance.scoring", mcp_ids)


class ParityReportTests(unittest.TestCase):
    """Parity report identifies known gaps."""

    def setUp(self):
        self.registry = SurfaceRegistry()
        self.report = self.registry.parity_report()

    def test_report_has_expected_keys(self):
        self.assertIn("full_parity", self.report)
        self.assertIn("gaps", self.report)
        self.assertIn("total_capabilities", self.report)

    def test_full_parity_plus_gaps_equals_total(self):
        total = self.report["total_capabilities"]
        full = self.report["full_parity_count"]
        gap_count = self.report["gaps_count"]
        self.assertEqual(full + gap_count, total)

    def test_known_full_parity_capabilities(self):
        """Capabilities known to have all 3 surfaces should appear in full_parity."""
        full = set(self.report["full_parity"])
        for cap_id in ("inventory.observe", "fleet.enrollment", "fleet.lifecycle",
                        "governance.scoring", "mode.management", "pra.management",
                        "security.posture", "branding.apply", "automation.catalog"):
            self.assertIn(cap_id, full, f"{cap_id} expected in full parity")

    def test_known_gaps_exist(self):
        """Capabilities known to lack console should appear in gaps."""
        gap_ids = {g["id"] for g in self.report["gaps"]}
        for cap_id in ("governance.risks", "docker.management", "sla.tracking",
                        "notifications.routing", "storage.analysis", "hooks.management"):
            self.assertIn(cap_id, gap_ids, f"{cap_id} expected in gaps")

    def test_gap_entries_have_missing_field(self):
        for gap in self.report["gaps"]:
            self.assertIn("missing", gap)
            self.assertIsInstance(gap["missing"], list)
            self.assertGreater(len(gap["missing"]), 0)


class CoverageScoreTests(unittest.TestCase):
    """Coverage score computation."""

    def setUp(self):
        self.registry = SurfaceRegistry()

    def test_coverage_score_is_percentage(self):
        score = self.registry.coverage_score()
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 100.0)

    def test_coverage_score_is_nonzero(self):
        score = self.registry.coverage_score()
        self.assertGreater(score, 0.0, "Expected some capabilities to have full parity")

    def test_coverage_score_is_not_100(self):
        score = self.registry.coverage_score()
        self.assertLess(score, 100.0, "Expected some gaps — not all capabilities have all 3 surfaces")


class FleetLifecycleParityTests(unittest.TestCase):
    """Fleet lifecycle parity has matching REST and MCP entries."""

    def test_payload_structure(self):
        payload = fleet_lifecycle_parity_payload()
        self.assertEqual(payload["surface"], "fleet-lifecycle")
        self.assertIn("capabilities", payload)
        self.assertIn("summary", payload)

    def test_has_enrollment_entries(self):
        payload = fleet_lifecycle_parity_payload()
        cap_names = {e["capability"] for e in payload["capabilities"]}
        self.assertIn("fleet.enrollment-request", cap_names)
        self.assertIn("fleet.enrollment-attest", cap_names)
        self.assertIn("fleet.enrollment-register", cap_names)

    def test_every_entry_has_rest_and_mcp(self):
        payload = fleet_lifecycle_parity_payload()
        for entry in payload["capabilities"]:
            self.assertIn("rest", entry, f"{entry['capability']} missing rest key")
            self.assertIn("mcp", entry, f"{entry['capability']} missing mcp key")

    def test_fleet_lifecycle_action_has_all_rest_routes(self):
        payload = fleet_lifecycle_parity_payload()
        actions = next(
            e for e in payload["capabilities"]
            if e["capability"] == "fleet.lifecycle-action"
        )
        expected_actions = ["drain", "cordon", "uncordon", "revoke", "retire",
                            "rotate-credentials", "re-enroll", "delete"]
        for action in expected_actions:
            self.assertTrue(
                any(action in r for r in actions["rest"]),
                f"Missing REST route for action '{action}'",
            )

    def test_rest_and_mcp_counts_in_summary(self):
        payload = fleet_lifecycle_parity_payload()
        self.assertGreaterEqual(payload["summary"]["rest_entry_count"], 10)
        self.assertGreaterEqual(payload["summary"]["mcp_entry_count"], 5)


class GovernanceParityTests(unittest.TestCase):
    """Governance parity definitions."""

    def test_payload_structure(self):
        payload = governance_parity_payload()
        self.assertEqual(payload["surface"], "governance")

    def test_has_risk_register(self):
        payload = governance_parity_payload()
        caps = {e["capability"] for e in payload["capabilities"]}
        self.assertIn("governance.risk-register", caps)

    def test_identifies_changelog_endpoint(self):
        payload = governance_parity_payload()
        changelog = next(
            e for e in payload["capabilities"]
            if e["capability"] == "governance.change-log"
        )
        self.assertIn("GET /api/governance/changelog", changelog["rest"])
        self.assertNotIn("gap", changelog)


class ModeManagementParityTests(unittest.TestCase):
    """Mode management parity definitions."""

    def test_payload_structure(self):
        payload = mode_management_parity_payload()
        self.assertEqual(payload["surface"], "mode-management")
        self.assertGreaterEqual(payload["summary"]["capability_count"], 5)

    def test_all_entries_have_rest_and_mcp(self):
        payload = mode_management_parity_payload()
        for entry in payload["capabilities"]:
            self.assertTrue(len(entry["rest"]) > 0, f"{entry['capability']} has no REST")
            self.assertTrue(len(entry["mcp"]) > 0, f"{entry['capability']} has no MCP")


class SecurityAuditParityTests(unittest.TestCase):
    """Security/audit parity definitions."""

    def test_payload_structure(self):
        payload = security_audit_parity_payload()
        self.assertEqual(payload["surface"], "security-audit")

    def test_verifies_no_gaps(self):
        payload = security_audit_parity_payload()
        self.assertEqual(payload["summary"]["gap_count"], 0)


class FullParityPayloadTests(unittest.TestCase):
    """Combined parity payload covers all surfaces."""

    def test_full_parity_has_all_surfaces(self):
        payload = full_parity_payload()
        surface_names = {s["surface"] for s in payload["surfaces"]}
        self.assertIn("fleet-lifecycle", surface_names)
        self.assertIn("governance", surface_names)
        self.assertIn("mode-management", surface_names)
        self.assertIn("node-actions", surface_names)
        self.assertIn("security-audit", surface_names)

    def test_full_parity_summary(self):
        payload = full_parity_payload()
        self.assertEqual(payload["summary"]["surface_count"], 5)
        self.assertGreater(payload["summary"]["total_capabilities"], 30)


class AllParityDefinitionsTests(unittest.TestCase):
    """Structural validation of ALL_PARITY_DEFINITIONS."""

    def test_all_definitions_have_required_keys(self):
        for defn in ALL_PARITY_DEFINITIONS:
            self.assertIn("surface", defn)
            self.assertIn("scope", defn)
            self.assertIn("entries", defn)
            self.assertIsInstance(defn["entries"], list)
            self.assertGreater(len(defn["entries"]), 0)


if __name__ == "__main__":
    unittest.main()
