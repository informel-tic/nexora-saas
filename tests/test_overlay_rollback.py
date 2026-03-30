import json

import nexora_node_sdk.overlay as overlay


def test_full_overlay_rollback_removes_components(tmp_path, monkeypatch):
    # isolate overlay dirs and manifest
    base = tmp_path / "overlay"
    docker_dir = tmp_path / "docker"
    nginx_dir = tmp_path / "nginx"
    cron_dir = tmp_path / "cron"
    systemd_dir = tmp_path / "systemd"
    for d in (docker_dir, nginx_dir, cron_dir, systemd_dir):
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(overlay, "OVERLAY_DIR", base)
    monkeypatch.setattr(overlay, "OVERLAY_MANIFEST_PATH", base / "manifest.json")
    monkeypatch.setattr(overlay, "DOCKER_COMPOSE_DIR", docker_dir)
    monkeypatch.setattr(overlay, "NGINX_SNIPPETS_DIR", nginx_dir)
    monkeypatch.setattr(overlay, "CRON_DIR", cron_dir)
    monkeypatch.setattr(overlay, "SYSTEMD_DIR", systemd_dir)

    manifest = {
        "version": 1,
        "created_at": "now",
        "updated_at": "now",
        "components": [
            {"kind": "docker-service", "name": "svc1", "detail": {}},
            {"kind": "nginx-snippet", "name": "svc1", "detail": {}},
            {"kind": "cron", "name": "job1", "detail": {}},
            {"kind": "systemd", "name": "unit1", "detail": {}},
        ],
        "docker_installed_by_nexora": True,
        "rollback_safe": True,
    }
    base.mkdir(parents=True, exist_ok=True)
    (docker_dir / "svc1.yml").write_text("services: {}")
    (nginx_dir / "svc1.conf").write_text("server {}")
    (cron_dir / "nexora-job1").write_text("# cron")
    (systemd_dir / "nexora-unit1.service").write_text("[Unit]\nDescription=test")
    overlay.OVERLAY_MANIFEST_PATH.write_text(json.dumps(manifest))

    # stub external commands
    monkeypatch.setattr(overlay, "_run_cmd", lambda *a, **k: {"ok": True, "out": "", "err": ""})
    monkeypatch.setattr(overlay, "stop_all_overlay_containers", lambda: {"stopped": ["svc1"]})

    res = overlay.full_overlay_rollback()
    assert res["rollback_complete"] is True
    removed = res["removed"]
    assert "svc1" in removed["docker_services"]
    assert "svc1" in removed["nginx_snippets"]
    assert "job1" in removed["crons"]
    assert "unit1" in removed["systemd_units"]
    assert "docker-ce" in removed["docker_engine"] or isinstance(removed["docker_engine"], list)
    # overlay dir should be removed
    assert not overlay.OVERLAY_DIR.exists()
