from pathlib import Path
from types import SimpleNamespace

from nexora_node_sdk import models
from nexora_node_sdk import node_actions as na


class FakeState:
    def __init__(self):
        self._data = {}
        self.path = Path("/tmp/state.json")

    def load(self):
        return dict(self._data)

    def save(self, data):
        self._data = dict(data)


class FakeService:
    def __init__(self):
        self.state = FakeState()
        self._inventory = {
            "apps": {"apps": [{"id": "app1"}]},
            "domains": {"domains": ["d1"]},
            "permissions": {"permissions": {"p1": {"allowed": ["u"]}}},
        }

    def invalidate_cache(self):
        return None

    def local_inventory(self):
        return dict(self._inventory)

    def inventory_slice(self, section: str):
        return self._inventory.get(section, {})

    def local_node_summary(self):
        return models.NodeSummary(node_id="n1", hostname="h1", tenant_id="t-1")

    def identity(self):
        return {"node_id": "n1"}

    def compatibility_report(self):
        return {"assessment": {"bootstrap_allowed": True}}

    def dashboard(self):
        return models.DashboardSummary(node=models.NodeSummary(node_id="n1", hostname="h1"))


def test_sanitize_params_redacts_and_truncates():
    params = {
        "password": "secret",
        "config": {"token": "t", "keep": "ok"},
        "long": "x" * 200,
        "list": [1, 2, 3],
    }
    cleaned = na._sanitize_params(params)
    assert isinstance(cleaned, dict)
    assert isinstance(cleaned["password"], dict) and cleaned["password"].get("redacted")
    # opaque container keys (like 'config') are fully redacted
    assert isinstance(cleaned["config"], dict) and cleaned["config"].get("redacted")
    assert isinstance(cleaned["long"], dict) and cleaned["long"].get("truncated")


def test_extract_tenant_id_variants():
    # dict
    assert na._extract_tenant_id({"tenant_id": "t1"}) == "t1"
    # pydantic model
    ns = models.NodeSummary(node_id="n", hostname="h", tenant_id="t2")
    assert na._extract_tenant_id(ns) == "t2"
    # simple object with attribute
    obj = SimpleNamespace(tenant_id="t3")
    assert na._extract_tenant_id(obj) == "t3"


def test_run_inventory_refresh_and_snapshot_persistence():
    svc = FakeService()
    # dry run
    preview = na.run_inventory_refresh(svc, params={}, dry_run=True)
    assert preview.get("snapshot_preview") and preview["changed"] is False

    # actual run
    res = na.run_inventory_refresh(svc, params={}, dry_run=False)
    assert "snapshot" in res
    state = svc.state.load()
    assert "inventory_snapshots" in state and len(state["inventory_snapshots"]) == 1


def test_permissions_sync_dry_and_apply():
    svc = FakeService()
    # dry-run when no desired_state exists
    res = na.run_permissions_sync(svc, params={}, dry_run=True)
    assert res.get("planned_mode") in ("create_baseline", "reconcile_from_local")

    # apply
    res2 = na.run_permissions_sync(svc, params={}, dry_run=False)
    assert res2.get("changed") is True or res2.get("changed") is False
    state = svc.state.load()
    assert "desired_state" in state and "permissions" in state["desired_state"]


def test_docker_compose_apply_validation_and_dry():
    svc = FakeService()
    # missing content
    bad = na.run_docker_compose_apply(svc, params={"content": ""}, dry_run=False)
    assert bad["success"] is False

    # dry run with content
    ok = na.run_docker_compose_apply(svc, params={"content": "a\nb"}, dry_run=True)
    assert ok["line_count"] == 2


def test_execute_unknown_and_blocked_action():
    svc = FakeService()
    engine = na.NodeActionEngine(svc)
    unknown = engine.execute("not-exist", dry_run=True)
    assert unknown.get("success") is False

    # blocked (privileged) action
    blocked = engine.execute("automation/install", dry_run=True)
    assert blocked.get("requires_privileged_runtime") is True
    assert "privileged_plan" in blocked
