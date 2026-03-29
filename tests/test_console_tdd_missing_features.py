from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import apps.control_plane.api as api_module
from nexora_node_sdk.auth import get_api_token
from nexora_saas.orchestrator import NexoraService


class ConsoleMissingFeaturesTDDTests(unittest.TestCase):
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
            "X-Nexora-Actor-Role": "admin",
        }

    def tearDown(self) -> None:
        os.environ.pop("NEXORA_STATE_PATH", None)
        api_module.service = self.original_service
        self.tmp_dir.cleanup()

    def test_pra_action_endpoints_are_available(self):
        routes = [
            "/api/pra/snapshot",
            "/api/pra/readiness",
            "/api/pra/export",
        ]
        for route in routes:
            with self.subTest(route=route):
                response = self.client.get(route, headers=self.headers)
                self.assertEqual(response.status_code, 200, response.text)
                payload = response.json()
                self.assertIsInstance(payload, dict)
                self.assertIn("action", payload)

    def test_subscription_reactivate_endpoint_restores_active_status(self):
        org = self.client.post(
            "/api/organizations",
            headers=self.headers,
            json={"name": "Acme", "contact_email": "ops@acme.test", "billing_address": ""},
        )
        self.assertEqual(org.status_code, 200, org.text)
        org_payload = org.json()
        org_id = org_payload.get("org_id")
        if not org_id:
            org_id = (org_payload.get("organization") or {}).get("org_id")
        self.assertTrue(org_id)

        sub = self.client.post(
            "/api/subscriptions",
            headers=self.headers,
            json={"org_id": org_id, "plan_tier": "free", "tenant_label": "acme"},
        )
        self.assertEqual(sub.status_code, 200, sub.text)
        sub_payload = sub.json()
        sub_id = sub_payload.get("subscription_id")
        if not sub_id:
            sub_id = (sub_payload.get("subscription") or {}).get("subscription_id")
        self.assertTrue(sub_id)

        suspend = self.client.post(
            f"/api/subscriptions/{sub_id}/suspend",
            headers=self.headers,
            json={"reason": "billing"},
        )
        self.assertEqual(suspend.status_code, 200, suspend.text)

        reactivate = self.client.post(
            f"/api/subscriptions/{sub_id}/reactivate",
            headers=self.headers,
            json={},
        )
        self.assertEqual(reactivate.status_code, 200, reactivate.text)
        self.assertTrue(reactivate.json().get("success"))
        self.assertEqual(reactivate.json().get("subscription", {}).get("status"), "active")

    def test_owner_console_catalog_renderer_uses_existing_view(self):
        source = Path("apps/owner_console/app.js").read_text(encoding="utf-8")
        self.assertIn("catalog: views.loadYnhCatalog", source)
        self.assertIn("'ynh-catalog': views.loadYnhCatalog", source)

    def test_owner_console_tenants_loader_handles_list_payload(self):
        source = Path("apps/owner_console/app.js").read_text(encoding="utf-8")
        self.assertIn("Array.isArray(data)", source)

    def test_console_api_supports_custom_http_method(self):
        source = Path("apps/console/api.js").read_text(encoding="utf-8")
        self.assertIn("init && init.method", source)

    def test_owner_api_supports_custom_http_method(self):
        source = Path("apps/owner_console/api.js").read_text(encoding="utf-8")
        self.assertIn("init && init.method", source)


if __name__ == "__main__":
    unittest.main()
