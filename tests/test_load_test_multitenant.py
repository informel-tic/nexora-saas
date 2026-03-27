from __future__ import annotations

import unittest

from scripts.load_test_multitenant import run_smoke


class LoadTestMultitenantTests(unittest.TestCase):
    def test_run_smoke_reports_zero_failures_for_small_run(self):
        report = run_smoke(tenants=4, requests=40, workers=8, duration_seconds=5)
        self.assertEqual(report["failures"], 0)
        self.assertGreater(report["requests_executed"], 0)
        self.assertIn("latency_ms", report)
        self.assertIn("p95", report["latency_ms"])


if __name__ == "__main__":
    unittest.main()
