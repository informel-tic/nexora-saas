import tempfile
import unittest
from pathlib import Path

from nexora_node_sdk import overlay_guard


class OverlayGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        # Point guard paths to temporary directory
        overlay_guard.GUARD_DIR = Path(self.tmpdir.name) / "guard"
        overlay_guard.SAAS_SECRET_PATH = overlay_guard.GUARD_DIR / "saas_shared_secret"
        overlay_guard.TAMPER_LOG_PATH = overlay_guard.GUARD_DIR / "tamper_events.jsonl"
        overlay_guard.MANIFEST_SIG_PATH = Path(self.tmpdir.name) / "overlay" / "manifest.sig"
        # Ensure clean
        try:
            if overlay_guard.SAAS_SECRET_PATH.exists():
                overlay_guard.SAAS_SECRET_PATH.unlink()
        except OSError:
            pass

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_compute_and_validate_lease(self):
        expiry = overlay_guard.compute_lease_expiry(seconds=60)
        self.assertTrue(overlay_guard.is_lease_valid(expiry))
        self.assertFalse(overlay_guard.is_lease_valid("not-a-date"))
        self.assertFalse(overlay_guard.is_lease_valid(None))

    def test_renew_and_find_expired(self):
        manifest = {"components": [{"name": "c1", "kind": "docker-service", "valid_until": None},
                                     {"name": "c2", "kind": "docker-service", "valid_until": overlay_guard.compute_lease_expiry(seconds=-10)}]}
        # Renew leases -> no expired components
        manifest2 = overlay_guard.renew_all_leases(manifest, lease_seconds=60)
        expired = overlay_guard.find_expired_components(manifest2)
        self.assertEqual(len(expired), 0)

    def test_check_overlay_file_integrity_reports_missing(self):
        # Create an existing file and a missing file path
        existing = Path(self.tmpdir.name) / "compose.yml"
        existing.write_text("content")
        manifest = {"components": [
            {"name": "present", "kind": "docker-service", "detail": {"compose_path": str(existing)}},
            {"name": "missing", "kind": "docker-service", "detail": {"compose_path": str(Path(self.tmpdir.name) / "nope.yml")}},
        ]}
        res = overlay_guard.check_overlay_file_integrity(manifest)
        self.assertFalse(res["integrity_ok"])
        self.assertTrue(any(i["issue"] == "compose_file_missing" for i in res["issues"]))

    def test_tamper_logging_and_retrieval(self):
        # Log an event and retrieve it
        overlay_guard._log_tamper_event("unit_test_event", {"x": 1})
        events = overlay_guard.get_tamper_events()
        self.assertTrue(isinstance(events, list))
        self.assertTrue(any(e.get("event") == "unit_test_event" for e in events))


if __name__ == "__main__":
    unittest.main()
