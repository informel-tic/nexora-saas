"""Fleet management: multi-node inventory, drift detection, topology."""

from __future__ import annotations

import datetime
import time
from typing import Any

from .scoring import compute_health_score, compute_pra_score, compute_security_score


def build_fleet_inventory(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a consolidated fleet inventory from multiple node inventories."""
    all_apps: list[str] = []
    all_domains: list[str] = []
    node_summaries: list[dict[str, Any]] = []

    for node in nodes:
        node_id = node.get("node_id", "unknown")
        inv = node.get("inventory", {})
        apps = inv.get("apps", {}).get("apps", []) if isinstance(inv.get("apps"), dict) else []
        domains = inv.get("domains", {}).get("domains", []) if isinstance(inv.get("domains"), dict) else []
        all_apps.extend(
            [a.get("id", "") for a in apps] if isinstance(apps, list) and apps and isinstance(apps[0], dict) else apps
        )
        all_domains.extend(domains)
        node_summaries.append(
            {
                "node_id": node_id,
                "apps_count": len(apps),
                "domains_count": len(domains),
                "health": compute_health_score(inv),
                "security": compute_security_score(inv),
                "pra": compute_pra_score(inv),
            }
        )

    return {
        "total_nodes": len(nodes),
        "total_apps": len(set(all_apps)),
        "total_domains": len(set(all_domains)),
        "unique_apps": sorted(set(all_apps)),
        "unique_domains": sorted(set(all_domains)),
        "nodes": node_summaries,
        "timestamp": datetime.datetime.now().isoformat(),
    }


def detect_drift(reference: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    """Compare two node inventories and detect configuration drift."""
    drifts: list[dict[str, Any]] = []

    ref_apps = set()
    tgt_apps = set()
    if isinstance(reference.get("apps"), dict):
        for a in reference["apps"].get("apps", []):
            ref_apps.add(a.get("id", "") if isinstance(a, dict) else str(a))
    if isinstance(target.get("apps"), dict):
        for a in target["apps"].get("apps", []):
            tgt_apps.add(a.get("id", "") if isinstance(a, dict) else str(a))
    for app in ref_apps - tgt_apps:
        drifts.append({"category": "apps", "type": "missing_on_target", "item": app})
    for app in tgt_apps - ref_apps:
        drifts.append({"category": "apps", "type": "extra_on_target", "item": app})

    ref_domains = set(
        reference.get("domains", {}).get("domains", []) if isinstance(reference.get("domains"), dict) else []
    )
    tgt_domains = set(target.get("domains", {}).get("domains", []) if isinstance(target.get("domains"), dict) else [])
    for d in ref_domains - tgt_domains:
        drifts.append({"category": "domains", "type": "missing_on_target", "item": d})
    for d in tgt_domains - ref_domains:
        drifts.append({"category": "domains", "type": "extra_on_target", "item": d})

    ref_perms = (
        reference.get("permissions", {}).get("permissions", {})
        if isinstance(reference.get("permissions"), dict)
        else {}
    )
    tgt_perms = (
        target.get("permissions", {}).get("permissions", {}) if isinstance(target.get("permissions"), dict) else {}
    )
    for perm in set(list(ref_perms) + list(tgt_perms)):
        ref_allowed = sorted(
            ref_perms.get(perm, {}).get("allowed", []) if isinstance(ref_perms.get(perm), dict) else []
        )
        tgt_allowed = sorted(
            tgt_perms.get(perm, {}).get("allowed", []) if isinstance(tgt_perms.get(perm), dict) else []
        )
        if ref_allowed != tgt_allowed:
            drifts.append(
                {
                    "category": "permissions",
                    "type": "divergent",
                    "item": perm,
                    "reference": ref_allowed,
                    "target": tgt_allowed,
                }
            )

    severity = "critical" if len(drifts) > 10 else "warning" if len(drifts) > 3 else "info" if drifts else "clean"

    return {
        "drift_count": len(drifts),
        "severity": severity,
        "drifts": drifts,
        "timestamp": datetime.datetime.now().isoformat(),
    }


def generate_fleet_topology(nodes: list[dict[str, Any]], roles: dict[str, str] | None = None) -> dict[str, Any]:
    """Generate a fleet topology map with node roles."""
    roles = roles or {}
    topology: list[dict[str, Any]] = []

    for node in nodes:
        node_id = node.get("node_id", "unknown")
        inv = node.get("inventory", {})
        apps = inv.get("apps", {}).get("apps", []) if isinstance(inv.get("apps"), dict) else []
        domains = inv.get("domains", {}).get("domains", []) if isinstance(inv.get("domains"), dict) else []
        services = inv.get("services", {}) if isinstance(inv.get("services"), dict) else {}

        has_mail = any(s in services for s in ("postfix", "dovecot", "rspamd"))
        has_db = any(s in services for s in ("mysql", "mariadb", "postgresql"))

        auto_role = roles.get(node_id, "apps")
        if has_mail:
            auto_role = "mail"
        if not apps and has_db:
            auto_role = "storage"

        topology.append(
            {
                "node_id": node_id,
                "status": node.get("status", "discovered"),
                "role": auto_role,
                "apps_count": len(apps),
                "domains": domains,
                "capabilities": {
                    "mail": has_mail,
                    "database": has_db,
                    "apps": bool(apps),
                },
            }
        )

    return {
        "nodes": topology,
        "total_nodes": len(topology),
        "roles": list(set(n["role"] for n in topology)),
        "timestamp": datetime.datetime.now().isoformat(),
    }


def compare_nodes(node_a: dict[str, Any], node_b: dict[str, Any]) -> dict[str, Any]:
    """Compare two nodes side by side."""

    def _extract(inv):
        apps = inv.get("apps", {}).get("apps", []) if isinstance(inv.get("apps"), dict) else []
        domains = inv.get("domains", {}).get("domains", []) if isinstance(inv.get("domains"), dict) else []
        return {
            "apps": sorted([a.get("id", str(a)) if isinstance(a, dict) else str(a) for a in apps]),
            "domains": sorted(domains),
            "health": compute_health_score(inv),
            "security": compute_security_score(inv),
            "pra": compute_pra_score(inv),
        }

    a_data = _extract(node_a.get("inventory", {}))
    b_data = _extract(node_b.get("inventory", {}))

    return {
        "node_a": {"node_id": node_a.get("node_id"), **a_data},
        "node_b": {"node_id": node_b.get("node_id"), **b_data},
        "shared_apps": sorted(set(a_data["apps"]) & set(b_data["apps"])),
        "only_a_apps": sorted(set(a_data["apps"]) - set(b_data["apps"])),
        "only_b_apps": sorted(set(b_data["apps"]) - set(a_data["apps"])),
        "shared_domains": sorted(set(a_data["domains"]) & set(b_data["domains"])),
        "timestamp": datetime.datetime.now().isoformat(),
    }


# ── Remote node communication ─────────────────────────────────────────


def build_remote_agent_url(host: str, port: int = 38121, path: str = "/inventory", *, scheme: str = "https") -> str:
    """Build a remote node-agent URL using HTTPS by default."""

    normalized = path if path.startswith("/") else f"/{path}"
    return f"{scheme}://{host}:{port}{normalized}"


def _request_with_retries(
    client: Any,
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    timeout: int,
    retries: int = 3,
    verify: Any = True,
    cert: Any = None,
) -> Any:
    """Execute a client request with simple exponential backoff."""

    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            return client.request(method, url, headers=headers, timeout=timeout, verify=verify, cert=cert)
        except Exception as exc:  # pragma: no cover
            last_error = exc
            if attempt == retries - 1:
                raise
            time.sleep(min(0.1 * (2**attempt), 0.5))
    raise RuntimeError(str(last_error) if last_error else "request failed")


def fetch_remote_inventory(
    host: str,
    port: int = 38121,
    api_token: str = "",
    *,
    timeout: int = 30,
    tls_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch inventory from a remote Nexora node agent over HTTPS."""
    import httpx

    try:
        headers = {}
        if api_token:
            headers["Authorization"] = f"Bearer {api_token}"
        tls_config = tls_config or {"verify": True, "cert": None}
        with httpx.Client() as client:
            resp = _request_with_retries(
                client,
                "GET",
                build_remote_agent_url(host, port, "/inventory"),
                headers=headers,
                timeout=timeout,
                verify=tls_config.get("verify", True),
                cert=tls_config.get("cert"),
            )
        if resp.status_code == 200:
            return {
                "success": True,
                "inventory": resp.json(),
                "host": host,
                "fetched_at": datetime.datetime.now().isoformat(),
            }
        return {"success": False, "status": resp.status_code, "host": host}
    except Exception as e:
        return {"success": False, "error": str(e), "host": host}


def fetch_remote_summary(
    host: str,
    port: int = 38121,
    api_token: str = "",
    *,
    timeout: int = 15,
    tls_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch node summary from a remote agent over HTTPS."""
    import httpx

    try:
        headers = {}
        if api_token:
            headers["Authorization"] = f"Bearer {api_token}"
        tls_config = tls_config or {"verify": True, "cert": None}
        with httpx.Client() as client:
            resp = _request_with_retries(
                client,
                "GET",
                build_remote_agent_url(host, port, "/summary"),
                headers=headers,
                timeout=timeout,
                verify=tls_config.get("verify", True),
                cert=tls_config.get("cert"),
            )
        if resp.status_code == 200:
            return {
                "success": True,
                "summary": resp.json(),
                "host": host,
                "fetched_at": datetime.datetime.now().isoformat(),
            }
        return {"success": False, "status": resp.status_code, "host": host}
    except Exception as e:
        return {"success": False, "error": str(e), "host": host}


def fetch_fleet_inventories(
    nodes: list[dict[str, Any]],
    api_token: str = "",
    tls_config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Fetch inventories from all registered remote nodes."""

    results = []
    for node in nodes:
        host = node.get("hostname", node.get("host", ""))
        port = node.get("agent_port", 38121)
        if host:
            r = fetch_remote_inventory(host, port, api_token, tls_config=tls_config)
            results.append({"node_id": node.get("node_id"), **r})
        else:
            results.append(
                {
                    "node_id": node.get("node_id"),
                    "success": False,
                    "error": "No hostname",
                }
            )
    return results
