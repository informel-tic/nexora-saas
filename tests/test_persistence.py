"""Tests for nexora_node_sdk.persistence — JsonStateRepository."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


def _make_repo(tmp_path: Path):
    from nexora_node_sdk.persistence import JsonStateRepository
    from nexora_node_sdk.state import StateStore

    state_file = tmp_path / "state.json"
    store = StateStore(state_file)
    return JsonStateRepository(store=store, backup_retention=5), state_file


class TestJsonStateRepositoryProperties(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.repo, self.state_file = _make_repo(self.tmp)

    def tearDown(self):
        self._td.cleanup()

    def test_path_property(self):
        self.assertEqual(self.repo.path, self.state_file)

    def test_backup_dir_property(self):
        self.assertEqual(self.repo.backup_dir, self.state_file.parent / "backups")

    def test_temp_path_has_tmp_suffix(self):
        self.assertIn(".tmp", str(self.repo.temp_path))

    def test_journal_path_has_journal_suffix(self):
        self.assertIn(".journal", str(self.repo.journal_path))

    def test_backend_name(self):
        self.assertEqual(self.repo.backend_name, "json-file")

    def test_schema_version(self):
        self.assertEqual(self.repo.schema_version, "ws2-v2")


class TestJsonStateRepositoryLoadSave(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.repo, _ = _make_repo(self.tmp)

    def tearDown(self):
        self._td.cleanup()

    def test_load_returns_dict_with_defaults_when_no_file(self):
        data = self.repo.load()
        self.assertIsInstance(data, dict)
        self.assertIn("nodes", data)

    def test_save_then_load_roundtrip(self):
        self.repo.save({"nodes": [], "custom_key": "hello"})
        loaded = self.repo.load()
        self.assertEqual(loaded["custom_key"], "hello")

    def test_save_creates_persistence_metadata(self):
        self.repo.save({})
        loaded = self.repo.load()
        self.assertIn("_persistence", loaded)
        self.assertEqual(loaded["_persistence"]["backend"], "json-file")
        self.assertEqual(loaded["_persistence"]["schema_version"], "ws2-v2")

    def test_save_creates_backup_before_overwrite(self):
        self.repo.save({"nodes": [], "v": 1})
        self.repo.save({"nodes": [], "v": 2})
        backups = self.repo.list_backups()
        self.assertGreaterEqual(len(backups), 1)

    def test_load_strips_state_warning_from_default_state(self):
        data = self.repo.load()
        self.assertNotIn("_state_warning", data)

    def test_save_strips_state_warning_and_recovery(self):
        self.repo.save({"_state_warning": {"code": "x"}, "_state_recovery": {}})
        loaded = self.repo.load()
        self.assertNotIn("_state_warning", loaded)
        self.assertNotIn("_state_recovery", loaded)


class TestJsonStateRepositoryBackup(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.repo, _ = _make_repo(self.tmp)

    def tearDown(self):
        self._td.cleanup()

    def test_create_backup_returns_dict_with_created_true(self):
        self.repo.save({"nodes": []})
        result = self.repo.create_backup(reason="test")
        self.assertTrue(result["created"])
        self.assertEqual(result["reason"], "test")
        self.assertIn("path", result)

    def test_list_backups_empty_when_none(self):
        backups = self.repo.list_backups()
        self.assertIsInstance(backups, list)

    def test_backup_retention_enforced(self):
        self.repo.save({"nodes": []})
        # Create more backups than retention limit (5)
        for i in range(8):
            self.repo.create_backup(reason=f"b{i}")
        backups = self.repo.list_backups()
        self.assertLessEqual(len(backups), 5)

    def test_restore_backup_no_backup_returns_error(self):
        result = self.repo.restore_backup()
        self.assertFalse(result["restored"])
        self.assertIn("error", result)

    def test_restore_backup_from_explicit_nonexistent_path(self):
        result = self.repo.restore_backup("/nonexistent/path/state.json")
        self.assertFalse(result["restored"])

    def test_restore_backup_from_created_backup(self):
        self.repo.save({"nodes": [], "marker": "original"})
        bk = self.repo.create_backup(reason="snap")
        self.repo.save({"nodes": [], "marker": "modified"})
        result = self.repo.restore_backup(bk["path"])
        self.assertTrue(result["restored"])
        loaded = self.repo.load()
        self.assertEqual(loaded.get("marker"), "original")


class TestJsonStateRepositoryJournal(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.repo, self.state_file = _make_repo(self.tmp)

    def tearDown(self):
        self._td.cleanup()

    def test_journal_cleaned_up_after_save(self):
        self.repo.save({"nodes": []})
        self.assertFalse(self.repo.journal_path.exists())

    def test_load_recovers_from_valid_journal(self):
        # Manually write a journal as if a save was interrupted
        journal_payload = {
            "created_at": "2024-01-01T00:00:00Z",
            "reason": "pending-save",
            "payload": {"nodes": [], "recovered_marker": True},
        }
        self.repo.journal_path.write_text(
            json.dumps(journal_payload), encoding="utf-8"
        )
        loaded = self.repo.load()
        self.assertTrue(loaded.get("recovered_marker"))
        # Journal should be consumed
        self.assertFalse(self.repo.journal_path.exists())

    def test_load_handles_corrupt_journal_gracefully(self):
        self.repo.journal_path.parent.mkdir(parents=True, exist_ok=True)
        self.repo.journal_path.write_text("not-json", encoding="utf-8")
        # Should not raise
        loaded = self.repo.load()
        self.assertIsInstance(loaded, dict)


class TestJsonStateRepositoryDescribe(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.repo, _ = _make_repo(self.tmp)

    def tearDown(self):
        self._td.cleanup()

    def test_describe_returns_expected_keys(self):
        desc = self.repo.describe()
        for key in ("backend", "path", "exists", "backup_dir", "journal_path", "schema_version"):
            self.assertIn(key, desc)

    def test_describe_exists_false_before_save(self):
        desc = self.repo.describe()
        self.assertFalse(desc["exists"])

    def test_describe_exists_true_after_save(self):
        self.repo.save({})
        desc = self.repo.describe()
        self.assertTrue(desc["exists"])

    def test_backup_policy_returns_strategy(self):
        policy = self.repo.backup_policy()
        self.assertIn("strategy", policy)
        self.assertIn("backup_retention", policy)
        self.assertEqual(policy["backup_retention"], 5)


class TestJsonStateRepositoryCoherence(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.repo, _ = _make_repo(self.tmp)

    def tearDown(self):
        self._td.cleanup()

    def test_coherence_report_structure(self):
        self.repo.save({"nodes": [{"node_id": "n1", "status": "healthy"}]})
        report = self.repo.coherence_report()
        self.assertIn("counts", report)
        self.assertIn("nodes", report["counts"])
        self.assertEqual(report["counts"]["nodes"], 1)


if __name__ == "__main__":
    unittest.main()
