import re
from pathlib import Path
import datetime

import nexora_node_sdk.edge as edge


def test_generate_nginx_lb_config_modes_and_health():
    backends = [
        {"host": "10.0.0.1", "port": 8080, "weight": 2},
        {"host": "10.0.0.2", "port": 8080, "backup": True},
    ]
    r = edge.generate_nginx_lb_config(backends, "example.com", mode="least_conn", health_check=True)
    assert r["domain"] == "example.com"
    assert r["backend_count"] == 2
    cfg = r["config"]
    assert "upstream example_com" in cfg
    assert "least_conn;" in cfg
    assert "server 10.0.0.1:8080 weight=2;" in cfg
    assert "backup" in cfg
    assert "/api/health" in cfg


def test_generate_haproxy_config_and_dns_and_network_map():
    backends = [{"host": "1.1.1.1", "port": 80}, {"host": "2.2.2.2", "port": 8080, "backup": True, "check": False}]
    hap = edge.generate_haproxy_config(backends, frontend_name="front", mode="leastconn")
    assert "balance leastconn" in hap["config"]
    assert "server node0 1.1.1.1:80" in hap["config"]

    dns = edge.generate_dns_failover({"ip": "1.2.3.4", "node_id": "p"}, {"ip": "5.6.7.8", "node_id": "s"}, "ex.com")
    assert dns["domain"] == "ex.com"
    assert any(r["priority"] == "primary" for r in dns["records"]) 

    nodes = [{"node_id": "n1", "role": "apps", "ip": "1.2.3.4", "inventory": {"domains": {"domains": ["ex.com"]}}}]
    nm = edge.generate_network_map(nodes, edges=None)
    assert nm["total_nodes"] == 1
    assert nm["nodes"][0]["domains"] == ["ex.com"]


def test_resolve_nginx_domain_dir_invalid_and_apply(tmp_path, monkeypatch):
    # invalid domain raises
    try:
        edge._resolve_nginx_domain_dir("BAD/DOMAIN")
    except ValueError:
        pass

    # apply_nginx_lb: success and failure paths
    target_dir = tmp_path / "nginx.d"
    target_dir.mkdir()

    def fake_resolve(domain):
        return target_dir

    monkeypatch.setattr(edge, "_resolve_nginx_domain_dir", fake_resolve)

    class FakeProc:
        def __init__(self, returncode=0, stderr=""):
            self.returncode = returncode
            self.stderr = stderr

    # success: nginx -t returns 0
    monkeypatch.setattr(edge._sp, "run", lambda *a, **k: FakeProc(0))
    ok = edge.apply_nginx_lb("cfg", "ex.com")
    assert ok["success"] is True
    p = Path(ok["path"])
    assert p.exists()

    # failure: nginx -t returns non-zero and file is removed
    def fake_run_fail(*a, **k):
        # first call is nginx -t -> fail
        return FakeProc(1, stderr="Err")

    monkeypatch.setattr(edge._sp, "run", fake_run_fail)
    res = edge.apply_nginx_lb("cfg", "ex.com")
    assert res["success"] is False
    assert "nginx -t failed" in res.get("error", "") or "Err" in res.get("error", "")
