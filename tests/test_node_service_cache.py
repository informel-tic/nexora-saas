import tempfile
import time
from pathlib import Path

from nexora_node_sdk import node_service


def test_inventory_cache_ttl():
    cache = node_service._InventoryCache(ttl=0.05)
    cache.set("k", {"x": 1})
    assert cache.get("k") == {"x": 1}
    time.sleep(0.06)
    assert cache.get("k") is None


def test_persist_and_load_cache_entry():
    with tempfile.TemporaryDirectory() as td:
        state_path = Path(td) / "var" / "state.json"
        ns = node_service.NodeService(repo_root=td, state_path=state_path)
        # persist an entry
        ns._persist_cache_entry("version", {"yunohost": {"version": "9.0"}})
        # create a fresh instance pointing to same state file
        ns2 = node_service.NodeService(repo_root=td, state_path=state_path)
        loaded = ns2._load_persisted_cache_entry("version")
        assert loaded is not None
        assert loaded.get("yunohost", {}).get("version") == "9.0"
