from __future__ import annotations

import json
import logging
import subprocess
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _run(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        return subprocess.CompletedProcess(cmd, returncode=127, stdout="", stderr=str(exc))
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, returncode=124, stdout="", stderr=f"Timeout after {timeout}s")


def _run_json(cmd: list[str], timeout: int = 30) -> Dict[str, Any]:
    proc = _run(cmd, timeout=timeout)
    if proc.returncode != 0:
        return {"_error": proc.stderr.strip() or proc.stdout.strip(), "_cmd": cmd}
    try:
        return json.loads(proc.stdout) if proc.stdout.strip() else {}
    except Exception as exc:
        logger.warning(
            "failed to parse YunoHost JSON output",
            extra={"cmd": cmd, "error": str(exc)},
        )
        return {"_raw": proc.stdout.strip(), "_cmd": cmd}


def ynh_version() -> Dict[str, Any]:
    return _run_json(["yunohost", "tools", "version", "--output-as", "json"])


def ynh_settings() -> Dict[str, Any]:
    return _run_json(["yunohost", "settings", "list", "--full", "--output-as", "json"])


def ynh_apps() -> Dict[str, Any]:
    return _run_json(["yunohost", "app", "list", "--output-as", "json"])


def ynh_domains() -> Dict[str, Any]:
    return _run_json(["yunohost", "domain", "list", "--output-as", "json"])


def ynh_certs() -> Dict[str, Any]:
    return _run_json(["yunohost", "domain", "cert", "status", "--output-as", "json"])


def ynh_services() -> Dict[str, Any]:
    return _run_json(["yunohost", "service", "status", "--output-as", "json"])


def ynh_backups() -> Dict[str, Any]:
    return _run_json(["yunohost", "backup", "list", "--output-as", "json"])


def ynh_permissions() -> Dict[str, Any]:
    return _run_json(["yunohost", "user", "permission", "list", "--output-as", "json"])


def ynh_diagnosis() -> Dict[str, Any]:
    return _run_json(["yunohost", "diagnosis", "show", "--output-as", "json"])


def ynh_app_map() -> Dict[str, Any]:
    return _run_json(["yunohost", "app", "map", "--output-as", "json"])


# ── Systemctl fallback for services (no root needed) ─────────────────────

def systemctl_list_units(state: str = "active") -> Dict[str, Any]:
    """List systemd units — readable without root."""
    proc = _run([
        "systemctl", "list-units",
        "--type=service",
        f"--state={state}",
        "--no-pager",
        "--output=json",
    ])
    if proc.returncode == 0 and proc.stdout.strip():
        try:
            units = json.loads(proc.stdout)
            result: Dict[str, Any] = {}
            for u in units:
                name = u.get("unit", "").removesuffix(".service")
                result[name] = {
                    "status": u.get("active", "unknown"),
                    "sub": u.get("sub", ""),
                    "description": u.get("description", ""),
                    "load": u.get("load", ""),
                }
            return result
        except Exception:
            pass

    # Fallback: parse text output
    proc = _run(["systemctl", "list-units", "--type=service", "--no-pager"])
    if proc.returncode != 0:
        return {"_error": proc.stderr.strip()}
    result = {}
    for line in proc.stdout.splitlines():
        parts = line.split()
        if parts and parts[0].endswith(".service"):
            name = parts[0].removesuffix(".service")
            active = parts[2] if len(parts) > 2 else "unknown"
            sub = parts[3] if len(parts) > 3 else ""
            result[name] = {"status": active, "sub": sub, "description": " ".join(parts[4:]) if len(parts) > 4 else ""}
    return result or {"_error": "No services found"}


def systemctl_status(service_name: str) -> Dict[str, Any]:
    """Get detailed status for one systemd service."""
    proc = _run(["systemctl", "is-active", service_name])
    active = proc.stdout.strip()
    proc2 = _run(["systemctl", "show", service_name, "--property=ActiveState,SubState,Description,LoadState,MainPID"])
    props: Dict[str, str] = {}
    for line in proc2.stdout.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            props[k] = v
    return {
        "name": service_name,
        "active": active,
        "status": props.get("ActiveState", active),
        "sub": props.get("SubState", ""),
        "description": props.get("Description", ""),
        "pid": props.get("MainPID", "0"),
        "load": props.get("LoadState", ""),
    }


def services_with_fallback() -> Dict[str, Any]:
    """Return YunoHost services, falling back to systemctl if no root."""
    result = ynh_services()
    if "_error" not in result:
        return result

    # Fallback: systemctl for known YunoHost-related services
    ynh_core_services = [
        "yunohost-api", "metronome", "nginx", "postfix", "dovecot", "rspamd",
        "mysql", "postgresql", "redis-server", "php8.2-fpm", "php8.3-fpm",
        "php7.4-fpm", "slapd", "fail2ban", "ssh", "systemd-resolved",
        "dnsmasq", "bind9", "coturn", "avahi-daemon",
    ]
    services: Dict[str, Any] = {}
    for svc in ynh_core_services:
        info = systemctl_status(svc)
        if info["active"] != "unknown" or info["load"] not in ("", "not-found"):
            services[svc] = {
                "status": info["active"],
                "active": info["active"],
                "description": info["description"],
            }

    if services:
        return services

    # Last resort: list all active services from systemctl
    return systemctl_list_units("active")


