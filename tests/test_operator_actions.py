import json

from nexora_node_sdk import operator_actions


def test_list_and_summarize_actions():
    lst = operator_actions.list_supported_agent_actions()
    assert isinstance(lst, list)
    summary = operator_actions.summarize_agent_capabilities()
    assert "roles" in summary and "actions" in summary


def test_restart_and_backup_mock_and_apply_branding_and_register_node(tmp_path):
    orig = operator_actions._ynh
    try:
        # Mock _ynh to simulate successful backup list and operations
        operator_actions._ynh = lambda *a, **k: {"success": True, "data": {"archives": ["b1", "b2"]}}
        r = operator_actions.restart_service("dummy")
        assert r["action"] == "restart_service"
        # create_backup should report success because _ynh mocked as success
        b = operator_actions.create_backup(name="tst", description="d", apps="")
        assert b["action"] == "create_backup"
        assert b["success"] is True

        # apply_branding writes to the provided state file
        state_file = tmp_path / "state.json"
        res = operator_actions.apply_branding("AcmeBrand", "#abc", state_path=str(state_file))
        assert res["success"] is True
        data = json.loads(state_file.read_text(encoding="utf-8"))
        assert "branding" in data

        # register a fleet node and ensure state file updated
        reg = operator_actions.register_fleet_node(
            node_id="node-x",
            host="host.local",
            state_path=str(state_file),
            enrollment_mode="push",
            enrolled_by="tester",
            target_status="bootstrap_pending",
        )
        assert reg["success"] is True
        assert reg["node_id"] == "node-x"
        saved = json.loads(state_file.read_text(encoding="utf-8"))
        assert any(n.get("node_id") == "node-x" for n in saved.get("nodes", []))
    finally:
        operator_actions._ynh = orig


def test_sync_branding_to_node_failure():
    # Expect failure when host unreachable / httpx raises
    out = operator_actions.sync_branding_to_node("no-such-host", 1234, {"b": 1}, api_token="t")
    assert out["success"] is False
