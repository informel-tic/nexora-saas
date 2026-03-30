from nexora_node_sdk import privileged_actions


def test_build_privileged_execution_plan_known():
    p = privileged_actions.build_privileged_execution_plan("hooks/install", params={"x": 1})
    assert p["action"] == "hooks/install"
    assert p["requires_privileged_runtime"] is True
    assert "command" in p


def test_build_privileged_execution_plan_unknown():
    p = privileged_actions.build_privileged_execution_plan("unknown/action")
    assert p["action"] == "unknown/action"
    assert p["requires_privileged_runtime"] is True
    assert isinstance(p["params"], dict)
