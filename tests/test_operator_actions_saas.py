import json
import sys

import nexora_saas.operator_actions as op


def test_list_and_summary():
    actions = op.list_supported_agent_actions()
    assert isinstance(actions, list)
    assert "branding/apply" in actions
    summary = op.summarize_agent_capabilities()
    assert "roles" in summary and "actions" in summary
    assert "branding/apply" in summary["actions"]


def test_apply_branding_writes_state_file(tmp_path):
    state_path = tmp_path / "state.json"
    res = op.apply_branding("MyBrand", "blue", state_path=str(state_path))
    assert res["success"] is True
    data = json.loads(state_path.read_text())
    assert data["branding"]["brand_name"] == "MyBrand"
    assert data["branding"]["accent"] == "blue"


def test_sync_branding_handles_exception(monkeypatch):
    class DummyMod:
        def post(self, url, json=None, headers=None, timeout=None):
            raise RuntimeError("boom")

    monkeypatch.setitem(sys.modules, "httpx", DummyMod())
    res = op.sync_branding_to_node("host", 12345, {"k": "v"}, "token")
    assert res["success"] is False
    assert "error" in res


def test_register_fleet_node_minimal(monkeypatch, tmp_path):
    # stub external dependencies imported at module level
    monkeypatch.setattr(op, "assess_compatibility", lambda *a, **k: "compatible")
    monkeypatch.setattr(op, "load_compatibility_matrix", lambda: {})
    monkeypatch.setattr(op, "normalize_node_record", lambda r: dict(r, status="registered"))
    monkeypatch.setattr(op, "transition_node_status", lambda r, target_status: dict(r, status=target_status))
    state_path = tmp_path / "state.json"
    res = op.register_fleet_node("node1", "host1", state_path=str(state_path))
    assert res["success"] is True
    assert res["node_id"] == "node1"
    assert res["status"] == "registered"
    data = json.loads(state_path.read_text())
    assert any(n.get("node_id") == "node1" for n in data["nodes"])
