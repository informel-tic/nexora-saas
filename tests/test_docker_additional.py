import json
import sys
import types

import nexora_node_sdk.docker as docker


def test_generate_compose_file_basic(monkeypatch):
    # stub yaml to avoid external dependency
    mod = types.ModuleType("yaml")
    mod.dump = lambda data, default_flow_style=False, sort_keys=False: "services:\n  svc:\n    image: alpine\n"
    monkeypatch.setitem(sys.modules, "yaml", mod)

    services = [{"name": "svc", "image": "alpine", "ports": ["127.0.0.1:123:123"]}]
    yml = docker.generate_compose_file(services)
    assert "services:" in yml
    assert "svc" in yml


def test_generate_nginx_proxy_for_container():
    cfg = docker.generate_nginx_proxy_for_container("nexora_svc", "example.com", 8080, path="/")
    assert "proxy_pass http://127.0.0.1:8080" in cfg
    assert "location /" in cfg


def test_estimate_docker_resources():
    r = docker.estimate_docker_resources(["redis", "custom-service"])
    assert r["total_mem_mb"] == 256 + 256
    assert any(s["service"] == "redis" for s in r["services"])
    assert r["recommended_ram_gb"] >= 2


def test_write_compose_file(tmp_path):
    p = tmp_path / "compose.yml"
    res = docker.write_compose_file("content", path=str(p))
    assert "written" in res and p.exists()


def test_docker_run_monkeypatched(monkeypatch):
    captured = {}

    def fake_run(cmd, timeout=120):
        captured["cmd"] = cmd
        return {"success": True, "stdout": "abcdef1234567890", "stderr": ""}

    monkeypatch.setattr(docker, "_run", fake_run)
    out = docker.docker_run("alpine:latest", "ctr1", ports=["127.0.0.1:1:2"], volumes=["/data:/data"], environment={"K": "V"})
    assert out["success"] is True
    assert out["container_id"] == "abcdef123456"
    assert "docker" in captured["cmd"][0]


def test_docker_info_parses_json(monkeypatch):
    info = {
        "ServerVersion": "20.10.12",
        "ContainersRunning": 2,
        "Containers": 5,
        "Images": 10,
        "Driver": "overlay2",
        "MemTotal": 536870912,
    }

    def fake_run(cmd, timeout=30):
        return {"success": True, "stdout": json.dumps(info), "stderr": ""}

    monkeypatch.setattr(docker, "_run", fake_run)
    r = docker.docker_info()
    assert r["available"] is True
    assert r["version"] == "20.10.12"
    assert r["memory_total_mb"] == 512
