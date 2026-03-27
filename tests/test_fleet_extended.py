from __future__ import annotations

import unittest
from pathlib import Path


class FleetExtendedTests(unittest.TestCase):
    def test_fleet_source_defaults_remote_urls_to_https(self):
        source = Path("src/nexora_node_sdk/fleet.py").read_text(encoding="utf-8")
        self.assertIn('scheme: str = "https"', source)

    def test_fleet_source_mentions_retry_helper(self):
        source = Path("src/nexora_node_sdk/fleet.py").read_text(encoding="utf-8")
        self.assertIn('_request_with_retries', source)

    def test_fleet_source_mentions_fetched_at_cache(self):
        source = Path("src/nexora_node_sdk/fleet.py").read_text(encoding="utf-8")
        self.assertIn('"fetched_at"', source)


if __name__ == "__main__":
    unittest.main()
