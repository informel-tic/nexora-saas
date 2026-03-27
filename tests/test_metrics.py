from __future__ import annotations

import unittest

from nexora_node_sdk.metrics import record_metric, summarize_metric_series
from nexora_saas.notifications import format_alert
from nexora_saas.sla import compute_sla_from_history, record_downtime


class MetricsTests(unittest.TestCase):
    def test_record_metric_appends_sample(self):
        series = []
        record_metric(series, "cpu_usage", 42.0, labels={"node": "a"})
        self.assertEqual(series[0]["name"], "cpu_usage")

    def test_summarize_metric_series_computes_average(self):
        series = []
        record_metric(series, "cpu_usage", 40)
        record_metric(series, "cpu_usage", 50)
        summary = summarize_metric_series(series, "cpu_usage")
        self.assertEqual(summary["avg"], 45.0)

    def test_notifications_and_sla_helpers_remain_usable(self):
        alert = format_alert("pra_ready", date="2026-03-23", score=90)
        self.assertEqual(alert["template"], "pra_ready")
        history = record_downtime(5, reason="test", state_path="/tmp/nexora-sla-test.json")
        report = compute_sla_from_history(state_path="/tmp/nexora-sla-test.json")
        self.assertTrue(history["recorded"])
        self.assertIn("uptime", report)


if __name__ == "__main__":
    unittest.main()
