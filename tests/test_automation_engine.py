"""Tests for nexora_node_sdk.automation_engine — tier-gated automation."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class TestResolveTier(unittest.TestCase):
    def test_free_tier_from_enum(self):
        from nexora_node_sdk.automation_engine import _resolve_tier
        from nexora_node_sdk.models import TenantTier

        self.assertEqual(_resolve_tier(TenantTier.FREE), TenantTier.FREE)

    def test_pro_tier_from_string(self):
        from nexora_node_sdk.automation_engine import _resolve_tier
        from nexora_node_sdk.models import TenantTier

        self.assertEqual(_resolve_tier("pro"), TenantTier.PRO)

    def test_enterprise_from_string(self):
        from nexora_node_sdk.automation_engine import _resolve_tier
        from nexora_node_sdk.models import TenantTier

        self.assertEqual(_resolve_tier("enterprise"), TenantTier.ENTERPRISE)

    def test_invalid_string_defaults_to_free(self):
        from nexora_node_sdk.automation_engine import _resolve_tier
        from nexora_node_sdk.models import TenantTier

        self.assertEqual(_resolve_tier("nonexistent_tier"), TenantTier.FREE)


class TestGetAutomationProfileForTier(unittest.TestCase):
    def test_free_returns_minimal(self):
        from nexora_node_sdk.automation_engine import get_automation_profile_for_tier

        self.assertEqual(get_automation_profile_for_tier("free"), "minimal")

    def test_pro_returns_standard(self):
        from nexora_node_sdk.automation_engine import get_automation_profile_for_tier

        self.assertEqual(get_automation_profile_for_tier("pro"), "standard")

    def test_enterprise_returns_professional(self):
        from nexora_node_sdk.automation_engine import get_automation_profile_for_tier

        self.assertEqual(get_automation_profile_for_tier("enterprise"), "professional")


class TestGetAllowedTemplates(unittest.TestCase):
    def test_free_has_minimal_templates(self):
        from nexora_node_sdk.automation_engine import get_allowed_templates

        templates = get_allowed_templates("free")
        self.assertIsInstance(templates, list)
        ids = [t["id"] for t in templates]
        self.assertIn("daily_backup", ids)
        self.assertIn("cert_renewal_check", ids)

    def test_pro_has_more_than_free(self):
        from nexora_node_sdk.automation_engine import get_allowed_templates

        free_count = len(get_allowed_templates("free"))
        pro_count = len(get_allowed_templates("pro"))
        self.assertGreater(pro_count, free_count)

    def test_enterprise_has_all_templates(self):
        from nexora_node_sdk.automation_engine import get_allowed_templates
        from nexora_saas.automation import AUTOMATION_TEMPLATES

        enterprise_templates = get_allowed_templates("enterprise")
        self.assertEqual(len(enterprise_templates), len(AUTOMATION_TEMPLATES))

    def test_templates_have_id_and_name(self):
        from nexora_node_sdk.automation_engine import get_allowed_templates

        for tpl in get_allowed_templates("pro"):
            self.assertIn("id", tpl)
            self.assertIn("name", tpl)


class TestGetBlockedTemplates(unittest.TestCase):
    def test_free_has_blocked_templates(self):
        from nexora_node_sdk.automation_engine import get_blocked_templates

        blocked = get_blocked_templates("free")
        self.assertGreater(len(blocked), 0)

    def test_enterprise_has_no_blocked_templates(self):
        from nexora_node_sdk.automation_engine import get_blocked_templates

        blocked = get_blocked_templates("enterprise")
        self.assertEqual(len(blocked), 0)

    def test_blocked_template_has_required_tier_and_hint(self):
        from nexora_node_sdk.automation_engine import get_blocked_templates

        blocked = get_blocked_templates("free")
        for item in blocked:
            self.assertIn("required_tier", item)
            self.assertIn("upgrade_hint", item)


class TestIsTemplateAllowed(unittest.TestCase):
    def test_daily_backup_allowed_for_free(self):
        from nexora_node_sdk.automation_engine import is_template_allowed

        self.assertTrue(is_template_allowed("daily_backup", "free"))

    def test_cert_renewal_allowed_for_free(self):
        from nexora_node_sdk.automation_engine import is_template_allowed

        self.assertTrue(is_template_allowed("cert_renewal_check", "free"))

    def test_weekly_pra_not_allowed_for_free(self):
        from nexora_node_sdk.automation_engine import is_template_allowed

        # weekly_pra_snapshot is only in standard+professional
        self.assertFalse(is_template_allowed("weekly_pra_snapshot", "free"))

    def test_weekly_pra_allowed_for_pro(self):
        from nexora_node_sdk.automation_engine import is_template_allowed

        self.assertTrue(is_template_allowed("weekly_pra_snapshot", "pro"))

    def test_all_allowed_for_enterprise(self):
        from nexora_node_sdk.automation_engine import is_template_allowed
        from nexora_saas.automation import AUTOMATION_TEMPLATES

        for tid in AUTOMATION_TEMPLATES:
            self.assertTrue(is_template_allowed(tid, "enterprise"), f"Template {tid} should be allowed for enterprise")


class TestGenerateTierAutomationPlan(unittest.TestCase):
    def test_free_plan_structure(self):
        from nexora_node_sdk.automation_engine import generate_tier_automation_plan

        plan = generate_tier_automation_plan("free")
        self.assertEqual(plan["tier"], "free")
        self.assertIn("jobs", plan)
        self.assertIn("blocked_templates", plan)
        self.assertGreater(plan.get("upgrade_unlocks", 0), 0)

    def test_enterprise_plan_has_no_blocked_templates(self):
        from nexora_node_sdk.automation_engine import generate_tier_automation_plan

        plan = generate_tier_automation_plan("enterprise")
        self.assertEqual(plan["blocked_templates"], [])
        self.assertEqual(plan.get("upgrade_unlocks"), 0)

    def test_plan_job_count_matches_allowed(self):
        from nexora_node_sdk.automation_engine import generate_tier_automation_plan, get_allowed_templates

        plan = generate_tier_automation_plan("pro")
        allowed = get_allowed_templates("pro")
        self.assertEqual(plan["job_count"], len(allowed))

    def test_plan_total_template_count(self):
        from nexora_node_sdk.automation_engine import generate_tier_automation_plan
        from nexora_saas.automation import AUTOMATION_TEMPLATES

        plan = generate_tier_automation_plan("free")
        self.assertEqual(plan["total_template_count"], len(AUTOMATION_TEMPLATES))


class TestGenerateTierCrontab(unittest.TestCase):
    def test_returns_expected_keys(self):
        from nexora_node_sdk.automation_engine import generate_tier_crontab

        result = generate_tier_crontab("free")
        for key in ("tier", "profile", "content", "job_count"):
            self.assertIn(key, result)

    def test_content_is_string(self):
        from nexora_node_sdk.automation_engine import generate_tier_crontab

        result = generate_tier_crontab("pro")
        self.assertIsInstance(result["content"], str)

    def test_tier_preserved(self):
        from nexora_node_sdk.automation_engine import generate_tier_crontab

        result = generate_tier_crontab("enterprise")
        self.assertEqual(result["tier"], "enterprise")


class TestRecordJobExecution(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.history_file = str(self.tmp / "automation-history.json")

    def tearDown(self):
        self._td.cleanup()

    def test_records_execution_creates_file(self):
        from nexora_node_sdk.automation_engine import record_job_execution

        result = record_job_execution(
            "daily_backup",
            success=True,
            tier="free",
            duration_s=1.5,
            state_path=self.history_file,
        )
        self.assertTrue(result["recorded"])
        self.assertEqual(result["template_id"], "daily_backup")
        self.assertTrue(Path(self.history_file).exists())

    def test_multiple_records_accumulate(self):
        from nexora_node_sdk.automation_engine import record_job_execution

        for i in range(3):
            record_job_execution(
                "daily_backup",
                success=True,
                tier="pro",
                duration_s=float(i),
                state_path=self.history_file,
            )
        data = json.loads(Path(self.history_file).read_text())
        self.assertEqual(len(data["executions"]), 3)

    def test_records_failure(self):
        from nexora_node_sdk.automation_engine import record_job_execution

        record_job_execution(
            "daily_backup",
            success=False,
            tier="free",
            error="disk full",
            state_path=self.history_file,
        )
        data = json.loads(Path(self.history_file).read_text())
        self.assertFalse(data["executions"][0]["success"])
        self.assertEqual(data["executions"][0]["error"], "disk full")

    def test_retention_capped_at_500(self):
        from nexora_node_sdk.automation_engine import record_job_execution

        # Create a file with 499 entries already
        initial = {"executions": [{"template_id": "x", "tier": "free", "success": True, "duration_s": 0, "error": "", "timestamp": "t"} for _ in range(499)]}
        Path(self.history_file).parent.mkdir(parents=True, exist_ok=True)
        Path(self.history_file).write_text(json.dumps(initial))
        # Add one more, still under 500
        record_job_execution("daily_backup", success=True, tier="free", state_path=self.history_file)
        data = json.loads(Path(self.history_file).read_text())
        self.assertEqual(len(data["executions"]), 500)
        # Add one more, should trim to 500
        record_job_execution("daily_backup", success=True, tier="free", state_path=self.history_file)
        data = json.loads(Path(self.history_file).read_text())
        self.assertEqual(len(data["executions"]), 500)


class TestGetJobHistory(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.history_file = str(self.tmp / "automation-history.json")

    def tearDown(self):
        self._td.cleanup()

    def test_empty_history_returns_correct_defaults(self):
        from nexora_node_sdk.automation_engine import get_job_history

        result = get_job_history(state_path=self.history_file)
        self.assertEqual(result["total_executions"], 0)
        self.assertEqual(result["success_rate"], 0)

    def test_returns_filtered_by_tier(self):
        from nexora_node_sdk.automation_engine import record_job_execution, get_job_history

        record_job_execution("daily_backup", success=True, tier="free", state_path=self.history_file)
        record_job_execution("weekly_pra_snapshot", success=True, tier="pro", state_path=self.history_file)
        result = get_job_history(tier="free", state_path=self.history_file)
        self.assertEqual(result["total_executions"], 1)

    def test_success_rate_calculation(self):
        from nexora_node_sdk.automation_engine import record_job_execution, get_job_history

        record_job_execution("daily_backup", success=True, tier="free", state_path=self.history_file)
        record_job_execution("daily_backup", success=False, tier="free", state_path=self.history_file)
        result = get_job_history(state_path=self.history_file)
        self.assertEqual(result["success_rate"], 50.0)


class TestGetAutomationStatus(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.history_file = str(self.tmp / "automation-history.json")

    def tearDown(self):
        self._td.cleanup()

    def test_status_structure(self):
        from nexora_node_sdk.automation_engine import get_automation_status
        from unittest.mock import patch

        with patch("nexora_node_sdk.automation_engine.get_job_history", return_value={
            "total_executions": 0, "success_rate": 0.0, "last_execution": None, "recent": []
        }):
            result = get_automation_status("pro")
            for key in ("tier", "profile", "active_jobs", "blocked_count", "jobs", "execution_history"):
                self.assertIn(key, result)

    def test_free_tier_blocked_count_positive(self):
        from nexora_node_sdk.automation_engine import get_automation_status
        from unittest.mock import patch

        with patch("nexora_node_sdk.automation_engine.get_job_history", return_value={
            "total_executions": 0, "success_rate": 0.0, "last_execution": None, "recent": []
        }):
            result = get_automation_status("free")
            self.assertGreater(result["blocked_count"], 0)


class TestMinimumTierForTemplate(unittest.TestCase):
    def test_daily_backup_min_tier_is_free(self):
        from nexora_node_sdk.automation_engine import _minimum_tier_for_template
        from nexora_node_sdk.models import TenantTier

        tier = _minimum_tier_for_template("daily_backup")
        self.assertEqual(tier, TenantTier.FREE)

    def test_unknown_template_returns_none(self):
        from nexora_node_sdk.automation_engine import _minimum_tier_for_template

        tier = _minimum_tier_for_template("nonexistent_template_xyz")
        self.assertIsNone(tier)


if __name__ == "__main__":
    unittest.main()