# ── YunoHost App Catalog ──────────────────────────────────────────────────

def ynh_app_catalog() -> Dict[str, Any]:
    """Fetch the YunoHost app catalog (requires internet access on server)."""
    return _run_json(["yunohost", "app", "catalog", "--output-as", "json"], timeout=60)


def ynh_app_catalog_filtered(category: str | None = None, query: str | None = None) -> list[Dict[str, Any]]:
    """Return filtered YunoHost catalog apps."""
    raw = ynh_app_catalog()
    if "_error" in raw:
        return []
    # yunohost app catalog returns {"apps": [...]}
    apps_raw = raw.get("apps", raw) if isinstance(raw, dict) else raw
    if isinstance(apps_raw, dict):
        # dict keyed by app_id
        apps: list[Dict[str, Any]] = [{"id": k, **v} for k, v in apps_raw.items()]
    elif isinstance(apps_raw, list):
        apps = list(apps_raw)
    else:
        return []

    if category:
        apps = [a for a in apps if category.lower() in str(a.get("category", "")).lower() or
                category.lower() in [str(t).lower() for t in a.get("tags", [])]]
    if query:
        q = query.lower()
        apps = [a for a in apps if q in str(a.get("id", "")).lower() or
                q in str(a.get("name", "")).lower() or
                q in str(a.get("description", "")).lower()]
    return apps[:200]  # Cap for API responses


def ynh_install_app(
    app_id: str,
    domain: str,
    path: str = "/",
    label: str | None = None,
    args: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    """Install a YunoHost application."""
    cmd = ["yunohost", "app", "install", app_id, "--domain", domain, "--path", path, "--no-ldap", "--output-as", "json"]
    if label:
        cmd.extend(["--label", label])
    # Extra install arguments
    if args:
        for k, v in args.items():
            cmd.extend(["-a", f"{k}={v}"])
    proc = _run(cmd, timeout=300)
    if proc.returncode == 0:
        try:
            return {"success": True, **json.loads(proc.stdout)}
        except Exception:
            pass
        return {"success": True, "output": proc.stdout.strip()}
    return {"success": False, "error": proc.stderr.strip() or proc.stdout.strip()}


def ynh_upgrade_app(app_id: str) -> Dict[str, Any]:
    """Upgrade a YunoHost application."""
    proc = _run(["yunohost", "app", "upgrade", app_id, "--output-as", "json"], timeout=300)
    if proc.returncode == 0:
        return {"success": True, "app_id": app_id, "output": proc.stdout.strip()}
    return {"success": False, "app_id": app_id, "error": proc.stderr.strip()}


def ynh_remove_app(app_id: str, purge: bool = False) -> Dict[str, Any]:
    """Remove a YunoHost application."""
    cmd = ["yunohost", "app", "remove", app_id, "--output-as", "json"]
    if purge:
        cmd.append("--purge")
    proc = _run(cmd, timeout=180)
    if proc.returncode == 0:
        return {"success": True, "app_id": app_id}
    return {"success": False, "app_id": app_id, "error": proc.stderr.strip()}


def ynh_app_info(app_id: str) -> Dict[str, Any]:
    """Get detailed info about an installed app."""
    return _run_json(["yunohost", "app", "info", app_id, "--output-as", "json"])


# ── Service management ────────────────────────────────────────────────

def ynh_service_action(service_name: str, action: str) -> Dict[str, Any]:
    """Start/stop/restart a YunoHost service."""
    if action not in ("start", "stop", "restart", "enable", "disable"):
        return {"success": False, "error": f"Invalid action: {action}"}
    proc = _run(["yunohost", "service", action, service_name, "--output-as", "json"])
    if proc.returncode == 0:
        return {"success": True, "service": service_name, "action": action}
    # Fallback to systemctl
    proc2 = _run(["systemctl", action, service_name])
    return {
        "success": proc2.returncode == 0,
        "service": service_name,
        "action": action,
        "via": "systemctl",
        "error": proc2.stderr.strip() if proc2.returncode != 0 else "",
    }


def ynh_service_logs(service_name: str, lines: int = 100) -> list[str]:
    """Get recent logs for a service via journald."""
    proc = _run(["journalctl", "-u", service_name, "-n", str(lines), "--no-pager", "--output=short-iso"])
    if proc.returncode == 0:
        return proc.stdout.splitlines()
    # Try with sudo
    proc2 = _run(["sudo", "-n", "journalctl", "-u", service_name, "-n", str(lines), "--no-pager"])
    if proc2.returncode == 0:
        return proc2.stdout.splitlines()
    return [f"[Unable to read logs for {service_name}: {proc.stderr.strip()}]"]

