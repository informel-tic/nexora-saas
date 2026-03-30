
from nexora_node_sdk import preflight


def test_build_install_preflight_blocked(monkeypatch):
    # compatibility denies install; domain path already used; no backups; unhealthy services; public permissions
    monkeypatch.setattr(
        preflight,
        "assess_compatibility",
        lambda *a, **k: {"capability_verdicts": {"install_app": {"allowed": False, "reasons": ["unsupported"]}}},
    )
    monkeypatch.setattr(preflight, "load_compatibility_matrix", lambda: {})
    monkeypatch.setattr(preflight.yh_adapter, "ynh_app_map", lambda: {"example.com": {"/": "existing_app"}})
    monkeypatch.setattr(preflight.yh_adapter, "ynh_backups", lambda: {})
    monkeypatch.setattr(preflight.yh_adapter, "ynh_services", lambda: {"services": {"db": {"status": "stopped"}}})
    monkeypatch.setattr(preflight.yh_adapter, "ynh_permissions", lambda: {"permissions": {"app1": {"allowed": ["visitors"]}}})

    report = preflight.build_install_preflight("nextcloud", "example.com", "/")
    assert report["status"] == "blocked"
    assert not report["allowed"]
    assert any(b.startswith("compatibility:") for b in report["blocking_issues"]) or "compatibility:unsupported" in report["blocking_issues"]
    assert any("path_already_used" in b for b in report["blocking_issues"])
    assert "no_backup_detected" in report["warnings"]
    assert any(w.startswith("unhealthy_services:") for w in report["warnings"])
    assert any(w.startswith("public_permissions:") for w in report["warnings"])


def test_build_install_preflight_allowed(monkeypatch):
    # compatibility allows install, backups present, no collisions, services healthy
    monkeypatch.setattr(
        preflight,
        "assess_compatibility",
        lambda *a, **k: {"capability_verdicts": {"install_app": {"allowed": True}}},
    )
    monkeypatch.setattr(preflight, "load_compatibility_matrix", lambda: {})
    monkeypatch.setattr(preflight.yh_adapter, "ynh_app_map", lambda: {})
    monkeypatch.setattr(preflight.yh_adapter, "ynh_backups", lambda: {"archives": ["b1"]})
    monkeypatch.setattr(preflight.yh_adapter, "ynh_services", lambda: {"services": {"db": {"status": "running"}}})
    monkeypatch.setattr(preflight.yh_adapter, "ynh_permissions", lambda: {"permissions": {}})

    report = preflight.build_install_preflight("nextcloud", "ok.example", "/")
    assert report["status"] == "allowed"
    assert report["allowed"] is True
    assert report["blocking_issues"] == []
