from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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


class HealthService(FakeService):
    def __init__(
        self,
        *,
        status: str = "healthy",
        backups_count: int = 1,
        security_score: int = 80,
        compat_allowed: bool = True,
    ):
        super().__init__()
        self._summary = models.NodeSummary(
            node_id="n1",
            hostname="h1",
            tenant_id="t-1",
            status=status,
            backups_count=backups_count,
            security_score=security_score,
            health_score=42,
        )
        self._compat_allowed = compat_allowed

    def local_node_summary(self):
        return self._summary

    def compatibility_report(self):
        return {"assessment": {"bootstrap_allowed": self._compat_allowed}}


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


def test_sanitize_params_truncates_lists_and_tuples():
    items = list(range(na._MAX_AUDIT_COLLECTION_ITEMS + 5))
    cleaned = na._sanitize_params({"items": items, "flags": ("a", "b")})

    assert len(cleaned["items"]) == na._MAX_AUDIT_COLLECTION_ITEMS + 1
    assert cleaned["items"][-1]["truncated"] == 5
    assert cleaned["flags"]["type"] == "tuple"
    assert cleaned["flags"]["items"][0] == "a"


def test_run_healthcheck_reports_alerts():
    svc = HealthService(status="degraded", backups_count=0, security_score=10, compat_allowed=False)
    res = na.run_healthcheck(svc, params={}, dry_run=False)

    assert res["checks"]["compatibility"] is False
    assert res["checks"]["backups_present"] is False
    assert res["checks"]["security_threshold"] is False
    assert res["checks"]["status_healthy"] is False
    assert "Compatibility policy blocks bootstrap or mutations" in res["alerts"]
    assert "No backups detected" in res["alerts"]
    assert "Node status is degraded" in res["alerts"]
    assert res["health_score"] == 42


def test_run_branding_apply_dry_run_and_failure():
    svc = FakeService()
    svc.state.save({"branding": {"brand_name": "Acme", "accent": "#123456"}})

    with patch("nexora_node_sdk.node_actions.apply_branding") as apply_branding:
        preview = na.run_branding_apply(svc, params={}, dry_run=True)

    assert preview["changed"] is False
    assert preview["branding"]["brand_name"] == "Acme"
    apply_branding.assert_not_called()

    with patch(
        "nexora_node_sdk.node_actions.apply_branding",
        return_value={"success": False, "error": "boom"},
    ):
        result = na.run_branding_apply(svc, params={}, dry_run=False)

    assert result["success"] is False
    assert result["error"] == "boom"
    assert "boom" in result.get("errors", [])


def test_run_pra_snapshot_dry_run_and_persist():
    svc = FakeService()
    restore_plan = {"steps": ["restore-1"]}

    with patch("nexora_node_sdk.node_actions.compute_pra_score", return_value={"score": 80}), patch(
        "nexora_node_sdk.node_actions.executive_report", return_value={"summary": "ok"}
    ), patch("nexora_node_sdk.node_actions.build_restore_plan", return_value=restore_plan):
        preview = na.run_pra_snapshot(svc, params={"snapshot_id": "snap-1"}, dry_run=True)

    assert preview["changed"] is False
    assert preview["snapshot_preview"]["snapshot_id"] == "snap-1"
    assert "pra_snapshots" not in svc.state.load()

    with patch("nexora_node_sdk.node_actions.compute_pra_score", return_value={"score": 90}), patch(
        "nexora_node_sdk.node_actions.executive_report", return_value={"summary": "ok"}
    ), patch("nexora_node_sdk.node_actions.build_restore_plan", return_value=restore_plan):
        result = na.run_pra_snapshot(svc, params={"snapshot_id": "snap-2"}, dry_run=False)

    assert result["changed"] is True
    state = svc.state.load()
    assert state["pra_snapshots"][0]["snapshot_id"] == "snap-2"


def test_maintenance_actions_dry_run_and_apply():
    svc = FakeService()

    with patch("nexora_node_sdk.node_actions.apply_maintenance_mode") as apply_mode, patch(
        "nexora_node_sdk.node_actions.remove_maintenance_mode"
    ) as remove_mode:
        preview_enable = na.run_maintenance_enable(svc, params={"domain": "ex.com"}, dry_run=True)
        preview_disable = na.run_maintenance_disable(svc, params={"domain": "ex.com"}, dry_run=True)

    assert preview_enable["maintenance_mode"] == "enable"
    assert preview_disable["maintenance_mode"] == "disable"
    apply_mode.assert_not_called()
    remove_mode.assert_not_called()

    with patch(
        "nexora_node_sdk.node_actions.apply_maintenance_mode",
        return_value={"success": True},
    ) as apply_mode, patch(
        "nexora_node_sdk.node_actions.remove_maintenance_mode",
        return_value={"success": True},
    ) as remove_mode:
        applied_enable = na.run_maintenance_enable(svc, params={"domain": "ex.com"}, dry_run=False)
        applied_disable = na.run_maintenance_disable(svc, params={"domain": "ex.com"}, dry_run=False)

    assert applied_enable["changed"] is True
    assert applied_disable["changed"] is True
    assert apply_mode.called
    assert remove_mode.called


def test_execute_validates_required_params_and_records_event():
    svc = FakeService()
    engine = na.NodeActionEngine(svc)
    result = engine.execute("maintenance/enable", dry_run=True, params={})

    assert result["success"] is False
    assert "Missing required parameter(s): domain" in result["error"]

    state = svc.state.load()
    assert state["node_action_events"][0]["action"] == "maintenance/enable"
    assert state["node_action_events"][0]["success"] is False


def test_execute_rejects_oversized_payload():
    svc = FakeService()
    engine = na.NodeActionEngine(svc)
    limit = na.ACTION_SPECS["docker/compose/apply"].max_payload_bytes
    assert limit is not None

    result = engine.execute(
        "docker/compose/apply",
        dry_run=True,
        params={"content": "x" * (limit + 1)},
    )

    assert result["success"] is False
    assert "Payload exceeds configured capacity limit" in result["error"]


def test_execute_sanitizes_params_in_audit_and_state():
    svc = FakeService()
    engine = na.NodeActionEngine(svc)
    result = engine.execute("inventory/refresh", dry_run=True, params={"password": "secret"})

    assert result["audit"]["params"]["password"]["redacted"] is True
    state = svc.state.load()
    assert state["node_action_events"][0]["params"]["password"]["redacted"] is True
