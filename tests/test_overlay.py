
import nexora_node_sdk.overlay as overlay


def test_load_manifest_defaults(tmp_path, monkeypatch):
    # isolate overlay paths to tmp_path
    monkeypatch.setattr(overlay, "OVERLAY_DIR", tmp_path / "overlay")
    monkeypatch.setattr(overlay, "OVERLAY_MANIFEST_PATH", (tmp_path / "overlay") / "manifest.json")
    # ensure no manifest exists
    if overlay.OVERLAY_MANIFEST_PATH.exists():
        overlay.OVERLAY_MANIFEST_PATH.unlink()
    m = overlay.load_manifest()
    assert isinstance(m, dict)
    assert m.get("version") == 1
    assert "created_at" in m and "updated_at" in m
    assert isinstance(m.get("components"), list)
    assert m.get("docker_installed_by_nexora") is False


def test_add_and_remove_component():
    manifest = {"components": []}
    overlay._add_component(manifest, kind="cron", name="job1", detail={"schedule": "*/5 * * * *"})
    assert len(manifest["components"]) == 1
    assert manifest["components"][0]["kind"] == "cron"
    removed = overlay._remove_component(manifest, kind="cron", name="job1")
    assert removed is True
    assert manifest["components"] == []


def test_deploy_overlay_service_writes_files(tmp_path, monkeypatch):
    # isolate directories and stub external commands
    monkeypatch.setattr(overlay, "DOCKER_COMPOSE_DIR", tmp_path / "docker")
    monkeypatch.setattr(overlay, "NGINX_SNIPPETS_DIR", tmp_path / "nginx")
    monkeypatch.setattr(overlay, "OVERLAY_MANIFEST_PATH", tmp_path / "overlay" / "manifest.json")

    def fake_run(cmd, timeout=60):
        return {"ok": True, "out": "ok", "err": ""}

    monkeypatch.setattr(overlay, "_run_cmd", fake_run)
    res = overlay.deploy_overlay_service("svc1", "services: {}")
    assert res["service"] == "svc1"
    assert res["deployed"] is True
    compose_f = overlay.DOCKER_COMPOSE_DIR / "svc1.yml"
    assert compose_f.exists()
    # manifest should include the docker-service entry
    m = overlay.load_manifest()
    svc_entries = [c for c in m.get("components", []) if c["kind"] == "docker-service" and c["name"] == "svc1"]
    assert svc_entries
