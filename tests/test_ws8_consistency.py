import os
import unittest
from unittest.mock import patch

from nexora_node_sdk.scoring import compute_health_score, compute_pra_score, compute_security_score
from nexora_saas.orchestrator import NexoraService


class WS8ConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.repo_root = os.getcwd()
        # Mock the state repository to avoid file I/O if possible,
        # or just let it use the real one if it's safe.
        # But we MUST mock the fetchers.
        self.mock_inventory = {
            "version": {"yunohost": {"version": "11.2.0"}},
            "apps": {"apps": []},
            "domains": {"domains": []},
            "certs": {"certificates": {}},
            "backups": {"archives": []},
            "services": {"services": {}},
            "permissions": {"permissions": {}},
            "settings": {},
            "diagnosis": {},
            "app_map": {}
        }

    def test_scoring_consistency(self):
        with patch('nexora_saas.orchestrator.NexoraService._fetch_section') as mock_fetch, \
             patch('nexora_saas.orchestrator.NexoraService._ensure_identity_state') as mock_id:
            mock_fetch.side_effect = lambda section: self.mock_inventory.get(section, {})
            mock_id.side_effect = lambda state, **kwargs: state # Just return state as is

            service = NexoraService(self.repo_root)

            # 1. Get reports from the specialized module
            inv = service.local_inventory()
            expected_sec = compute_security_score(inv)["score"]
            expected_pra = compute_pra_score(inv)["score"]
            expected_health = compute_health_score(inv)["score"]

            # 2. Get the summary from the service
            summary = service.local_node_summary()

            # 3. Assert they match
            self.assertEqual(summary.security_score, expected_sec, "Security score mismatch")
            self.assertEqual(summary.pra_score, expected_pra, "PRA score mismatch")
            self.assertEqual(summary.health_score, expected_health, "Health score mismatch")

    def test_dashboard_consistency(self):
        with patch('nexora_saas.orchestrator.NexoraService._fetch_section') as mock_fetch, \
             patch('nexora_saas.orchestrator.NexoraService._ensure_identity_state') as mock_id:
            mock_fetch.side_effect = lambda section: self.mock_inventory.get(section, {})
            mock_id.side_effect = lambda state, **kwargs: state

            service = NexoraService(self.repo_root)
            summary = service.local_node_summary()
            dash = service.dashboard()

            self.assertEqual(dash.node.security_score, summary.security_score)
            self.assertEqual(dash.node.pra_score, summary.pra_score)
            self.assertEqual(dash.node.health_score, summary.health_score)

if __name__ == "__main__":
    unittest.main()
