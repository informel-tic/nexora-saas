from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from nexora_saas.orchestrator import NexoraService


class OrchestratorBehaviorTests(unittest.TestCase):
    def _service_from_fixture(self, fixture_name: str) -> NexoraService:
        fixture = json.loads((Path("tests/fixtures") / fixture_name).read_text(encoding="utf-8"))
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        service = NexoraService(Path("."), state_path=Path(tmp.name) / "state.json")
        service._fetch_section = lambda section: fixture.get(section, {})  # type: ignore[method-assign]
        return service

    def test_local_node_summary_is_healthy_on_tested_fixture(self):
        service = self._service_from_fixture("inventory_healthy.json")
        summary = service.local_node_summary()
        self.assertEqual(summary.status, "healthy")
        self.assertEqual(summary.apps_count, 1)
        self.assertEqual(summary.backups_count, 1)
        self.assertIn("compatibility-status:production_ready", summary.notes)
        self.assertNotIn("compatibility:manual_review_required", summary.notes)

    def test_local_node_summary_marks_experimental_fixture_as_degraded(self):
        service = self._service_from_fixture("inventory_experimental.json")
        summary = service.local_node_summary()
        self.assertEqual(summary.status, "degraded")
        self.assertEqual(summary.apps_count, 1)
        self.assertIn("compatibility-status:observe_only", summary.notes)
        self.assertIn("compatibility:manual_review_required", summary.notes)
        self.assertTrue(any(note.startswith("compatibility:") for note in summary.notes))


if __name__ == "__main__":
    unittest.main()
