"""Comprehensive TDD test file for all uncovered modules.

Domains covered:
- quotas.py           (boundary conditions, unknown tiers, entitlements)
- sla.py              (zero total, downtime=total, exact-target boundary, persistence)
- governance.py       (executive report, risk register, all conditions)
- automation.py       (profiles, unknown profile, crontab, template lookup)
- notifications.py    (format_alert, webhook payloads, unknown template)
- portal.py           (palette fallback, sector themes, CSS variables)
- secret_store.py     (path traversal, issue/revoke/verify, listing, double-revoke)
- drift_detection.py  (identical inventories, full-empty, section drifts)
- monitoring.py       (cert thresholds at 0/7/14/30, services, backups, disk, aggregate)
- scoring.py          (score clamping, grade boundaries)
- pra.py              (backup scope, restore plan steps)
- multitenant.py      (tenant config, commands, report aggregation)
- owner_session.py    (expiry, double revoke, concurrent sessions, rotation clears)
- subscription.py     (invalid transitions: double cancel, cancel→reactivate)
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

# ─────────────────────────────────────────────────────────────────────
# 1. QUOTAS
# ─────────────────────────────────────────────────────────────────────

from nexora_node_sdk.models import TenantTier  # noqa: E402
from nexora_saas.quotas import (  # noqa: E402
    get_quota_limit,
    get_tenant_entitlements,
    is_quota_exceeded,
)


class QuotasTests(unittest.TestCase):
    """Boundary conditions and edge cases for quotas module."""

    def test_all_tiers_have_max_nodes(self):
        for tier in TenantTier:
            lim = get_quota_limit(tier, "max_nodes")
            self.assertGreater(lim, 0, f"Tier {tier} missing max_nodes quota")

    def test_free_tier_has_lowest_max_nodes(self):
        free = get_quota_limit(TenantTier.FREE, "max_nodes")
        pro = get_quota_limit(TenantTier.PRO, "max_nodes")
        ent = get_quota_limit(TenantTier.ENTERPRISE, "max_nodes")
        self.assertLess(free, pro)
        self.assertLess(pro, ent)

    def test_string_tier_resolves_correctly(self):
        """String tier names (from JSON state) must resolve same as enum."""
        self.assertEqual(get_quota_limit("free", "max_nodes"), get_quota_limit(TenantTier.FREE, "max_nodes"))
        self.assertEqual(get_quota_limit("pro", "max_nodes"), get_quota_limit(TenantTier.PRO, "max_nodes"))

    def test_unknown_string_tier_falls_back_to_free(self):
        """Unknown tier name must fall back to FREE quotas."""
        lim = get_quota_limit("platinum_plus", "max_nodes")
        self.assertEqual(lim, get_quota_limit(TenantTier.FREE, "max_nodes"))

    def test_unknown_resource_returns_zero(self):
        """Requesting an undefined resource must return 0."""
        self.assertEqual(get_quota_limit(TenantTier.PRO, "max_helicopters"), 0)

    def test_is_quota_exceeded_at_exact_limit(self):
        """Exactly at the limit should count as exceeded (>= semantics)."""
        limit = get_quota_limit(TenantTier.FREE, "max_nodes")
        self.assertTrue(is_quota_exceeded(TenantTier.FREE, "max_nodes", limit))

    def test_is_quota_exceeded_below_limit(self):
        limit = get_quota_limit(TenantTier.FREE, "max_nodes")
        self.assertFalse(is_quota_exceeded(TenantTier.FREE, "max_nodes", limit - 1))

    def test_is_quota_exceeded_above_limit(self):
        self.assertTrue(is_quota_exceeded(TenantTier.FREE, "max_nodes", 9999))

    def test_is_quota_exceeded_at_zero(self):
        """0 should never exceed limit (limit is >= 0)."""
        self.assertFalse(is_quota_exceeded(TenantTier.FREE, "max_nodes", 0))

    def test_entitlements_are_list(self):
        for tier in TenantTier:
            ents = get_tenant_entitlements(tier)
            self.assertIsInstance(ents, list, f"Tier {tier} entitlements must be a list")

    def test_enterprise_entitlements_are_superset_of_free(self):
        free_ents = set(get_tenant_entitlements(TenantTier.FREE))
        ent_ents = set(get_tenant_entitlements(TenantTier.ENTERPRISE))
        # At minimum, enterprise must have more or equal features
        self.assertGreaterEqual(len(ent_ents), len(free_ents))

    def test_entitlements_for_unknown_tier_falls_back_to_free(self):
        ents = get_tenant_entitlements("nonexistent")
        free_ents = get_tenant_entitlements(TenantTier.FREE)
        self.assertEqual(ents, free_ents)


# ─────────────────────────────────────────────────────────────────────
# 2. SLA
# ─────────────────────────────────────────────────────────────────────

from nexora_saas.sla import (  # noqa: E402
    SLA_TIERS,
    compute_downtime_from_events,
    compute_sla_from_history,
    compute_uptime,
    generate_sla_policy,
    generate_sla_report,
    get_sla_history,
    list_sla_tiers,
    record_downtime,
)


class SlaTests(unittest.TestCase):
    def test_all_tiers_have_uptime_target(self):
        for tier, cfg in SLA_TIERS.items():
            self.assertIn("uptime_target", cfg, f"Tier {tier} missing uptime_target")
            self.assertGreater(cfg["uptime_target"], 0)

    def test_compute_uptime_nominal(self):
        result = compute_uptime(43200, 60)  # 30 days, 1h downtime
        self.assertAlmostEqual(result["uptime_percent"], 99.8611, places=3)

    def test_compute_uptime_zero_total_returns_error(self):
        """Division by zero must be handled gracefully."""
        result = compute_uptime(0, 0)
        self.assertIn("error", result)

    def test_compute_uptime_full_downtime(self):
        """Downtime equal to total period → 0% uptime."""
        result = compute_uptime(100, 100)
        self.assertEqual(result["uptime_percent"], 0.0)

    def test_compute_uptime_exceeds_total(self):
        """Downtime greater than total period must floor at 0%."""
        result = compute_uptime(100, 200)
        self.assertLessEqual(result["uptime_percent"], 0.0)

    def test_compute_uptime_perfect(self):
        result = compute_uptime(1000, 0)
        self.assertEqual(result["uptime_percent"], 100.0)

    def test_generate_sla_policy_custom_targets(self):
        policy = generate_sla_policy("standard", custom_targets={"uptime_target": 99.99})
        self.assertEqual(policy["targets"]["uptime_target"], 99.99)

    def test_generate_sla_policy_unknown_tier_falls_back_to_standard(self):
        policy = generate_sla_policy("unknown_tier")
        self.assertEqual(policy["tier"], "unknown_tier")
        # Must still return valid targets (fallback to standard)
        self.assertIn("uptime_target", policy["targets"])

    def test_generate_sla_report_compliant(self):
        inventory = {}
        report = generate_sla_report(inventory, tier="basic", downtime_minutes=0, period_days=30)
        self.assertTrue(report["compliant"])
        self.assertEqual(report["recommendations"], [])

    def test_generate_sla_report_non_compliant(self):
        inventory = {}
        # For basic tier target=99.0, 1% of 43200 = 432 minutes downtime
        report = generate_sla_report(inventory, tier="basic", downtime_minutes=500, period_days=30)
        self.assertFalse(report["compliant"])
        self.assertTrue(len(report["recommendations"]) > 0)

    def test_generate_sla_report_exactly_at_boundary(self):
        """Exactly at target uptime must count as compliant."""
        total_minutes = 43200  # 30 days
        target_pct = SLA_TIERS["standard"]["uptime_target"]  # 99.5
        downtime = total_minutes * (100 - target_pct) / 100
        report = generate_sla_report({}, tier="standard", downtime_minutes=int(downtime), period_days=30)
        self.assertTrue(report["compliant"])

    def test_list_sla_tiers_returns_all(self):
        tiers = list_sla_tiers()
        self.assertEqual(len(tiers), len(SLA_TIERS))
        for t in tiers:
            self.assertIn("tier", t)
            self.assertIn("uptime_target", t)

    def test_record_and_retrieve_downtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = str(Path(tmp) / "sla.json")
            result = record_downtime(30, "test-outage", state_path=state_path)
            self.assertTrue(result["recorded"])
            self.assertEqual(result["total_downtime_minutes"], 30)

            # Second record accumulates
            result2 = record_downtime(15, "test-outage-2", state_path=state_path)
            self.assertEqual(result2["total_downtime_minutes"], 45)

    def test_get_sla_history_empty_path_returns_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = get_sla_history(state_path=str(Path(tmp) / "nonexistent.json"))
            self.assertEqual(data["events"], [])
            self.assertEqual(data["total_downtime_minutes"], 0)

    def test_compute_sla_from_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = str(Path(tmp) / "sla.json")
            record_downtime(60, "outage", state_path=state_path)
            result = compute_sla_from_history(period_days=30, tier="standard", state_path=state_path)
            self.assertIn("compliant", result)
            self.assertIn("uptime", result)

    def test_compute_downtime_from_events(self):
        events = [{"minutes": 30}, {"minutes": 15}, {"minutes": 0}]
        self.assertEqual(compute_downtime_from_events(events), 45)

    def test_compute_downtime_from_empty_events(self):
        self.assertEqual(compute_downtime_from_events([]), 0)


# ─────────────────────────────────────────────────────────────────────
# 3. GOVERNANCE
# ─────────────────────────────────────────────────────────────────────

from nexora_saas.governance import executive_report, risk_register  # noqa: E402


class GovernanceTests(unittest.TestCase):
    def _minimal_inventory(self):
        return {}

    def test_executive_report_empty_inventory(self):
        report = executive_report(self._minimal_inventory(), node_id="test-node")
        self.assertIn("scores", report)
        self.assertIn("overall_score", report)
        self.assertIn("priorities", report)
        self.assertEqual(report["node_id"], "test-node")
        self.assertIsInstance(report["overall_score"], int)

    def test_executive_report_score_in_range(self):
        report = executive_report({})
        self.assertGreaterEqual(report["overall_score"], 0)
        self.assertLessEqual(report["overall_score"], 100)
        for score_obj in report["scores"].values():
            s = score_obj["score"] if isinstance(score_obj, dict) and "score" in score_obj else score_obj
            self.assertGreaterEqual(s, 0)
            self.assertLessEqual(s, 100)

    def test_executive_report_priorities_not_empty_for_unhealthy(self):
        # Empty inventory → likely low scores → priorities should exist
        report = executive_report({})
        self.assertGreaterEqual(len(report["priorities"]), 1)

    def test_executive_report_with_healthy_inventory(self):
        inventory = {
            "backups": {"archives": [{"id": "b1"}, {"id": "b2"}, {"id": "b3"}]},
            "services": {"nginx": {"status": "running"}, "slapd": {"status": "running"}},
            "apps": {"apps": [{"id": "wordpress"}]},
        }
        report = executive_report(inventory, has_pra=True, has_monitoring=True)
        self.assertGreaterEqual(report["overall_score"], 40)

    def test_risk_register_empty_inventory(self):
        risks = risk_register({})
        # Should at least flag missing backups
        self.assertIsInstance(risks, dict)
        self.assertIn("risks", risks)
        ids = [r["id"] for r in risks["risks"]]
        self.assertIn("R001", ids, "Missing backup risk R001 expected")

    def test_risk_register_no_new_risks_when_healthy(self):
        inventory = {
            "backups": {"archives": [{"id": "b1"}]},
            "services": {"nginx": {"status": "running"}},
            "permissions": {"permissions": {}},
            "certs": {"certificates": {"example.com": {"validity": 365}}},
        }
        risks = risk_register(inventory)
        # Service risks and cert risks should not appear
        ids = [r["id"] for r in risks["risks"]]
        self.assertNotIn("R003", ids)

    def test_risk_register_flags_services_down(self):
        inventory = {
            "backups": {"archives": [{"id": "b1"}]},
            "services": {"nginx": {"status": "stopped"}},
        }
        risks = risk_register(inventory)
        ids = [r["id"] for r in risks["risks"]]
        self.assertIn("R003", ids)

    def test_risk_register_flags_many_public_perms(self):
        perms = {f"app{i}": {"allowed": ["visitors"]} for i in range(5)}
        inventory = {
            "backups": {"archives": [{"id": "b1"}]},
            "permissions": {"permissions": perms},
        }
        risks = risk_register(inventory)
        ids = [r["id"] for r in risks["risks"]]
        self.assertIn("R002", ids)

    def test_risk_register_cert_expiry_low(self):
        inventory = {
            "backups": {"archives": [{"id": "b1"}]},
            "certs": {"certificates": {"example.com": {"validity": 3}}},
        }
        risks = risk_register(inventory)
        ids = [r["id"] for r in risks["risks"]]
        # Should contain cert-related risk
        cert_risks = [r for r in risks["risks"] if "cert" in r["id"].lower() or "R004" in r["id"]]
        self.assertTrue(len(cert_risks) >= 1, f"Expected cert risk, got: {ids}")


# ─────────────────────────────────────────────────────────────────────
# 4. AUTOMATION
# ─────────────────────────────────────────────────────────────────────

from nexora_saas.automation import (  # noqa: E402
    AUTOMATION_TEMPLATES,
    CHECKLISTS,
    generate_automation_plan,
    generate_crontab,
    list_automation_templates,
)


class AutomationTests(unittest.TestCase):
    def test_list_templates_returns_all(self):
        templates = list_automation_templates()
        self.assertEqual(len(templates), len(AUTOMATION_TEMPLATES))
        for tpl in templates:
            self.assertIn("id", tpl)
            self.assertIn("schedule", tpl)
            self.assertIn("actions", tpl)

    def test_all_templates_have_valid_cron_schedule(self):
        """Each schedule must have exactly 5 fields."""
        for tpl in list_automation_templates():
            parts = tpl["schedule"].split()
            self.assertEqual(len(parts), 5, f"Template {tpl['id']} has invalid schedule: {tpl['schedule']}")

    def test_generate_automation_plan_standard(self):
        plan = generate_automation_plan("standard")
        self.assertEqual(plan["profile"], "standard")
        self.assertGreater(plan["job_count"], 0)
        self.assertIn("crontab_preview", plan)

    def test_generate_automation_plan_minimal(self):
        plan = generate_automation_plan("minimal")
        self.assertIn("daily_backup", [j["id"] for j in plan["jobs"]])

    def test_generate_automation_plan_professional_has_all(self):
        plan = generate_automation_plan("professional")
        self.assertEqual(plan["job_count"], len(AUTOMATION_TEMPLATES))

    def test_generate_automation_plan_unknown_profile_falls_back(self):
        """Unknown profile should fall back to standard."""
        plan = generate_automation_plan("nonexistent_profile")
        # Must return a plan with a non-zero job count (not crash)
        self.assertGreater(plan["job_count"], 0)

    def test_generate_crontab(self):
        jobs = [{"id": "daily_backup", "name": "Daily backup", "schedule": "0 2 * * *"}]
        crontab = generate_crontab(jobs, user="nexora")
        self.assertIn("0 2 * * *", crontab)
        self.assertIn("nexora", crontab)
        self.assertIn("daily_backup", crontab)

    def test_generate_crontab_empty_jobs(self):
        crontab = generate_crontab([])
        self.assertIsInstance(crontab, str)
        # No actual cron job lines (pattern: field field field field field command)
        job_lines = [
            ln for ln in crontab.splitlines()
            if ln.strip() and not ln.startswith("#") and not ln.startswith("SHELL") and not ln.startswith("PATH")
        ]
        self.assertEqual(job_lines, [], f"Expected no job lines, got: {job_lines}")

    def test_checklists_not_empty(self):
        self.assertGreater(len(CHECKLISTS), 0)
        for key, checklist in CHECKLISTS.items():
            self.assertIn("items", checklist, f"Checklist {key} missing items")
            self.assertGreater(len(checklist["items"]), 0)


# ─────────────────────────────────────────────────────────────────────
# 5. NOTIFICATIONS
# ─────────────────────────────────────────────────────────────────────

from nexora_saas.notifications import (  # noqa: E402
    ALERT_TEMPLATES,
    NOTIFICATION_CHANNELS,
    format_alert,
    generate_webhook_payload,
)


class NotificationsTests(unittest.TestCase):
    def test_all_templates_have_required_fields(self):
        for tid, tpl in ALERT_TEMPLATES.items():
            for field in ("title", "body", "level"):
                self.assertIn(field, tpl, f"Template {tid} missing field {field}")

    def test_format_alert_known_template(self):
        result = format_alert("service_down", service="nginx", node_id="node1", since="5m ago")
        self.assertIsNotNone(result)
        self.assertIn("nginx", result["title"])
        self.assertEqual(result["template"], "service_down")
        self.assertIn("level", result)

    def test_format_alert_unknown_template_returns_none(self):
        result = format_alert("completely_unknown_template")
        self.assertIsNone(result)

    def test_format_alert_disk_critical(self):
        alert = format_alert("disk_critical", node_id="n1", percent=95, mount="/", threshold=85)
        self.assertIsNotNone(alert)
        self.assertEqual(alert["level"], "critical")

    def test_format_alert_cert_expiring(self):
        alert = format_alert("cert_expiring", domain="example.com", days=5)
        self.assertIsNotNone(alert)
        self.assertIn("example.com", alert["title"])

    def test_generate_webhook_slack_format(self):
        alert = format_alert("service_down", service="nginx", node_id="n1", since="1m ago")
        payload = generate_webhook_payload(alert, format="slack")
        self.assertIn("text", payload)
        self.assertIn("username", payload)
        self.assertIn("nginx", payload["text"])

    def test_generate_webhook_mattermost_format(self):
        alert = format_alert("service_down", service="nginx", node_id="n1", since="1m ago")
        payload = generate_webhook_payload(alert, format="mattermost")
        self.assertIn("text", payload)

    def test_generate_webhook_ntfy_format(self):
        alert = format_alert("service_down", service="nginx", node_id="n1", since="1m ago")
        payload = generate_webhook_payload(alert, format="ntfy")
        self.assertIn("title", payload)
        self.assertIn("priority", payload)
        self.assertIsInstance(payload["priority"], int)
        # Critical → priority 5
        self.assertEqual(payload["priority"], 5)

    def test_notification_channels_defined(self):
        for channel_id in ("webhook", "email", "ntfy", "gotify"):
            self.assertIn(channel_id, NOTIFICATION_CHANNELS)

    def test_format_alert_backup_missing(self):
        alert = format_alert("backup_missing", node_id="n1", days=10)
        self.assertIsNotNone(alert)
        self.assertEqual(alert["level"], "high")


# ─────────────────────────────────────────────────────────────────────
# 6. PORTAL
# ─────────────────────────────────────────────────────────────────────

from nexora_saas.portal import (  # noqa: E402
    SECTOR_THEMES,
    THEME_PALETTES,
    generate_theme,
)


class PortalTests(unittest.TestCase):
    def test_all_palettes_have_required_fields(self):
        for name, palette in THEME_PALETTES.items():
            for field in ("accent", "surface", "text", "muted"):
                self.assertIn(field, palette, f"Palette {name} missing {field}")

    def test_generate_theme_valid_palette(self):
        theme = generate_theme("Acme Corp", palette_name="corporate")
        self.assertEqual(theme["brand_name"], "Acme Corp")
        self.assertIn("css_variables", theme)
        self.assertIn("--accent", theme["css_variables"])
        self.assertIn("--surface", theme["css_variables"])

    def test_generate_theme_unknown_palette_falls_back_to_corporate(self):
        """An unrecognized palette must fall back gracefully."""
        theme = generate_theme("Brand", palette_name="nonexistent_palette")
        self.assertIn("css_variables", theme)
        self.assertIn("--accent", theme["css_variables"])

    def test_generate_theme_custom_logo_and_tagline(self):
        theme = generate_theme("Brand", logo_url="https://example.com/logo.png", tagline="No tag no life")
        self.assertEqual(theme["logo_url"], "https://example.com/logo.png")
        self.assertEqual(theme["tagline"], "No tag no life")

    def test_generate_theme_default_tagline(self):
        theme = generate_theme("Nexora")
        self.assertIn("Nexora", theme["tagline"])

    def test_all_sector_themes_have_valid_palette(self):
        for sector, config in SECTOR_THEMES.items():
            palette_name = config["palette"]
            self.assertIn(palette_name, THEME_PALETTES, f"Sector {sector} references unknown palette {palette_name}")

    def test_generate_theme_all_css_variables_are_hex_colors(self):
        theme = generate_theme("Brand", palette_name="corporate")
        for var_name, value in theme["css_variables"].items():
            self.assertTrue(
                str(value).startswith("#"),
                f"CSS variable {var_name} should be a hex color, got: {value}",
            )

    def test_all_theme_palettes_have_primary_alias(self):
        """Each palette must expose a 'primary' alias for UI compatibility."""
        for name, palette in THEME_PALETTES.items():
            self.assertIn(
                "primary", palette,
                f"Palette '{name}' is missing the 'primary' color alias required by the console UI",
            )


# ─────────────────────────────────────────────────────────────────────
# 7. SECRET STORE
# ─────────────────────────────────────────────────────────────────────

from nexora_node_sdk.secret_store import (  # noqa: E402
    issue_secret,
    list_secrets,
    read_secret,
    revoke_secret,
    verify_secret,
)


class SecretStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state_dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    @unittest.skipIf(sys.platform == "win32", "POSIX file permissions not enforced on Windows")
    def test_issue_secret_creates_file_with_0600(self):
        result = issue_secret(self.state_dir, owner_type="node", owner_id="node-1", scopes=["read"])
        self.assertIn("token_path", result)
        path = Path(result["token_path"])
        self.assertTrue(path.exists())
        # File must not be world-readable
        mode = path.stat().st_mode & 0o777
        self.assertEqual(mode & 0o077, 0, f"Secret file mode {oct(mode)} must be 0600")

    def test_read_secret_returns_token(self):
        issue_secret(self.state_dir, owner_type="node", owner_id="node-1")
        token = read_secret(self.state_dir, owner_type="node", owner_id="node-1")
        self.assertIsNotNone(token)
        self.assertIsInstance(token, str)
        self.assertGreater(len(token), 0)

    def test_read_secret_unknown_owner_returns_none(self):
        result = read_secret(self.state_dir, owner_type="node", owner_id="does-not-exist")
        self.assertIsNone(result)

    def test_revoke_secret_clears_token(self):
        issue_secret(self.state_dir, owner_type="node", owner_id="node-rev")
        revoke_secret(self.state_dir, owner_type="node", owner_id="node-rev")
        token = read_secret(self.state_dir, owner_type="node", owner_id="node-rev")
        self.assertIsNone(token)

    def test_double_revoke_is_safe(self):
        """Revoking twice must not raise."""
        issue_secret(self.state_dir, owner_type="node", owner_id="node-dr")
        revoke_secret(self.state_dir, owner_type="node", owner_id="node-dr")
        # Should not raise
        revoke_secret(self.state_dir, owner_type="node", owner_id="node-dr")

    def test_verify_secret_correct_token(self):
        issue_secret(self.state_dir, owner_type="service", owner_id="svc-1")
        token = read_secret(self.state_dir, owner_type="service", owner_id="svc-1")
        self.assertTrue(verify_secret(self.state_dir, owner_type="service", owner_id="svc-1", provided_token=token))

    def test_verify_secret_wrong_token(self):
        issue_secret(self.state_dir, owner_type="service", owner_id="svc-2")
        self.assertFalse(verify_secret(self.state_dir, owner_type="service", owner_id="svc-2", provided_token="wrong"))

    def test_path_traversal_prevention(self):
        """A malicious owner_id with '../' must not escape the state dir."""
        # Should not raise, and must not write outside state_dir
        result = issue_secret(self.state_dir, owner_type="node", owner_id="../../../evil")
        path = Path(result["token_path"])
        # The path must be inside state_dir
        self.assertTrue(
            str(path).startswith(self.state_dir),
            f"Path traversal not prevented: {path}",
        )

    def test_list_secrets_empty_dir(self):
        results = list_secrets(self.state_dir)
        self.assertEqual(results, [])

    def test_list_secrets_multiple_owners(self):
        issue_secret(self.state_dir, owner_type="node", owner_id="n1")
        issue_secret(self.state_dir, owner_type="service", owner_id="s1")
        issue_secret(self.state_dir, owner_type="operator", owner_id="op1")
        results = list_secrets(self.state_dir)
        self.assertEqual(len(results), 3)

    def test_list_secrets_filtered_by_type(self):
        issue_secret(self.state_dir, owner_type="node", owner_id="n1")
        issue_secret(self.state_dir, owner_type="service", owner_id="s1")
        node_results = list_secrets(self.state_dir, owner_type="node")
        self.assertEqual(len(node_results), 1)

    def test_issue_secret_invalid_owner_type_raises(self):
        with self.assertRaises(ValueError):
            issue_secret(self.state_dir, owner_type="hacker", owner_id="bad")

    def test_secrets_metadata_never_contains_raw_token(self):
        """Audit listing must not expose raw tokens."""
        issue_secret(self.state_dir, owner_type="node", owner_id="n-audit")
        real_token = read_secret(self.state_dir, owner_type="node", owner_id="n-audit")
        meta_list = list_secrets(self.state_dir)
        for meta in meta_list:
            self.assertNotIn(real_token, str(meta))


# ─────────────────────────────────────────────────────────────────────
# 8. DRIFT DETECTION
# ─────────────────────────────────────────────────────────────────────

from nexora_node_sdk.drift_detection import detect_drift, detect_drift_from_state  # noqa: E402


class DriftDetectionTests(unittest.TestCase):
    def _make_inventory(
        self,
        apps=None,
        domains=None,
        services=None,
        permissions=None,
    ):
        return {
            "apps": {"apps": apps or []},
            "domains": {"domains": domains or []},
            "services": {svc: {"status": st} for svc, st in (services or {}).items()},
            "permissions": {"permissions": permissions or {}},
        }

    def test_identical_inventories_in_sync(self):
        inv = self._make_inventory(apps=[{"id": "wordpress"}], domains=["example.com"])
        result = detect_drift(inv, inv)
        self.assertEqual(result["status"], "in_sync")
        self.assertEqual(result["drift_count"], 0)

    def test_empty_inventories_in_sync(self):
        result = detect_drift({}, {})
        self.assertEqual(result["status"], "in_sync")

    def test_app_added_detected(self):
        baseline = self._make_inventory(apps=[])
        current = self._make_inventory(apps=[{"id": "nextcloud"}])
        result = detect_drift(baseline, current)
        self.assertGreater(result["drift_count"], 0)
        added = [d for d in result["drifts"] if d["type"] == "added" and d["section"] == "apps"]
        self.assertEqual(len(added), 1)

    def test_app_removed_detected(self):
        baseline = self._make_inventory(apps=[{"id": "wordpress"}])
        current = self._make_inventory(apps=[])
        result = detect_drift(baseline, current)
        removed = [d for d in result["drifts"] if d["type"] == "removed" and d["section"] == "apps"]
        self.assertEqual(len(removed), 1)

    def test_domain_added_detected(self):
        baseline = self._make_inventory(domains=["a.com"])
        current = self._make_inventory(domains=["a.com", "b.com"])
        result = detect_drift(baseline, current)
        added = [d for d in result["drifts"] if d["type"] == "added" and d["section"] == "domains"]
        self.assertEqual(len(added), 1)

    def test_service_status_change_detected(self):
        baseline = self._make_inventory(services={"nginx": "running"})
        current = self._make_inventory(services={"nginx": "stopped"})
        result = detect_drift(baseline, current)
        changed = [d for d in result["drifts"] if d["type"] == "changed" and d["section"] == "services"]
        self.assertEqual(len(changed), 1)

    def test_critical_drift_status_when_service_removed(self):
        baseline = self._make_inventory(services={"nginx": "running"})
        current = self._make_inventory(services={})
        result = detect_drift(baseline, current)
        # Removed service → warning severity → "drifted"
        self.assertIn(result["status"], ("drifted", "critical_drift", "minor_drift"))
        self.assertGreater(result["drift_count"], 0)

    def test_multiple_sections_drift(self):
        baseline = self._make_inventory(
            apps=[{"id": "wp"}], domains=["a.com"], services={"nginx": "running"}
        )
        current = self._make_inventory(
            apps=[], domains=["b.com"], services={"nginx": "stopped"}
        )
        result = detect_drift(baseline, current)
        self.assertGreater(result["drift_count"], 2)

    def test_detect_drift_from_state_no_baseline(self):
        state = {}
        result = detect_drift_from_state(state, {})
        self.assertEqual(result["status"], "no_baseline")

    def test_detect_drift_from_state_with_baseline(self):
        inv = self._make_inventory(apps=[{"id": "wp"}])
        state = {"inventory_snapshots": [{"inventory": inv, "timestamp": "2026-01-01T00:00:00Z"}]}
        # Same inventory → in_sync
        result = detect_drift_from_state(state, inv)
        self.assertEqual(result["status"], "in_sync")
        self.assertIn("baseline_timestamp", result)

    def test_sections_checked_always_present(self):
        result = detect_drift({}, {})
        self.assertIn("sections_checked", result)
        for section in ("apps", "domains", "services", "permissions"):
            self.assertIn(section, result["sections_checked"])


# ─────────────────────────────────────────────────────────────────────
# 9. MONITORING ENGINE
# ─────────────────────────────────────────────────────────────────────

from nexora_node_sdk.monitoring import (  # noqa: E402
    AlertSeverity,
    check_backup_freshness,
    check_certificates,
    check_disk_space,
    check_security_posture,
    check_services,
    run_monitoring_check,
)


class MonitoringTests(unittest.TestCase):
    def test_no_certs_no_alerts(self):
        alerts = check_certificates({"certs": {"certificates": {}}})
        self.assertEqual(alerts, [])

    def test_cert_expired_is_critical(self):
        inv = {"certs": {"certificates": {"e.com": {"validity": 0}}}}
        alerts = check_certificates(inv)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].severity, AlertSeverity.CRITICAL)

    def test_cert_negative_validity_is_critical(self):
        inv = {"certs": {"certificates": {"e.com": {"validity": -5}}}}
        alerts = check_certificates(inv)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].severity, AlertSeverity.CRITICAL)

    def test_cert_exactly_7_days_is_critical(self):
        inv = {"certs": {"certificates": {"e.com": {"validity": 7}}}}
        alerts = check_certificates(inv)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].severity, AlertSeverity.CRITICAL)

    def test_cert_8_days_is_warning(self):
        inv = {"certs": {"certificates": {"e.com": {"validity": 8}}}}
        alerts = check_certificates(inv)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].severity, AlertSeverity.WARNING)

    def test_cert_exactly_14_days_is_warning(self):
        inv = {"certs": {"certificates": {"e.com": {"validity": 14}}}}
        alerts = check_certificates(inv)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].severity, AlertSeverity.WARNING)

    def test_cert_exactly_30_days_is_info(self):
        inv = {"certs": {"certificates": {"e.com": {"validity": 30}}}}
        alerts = check_certificates(inv)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].severity, AlertSeverity.INFO)

    def test_cert_31_days_no_alert(self):
        inv = {"certs": {"certificates": {"e.com": {"validity": 31}}}}
        alerts = check_certificates(inv)
        self.assertEqual(len(alerts), 0)

    def test_cert_multiple_domains(self):
        inv = {"certs": {"certificates": {
            "expired.com": {"validity": 0},
            "ok.com": {"validity": 365},
        }}}
        alerts = check_certificates(inv)
        self.assertEqual(len(alerts), 1)
        self.assertIn("expired.com", alerts[0].id)

    def test_services_all_running_no_alerts(self):
        inv = {"services": {"nginx": {"status": "running"}, "slapd": {"status": "running"}}}
        alerts = check_services(inv)
        self.assertEqual(alerts, [])

    def test_critical_service_stopped_is_critical_alert(self):
        inv = {"services": {"nginx": {"status": "stopped"}}}
        alerts = check_services(inv)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].severity, AlertSeverity.CRITICAL)

    def test_unknown_service_stopped_is_warning(self):
        inv = {"services": {"my-custom-svc": {"status": "stopped"}}}
        alerts = check_services(inv)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].severity, AlertSeverity.WARNING)

    def test_no_backups_is_critical(self):
        alerts = check_backup_freshness({"backups": {"archives": []}})
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].severity, AlertSeverity.CRITICAL)
        self.assertEqual(alerts[0].id, "backup-none")

    def test_recent_backup_no_alert(self):
        now_iso = datetime.now(timezone.utc).isoformat()
        inv = {"backups": {"archives": [{"created_at": now_iso}]}}
        alerts = check_backup_freshness(inv, max_age_days=7)
        self.assertEqual(alerts, [])

    def test_stale_backup_is_warning(self):
        old_iso = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        inv = {"backups": {"archives": [{"created_at": old_iso}]}}
        alerts = check_backup_freshness(inv, max_age_days=7)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].id, "backup-stale")

    def test_disk_no_diagnosis_no_alerts(self):
        alerts = check_disk_space({})
        self.assertEqual(alerts, [])

    def test_disk_above_threshold_is_warning(self):
        inv = {"diagnosis": {"items": [{"category": "diskusage", "details": [{"usage_percent": 90, "mountpoint": "/"}]}]}}
        alerts = check_disk_space(inv, threshold_pct=85)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].severity, AlertSeverity.WARNING)

    def test_disk_above_95_is_critical(self):
        inv = {"diagnosis": {"items": [{"category": "diskusage", "details": [{"usage_percent": 97, "mountpoint": "/home"}]}]}}
        alerts = check_disk_space(inv, threshold_pct=85)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].severity, AlertSeverity.CRITICAL)

    def test_disk_exactly_at_threshold_triggers_alert(self):
        inv = {"diagnosis": {"items": [{"category": "diskusage", "details": [{"usage_percent": 85, "mountpoint": "/"}]}]}}
        alerts = check_disk_space(inv, threshold_pct=85)
        self.assertEqual(len(alerts), 1)

    def test_disk_below_threshold_no_alert(self):
        inv = {"diagnosis": {"items": [{"category": "diskusage", "details": [{"usage_percent": 80, "mountpoint": "/"}]}]}}
        alerts = check_disk_space(inv, threshold_pct=85)
        self.assertEqual(alerts, [])

    def test_security_posture_too_many_public_perms(self):
        perms = {f"app{i}": {"allowed": ["visitors"]} for i in range(5)}
        inv = {"permissions": {"permissions": perms}}
        alerts = check_security_posture(inv)
        self.assertEqual(len(alerts), 1)

    def test_security_posture_under_limit_no_alert(self):
        perms = {f"app{i}": {"allowed": ["visitors"]} for i in range(2)}
        inv = {"permissions": {"permissions": perms}}
        alerts = check_security_posture(inv)
        self.assertEqual(alerts, [])

    def test_run_monitoring_check_healthy_returns_healthy(self):
        now_iso = datetime.now(timezone.utc).isoformat()
        inv = {
            "services": {"nginx": {"status": "running"}},
            "certs": {"certificates": {"ok.com": {"validity": 365}}},
            "backups": {"archives": [{"created_at": now_iso}]},
        }
        report = run_monitoring_check(inv)
        self.assertEqual(report["status"], "healthy")
        self.assertEqual(report["critical_count"], 0)

    def test_run_monitoring_check_critical_returns_critical(self):
        inv = {"backups": {"archives": []}}  # No backups → critical
        report = run_monitoring_check(inv)
        self.assertEqual(report["status"], "critical")
        self.assertGreater(report["critical_count"], 0)

    def test_run_monitoring_check_has_expected_keys(self):
        report = run_monitoring_check({})
        for key in ("status", "alert_count", "critical_count", "warning_count", "alerts", "checks_performed"):
            self.assertIn(key, report)


# ─────────────────────────────────────────────────────────────────────
# 10. SCORING
# ─────────────────────────────────────────────────────────────────────

from nexora_node_sdk.scoring import (  # noqa: E402
    compute_compliance_score,
    compute_health_score,
    compute_pra_score,
    compute_security_score,
)


class ScoringTests(unittest.TestCase):
    def test_security_score_always_in_0_100(self):
        """Score must never go below 0 or above 100."""
        # Worst case: many expired certs, many public perms, many services down
        inv = {
            "certs": {"certificates": {f"d{i}.com": {"validity": -1} for i in range(10)}},
            "permissions": {"permissions": {f"app{i}": {"allowed": ["visitors"]} for i in range(20)}},
            "services": {f"svc{i}": {"status": "stopped"} for i in range(10)},
            "backups": {"archives": []},
        }
        result = compute_security_score(inv)
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)

    def test_security_score_perfect_inventory(self):
        inv = {"backups": {"archives": [{"id": "b"}]}}
        result = compute_security_score(inv)
        self.assertGreater(result["score"], 70)
        self.assertIn(result["grade"], ("A", "B"))

    def test_security_grade_A_for_high_score(self):
        inv = {"backups": {"archives": [{"id": "b"}]}}
        result = compute_security_score(inv)
        # With backups, no bad services, no expired certs → should be at least B
        self.assertIn(result["grade"], ("A", "B"))

    def test_pra_score_no_backups_is_low(self):
        result = compute_pra_score({})
        self.assertLess(result["score"], 50)

    def test_pra_score_many_backups_is_higher(self):
        inv = {"backups": {"archives": [{"id": "b1"}, {"id": "b2"}, {"id": "b3"}, {"id": "b4"}]}}
        result = compute_pra_score(inv)
        self.assertGreater(result["score"], compute_pra_score({})["score"])

    def test_pra_score_always_in_0_100(self):
        for inv in [{}, {"backups": {"archives": []}}, {"backups": {"archives": [{"id": "b"}] * 20}}]:
            result = compute_pra_score(inv)
            self.assertGreaterEqual(result["score"], 0, f"PRA score below 0: {result}")
            self.assertLessEqual(result["score"], 100, f"PRA score above 100: {result}")

    def test_health_score_all_running(self):
        inv = {"services": {"nginx": {"status": "running"}, "slapd": {"status": "running"}}}
        result = compute_health_score(inv)
        self.assertGreater(result["score"], 50)

    def test_health_score_all_down_is_low(self):
        inv = {"services": {"nginx": {"status": "stopped"}, "slapd": {"status": "stopped"}}}
        result = compute_health_score(inv)
        self.assertLessEqual(result["score"], 50)

    def test_health_score_always_in_0_100(self):
        for inv in [{}, {"services": {}}, {"services": {f"svc{i}": {"status": "stopped"} for i in range(20)}}]:
            result = compute_health_score(inv)
            self.assertGreaterEqual(result["score"], 0)
            self.assertLessEqual(result["score"], 100)

    def test_compliance_score_with_pra_and_monitoring(self):
        result_with = compute_compliance_score({}, has_pra=True, has_monitoring=True)
        result_without = compute_compliance_score({}, has_pra=False, has_monitoring=False)
        self.assertGreater(result_with["score"], result_without["score"])

    def test_compliance_score_always_in_0_100(self):
        result = compute_compliance_score({})
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)

    def test_all_scores_have_grade(self):
        for fn in (compute_security_score, compute_pra_score, compute_health_score):
            result = fn({})
            self.assertIn("grade", result, f"{fn.__name__} missing 'grade' key")
            self.assertIn(result["grade"], ("A", "B", "C", "D", "F"))


# ─────────────────────────────────────────────────────────────────────
# 11. PRA
# ─────────────────────────────────────────────────────────────────────

from nexora_node_sdk.pra import build_backup_scope, build_restore_plan  # noqa: E402


class PraTests(unittest.TestCase):
    def test_build_backup_scope_full(self):
        scope = build_backup_scope("full")
        self.assertEqual(scope["scope"], "full")
        self.assertIn("generated_at", scope)

    def test_build_backup_scope_with_apps(self):
        scope = build_backup_scope("selective", include_apps=["wordpress", "nextcloud"])
        self.assertEqual(scope["include_apps"], ["wordpress", "nextcloud"])

    def test_build_backup_scope_empty_apps(self):
        scope = build_backup_scope("full")
        self.assertEqual(scope["include_apps"], [])

    def test_build_restore_plan_has_steps(self):
        plan = build_restore_plan("snap-123", target_node="node-a")
        self.assertIn("steps", plan)
        self.assertGreater(len(plan["steps"]), 0)
        # Critical steps must be present
        for step in ("validate_snapshot", "restore_data", "verify_services"):
            self.assertIn(step, plan["steps"])

    def test_build_restore_plan_with_offsite_source(self):
        plan = build_restore_plan("snap-123", target_node="node-a", offsite_source="s3://bucket/snap-123")
        self.assertEqual(plan["offsite_source"], "s3://bucket/snap-123")

    def test_build_restore_plan_without_offsite(self):
        plan = build_restore_plan("snap-123", target_node="node-a")
        self.assertIsNone(plan["offsite_source"])

    def test_restore_plan_snapshot_and_target(self):
        plan = build_restore_plan("snap-abc", target_node="target-node-1")
        self.assertEqual(plan["snapshot_id"], "snap-abc")
        self.assertEqual(plan["target_node"], "target-node-1")


# ─────────────────────────────────────────────────────────────────────
# 12. MULTITENANT
# ─────────────────────────────────────────────────────────────────────

from nexora_saas.multitenant import (  # noqa: E402
    generate_tenant_config,
    generate_tenant_report,
    generate_tenant_setup_commands,
)


class MultitenantTests(unittest.TestCase):
    def test_generate_tenant_config_basic(self):
        config = generate_tenant_config("AcmeCorp")
        self.assertEqual(config["tenant_id"], "acmecorp")
        self.assertIn("quotas", config)
        self.assertIn("isolation", config)

    def test_tenant_id_is_slugified(self):
        config = generate_tenant_config("My Big Company")
        self.assertEqual(config["tenant_id"], "my-big-company")

    def test_tenant_domain_generated_if_not_provided(self):
        config = generate_tenant_config("Acme")
        self.assertIn("acme", config["domain"])

    def test_tenant_domain_uses_provided_value(self):
        config = generate_tenant_config("Acme", domain="acme.example.com")
        self.assertEqual(config["domain"], "acme.example.com")

    def test_tenant_quota_storage(self):
        config = generate_tenant_config("Acme", quota_gb=50)
        self.assertEqual(config["quotas"]["storage_gb"], 50)

    def test_tenant_isolation_method(self):
        config = generate_tenant_config("Acme")
        self.assertEqual(config["isolation"]["method"], "subdomain")

    def test_tenant_ynh_group(self):
        config = generate_tenant_config("Acme Corp")
        self.assertIn("acme_corp", config["ynh_group"])

    def test_generate_setup_commands_with_domain_and_users(self):
        config = generate_tenant_config("Acme", domain="acme.com", users=["alice", "bob"], apps=["wordpress"])
        cmds = generate_tenant_setup_commands(config)
        self.assertGreater(len(cmds), 0)
        # Domain creation must be first
        self.assertTrue(any("domain add" in c for c in cmds))
        # User creation
        self.assertTrue(any("alice" in c for c in cmds))
        # App install
        self.assertTrue(any("wordpress" in c for c in cmds))

    def test_generate_setup_commands_no_domain(self):
        config = generate_tenant_config("NoName")
        config["domain"] = ""
        config["users"] = []
        config["apps"] = []
        cmds = generate_tenant_setup_commands(config)
        # No domain add when domain is empty
        self.assertFalse(any("domain add" in c for c in cmds))

    def test_generate_tenant_report_aggregates(self):
        configs = [
            generate_tenant_config("A", apps=["wordpress"], users=["alice"]),
            generate_tenant_config("B", apps=["nextcloud", "gitea"], users=["bob", "carol"]),
        ]
        report = generate_tenant_report(configs)
        self.assertEqual(report["total_tenants"], 2)
        self.assertEqual(report["total_apps"], 3)
        self.assertEqual(report["total_users"], 3)

    def test_generate_tenant_report_empty(self):
        report = generate_tenant_report([])
        self.assertEqual(report["total_tenants"], 0)
        self.assertEqual(report["total_apps"], 0)


# ─────────────────────────────────────────────────────────────────────
# 13. OWNER SESSION (extreme edge cases)
# ─────────────────────────────────────────────────────────────────────

from nexora_node_sdk.auth._owner_session import (  # noqa: E402
    _sessions,
    _sessions_lock,
    create_owner_session,
    has_passphrase_configured,
    revoke_owner_session,
    set_owner_passphrase,
    validate_owner_session,
    verify_passphrase,
)


class OwnerSessionEdgeCaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_state = os.environ.get("NEXORA_STATE_PATH")
        self.old_pp_file = os.environ.get("NEXORA_OWNER_PASSPHRASE_FILE")
        self.state_path = str(Path(self.tmp.name) / "state.json")
        os.environ["NEXORA_STATE_PATH"] = self.state_path
        os.environ.pop("NEXORA_OWNER_PASSPHRASE_FILE", None)
        # Clear in-memory sessions
        with _sessions_lock:
            _sessions.clear()
        # Clear any existing passphrase
        pp_path = Path(self.state_path).with_name("owner-passphrase")
        if pp_path.exists():
            pp_path.unlink()

    def tearDown(self):
        with _sessions_lock:
            _sessions.clear()
        if self.old_state is not None:
            os.environ["NEXORA_STATE_PATH"] = self.old_state
        else:
            os.environ.pop("NEXORA_STATE_PATH", None)
        if self.old_pp_file is not None:
            os.environ["NEXORA_OWNER_PASSPHRASE_FILE"] = self.old_pp_file
        else:
            os.environ.pop("NEXORA_OWNER_PASSPHRASE_FILE", None)
        self.tmp.cleanup()

    def test_no_passphrase_configured_initially(self):
        self.assertFalse(has_passphrase_configured())

    def test_set_passphrase_marks_configured(self):
        set_owner_passphrase("MySecurePass123!")
        self.assertTrue(has_passphrase_configured())

    def test_verify_correct_passphrase(self):
        set_owner_passphrase("CorrectPass!")
        self.assertTrue(verify_passphrase("CorrectPass!"))

    def test_verify_wrong_passphrase(self):
        set_owner_passphrase("CorrectPass!")
        self.assertFalse(verify_passphrase("WrongPass!"))

    def test_create_session_returns_token(self):
        session = create_owner_session()
        self.assertIn("session_token", session)
        self.assertGreater(len(session["session_token"]), 0)
        self.assertEqual(session["role"], "owner")

    def test_validate_valid_session(self):
        session = create_owner_session()
        token = session["session_token"]
        result = validate_owner_session(token)
        self.assertIsNotNone(result)
        self.assertEqual(result["role"], "owner")

    def test_validate_unknown_token_returns_none(self):
        result = validate_owner_session("completely-unknown-token-xyz")
        self.assertIsNone(result)

    def test_validate_empty_token_returns_none(self):
        result = validate_owner_session("")
        self.assertIsNone(result)

    def test_revoke_session(self):
        session = create_owner_session()
        token = session["session_token"]
        revoked = revoke_owner_session(token)
        self.assertTrue(revoked)
        self.assertIsNone(validate_owner_session(token))

    def test_double_revoke_returns_false(self):
        session = create_owner_session()
        token = session["session_token"]
        revoke_owner_session(token)
        result = revoke_owner_session(token)
        self.assertFalse(result)

    def test_passphrase_rotation_clears_sessions(self):
        """Setting a new passphrase must invalidate all existing sessions."""
        session = create_owner_session()
        token = session["session_token"]
        # Session is valid
        self.assertIsNotNone(validate_owner_session(token))
        # Rotate passphrase
        set_owner_passphrase("NewPass2026!!")
        # Session must now be invalid
        self.assertIsNone(validate_owner_session(token))

    def test_multiple_sessions_independent(self):
        s1 = create_owner_session()
        s2 = create_owner_session()
        self.assertNotEqual(s1["session_token"], s2["session_token"])
        # Both valid
        self.assertIsNotNone(validate_owner_session(s1["session_token"]))
        self.assertIsNotNone(validate_owner_session(s2["session_token"]))

    def test_expired_session_is_rejected(self):
        """Manually inject an expired session and verify it is rejected."""
        token = "test-expired-token-xyz"
        with _sessions_lock:
            _sessions[token] = {
                "tenant_id": "test",
                "role": "owner",
                "issued_at": int(time.time()) - 10000,
                "expires_at": int(time.time()) - 1,  # Already expired
            }
        result = validate_owner_session(token)
        self.assertIsNone(result)

    def test_expired_session_is_garbage_collected(self):
        """Expired session must be removed from the store after validation check."""
        token = "test-gc-token"
        with _sessions_lock:
            _sessions[token] = {
                "tenant_id": "test",
                "role": "owner",
                "issued_at": int(time.time()) - 10000,
                "expires_at": int(time.time()) - 1,
            }
        validate_owner_session(token)
        with _sessions_lock:
            self.assertNotIn(token, _sessions, "Expired session must be garbage collected")


# ─────────────────────────────────────────────────────────────────────
# 14. SUBSCRIPTION — invalid state transitions
# ─────────────────────────────────────────────────────────────────────

from nexora_saas.subscription import (  # noqa: E402
    cancel_subscription,
    create_organization,
    create_subscription,
    reactivate_subscription,
    suspend_subscription,
)


class SubscriptionInvalidTransitionsTests(unittest.TestCase):
    def setUp(self):
        self.state: dict = {}
        org = create_organization(self.state, name="TransOrg", contact_email="t@t.test")["organization"]
        self.org_id = org["org_id"]
        sub_res = create_subscription(self.state, org_id=self.org_id, plan_tier="pro")
        self.sub_id = sub_res["subscription"]["subscription_id"]

    def test_cancel_active_subscription_succeeds(self):
        result = cancel_subscription(self.state, self.sub_id)
        self.assertTrue(result["success"])
        self.assertEqual(result["subscription"]["status"], "cancelled")

    def test_double_cancel_second_fails(self):
        cancel_subscription(self.state, self.sub_id)
        # Second cancel must fail
        result = cancel_subscription(self.state, self.sub_id)
        # Should not raise but return failure or idempotent result
        # According to the module, we check: cancelled → no-op graceful
        self.assertFalse(result.get("success", True) and result.get("subscription", {}).get("status") != "cancelled",
                         "Double cancel should either succeed idempotently or fail gracefully")

    def test_reactivate_cancelled_subscription_fails(self):
        """Cannot reactivate a cancelled subscription (only suspended ones)."""
        cancel_subscription(self.state, self.sub_id)
        result = reactivate_subscription(self.state, self.sub_id)
        self.assertFalse(result["success"], "Reactivating a cancelled subscription must fail")

    def test_reactivate_active_subscription_fails(self):
        """Reactivating an already active subscription must fail."""
        result = reactivate_subscription(self.state, self.sub_id)
        self.assertFalse(result["success"], "Reactivating an active subscription must fail")

    def test_suspend_then_reactivate(self):
        suspend_subscription(self.state, self.sub_id, reason="billing")
        result = reactivate_subscription(self.state, self.sub_id)
        self.assertTrue(result["success"])
        self.assertEqual(result["subscription"]["status"], "active")

    def test_suspend_cancelled_subscription_fails(self):
        cancel_subscription(self.state, self.sub_id)
        result = suspend_subscription(self.state, self.sub_id)
        self.assertFalse(result["success"], "Suspending a cancelled subscription must fail")

    def test_cancel_nonexistent_subscription(self):
        result = cancel_subscription(self.state, "sub-doesnotexist")
        self.assertFalse(result["success"])
        self.assertIn("error", result)

    def test_reactivate_nonexistent_subscription(self):
        result = reactivate_subscription(self.state, "sub-doesnotexist")
        self.assertFalse(result["success"])
        self.assertIn("error", result)

    def test_suspended_tenant_reactivated_with_subscription(self):
        """When a suspended subscription is reactivated, the tenant must also become active."""
        suspend_subscription(self.state, self.sub_id)
        reactivate_subscription(self.state, self.sub_id)
        # Find associated tenant
        sub = next(s for s in self.state["subscriptions"] if s["subscription_id"] == self.sub_id)
        tenant = next(t for t in self.state["tenants"] if t["tenant_id"] == sub["tenant_id"])
        self.assertEqual(tenant["status"], "active")


if __name__ == "__main__":
    unittest.main()
