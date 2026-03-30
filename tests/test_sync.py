
from nexora_node_sdk import sync


def test_build_sync_plan_permissions_and_apps():
    reference = {
        "node_id": "ref-1",
        "inventory": {
            "permissions": {"permissions": {"perm_add": {"allowed": ["a"]}, "perm_update": {"allowed": ["x", "y"]}}},
            "apps": {"apps": [{"id": "app1"}, {"id": "app2"}]},
        },
    }
    target = {
        "node_id": "t-1",
        "inventory": {
            "permissions": {"permissions": {"perm_update": {"allowed": ["y", "z"]}}},
            "apps": {"apps": [{"id": "app2"}]},
        },
    }
    plan = sync.build_sync_plan(reference, [target], sync_scope="all")
    assert plan["reference_node"] == "ref-1"
    assert plan["scope"] == "all"
    assert plan["total_actions"] >= 1
    actions = plan["targets"][0]["actions"]
    # Expect add_permission for perm_add, update_permission for perm_update, install_app for app1
    types = {a["type"] for a in actions}
    assert "add_permission" in types
    assert "update_permission" in types
    assert "install_app" in types


def test_build_sync_plan_scope_filtering():
    reference = {"node_id": "r", "inventory": {"apps": {"apps": [{"id": "a1"}]}}}
    target = {"node_id": "t", "inventory": {"apps": {"apps": []}}}
    plan_all = sync.build_sync_plan(reference, [target], sync_scope="inventory")
    assert any(a["type"] == "install_app" for a in plan_all["targets"][0]["actions"])
    plan_governance = sync.build_sync_plan(reference, [target], sync_scope="governance")
    # governance-only should not include install_app
    assert not any(a["type"] == "install_app" for a in plan_governance["targets"][0]["actions"])


def test_build_sync_plan_invalid_scope_defaults_to_all():
    plan = sync.build_sync_plan({"node_id": "r"}, [], sync_scope="bogus")
    assert plan["scope"] == "all"


def test_generate_sync_policy_and_job_and_conflicts():
    settings = {"auto_sync": True, "sync_interval": 30}
    policy = sync.generate_sync_policy(settings)
    assert policy["version"] == "1.0"
    assert "sync_scopes" in policy
    job = sync.build_sync_job(policy, mode="execute")
    assert job["mode"] == "execute"
    assert job["status"] == "queued"

    ref = {"a": 1, "b": 2}
    tgt = {"a": 1, "b": 3}
    conflicts = sync.detect_sync_conflicts(ref, tgt)
    assert any(c["key"] == "b" for c in conflicts)


def test_detect_sync_conflicts_no_conflicts():
    a = {"x": 1}
    b = {"x": 1}
    assert sync.detect_sync_conflicts(a, b) == []
