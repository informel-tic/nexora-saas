"""App migration between nodes — backup on source, restore on target."""

from __future__ import annotations

import datetime
import os
import json
import subprocess
import uuid
from pathlib import Path
from typing import Any

_DEFAULT_MIGRATION_STATE_FILE = Path("/opt/nexora/var/migration_state.json")


def _resolve_migration_state_file() -> Path:
    override = os.environ.get("NEXORA_MIGRATION_STATE_PATH", "").strip()
    if override:
        return Path(override)
    state_hint = os.environ.get("NEXORA_STATE_PATH", "").strip()
    if state_hint:
        hint_path = Path(state_hint)
        base_dir = hint_path.parent if hint_path.suffix else hint_path
        return base_dir / "migration_state.json"
    return _DEFAULT_MIGRATION_STATE_FILE


def _load_state() -> dict[str, Any]:
    try:
        state_file = _resolve_migration_state_file()
        if state_file.exists():
            return json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"jobs": {}}


def _save_state(state: dict[str, Any]) -> None:
    state_file = _resolve_migration_state_file()
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


def _run(cmd: list[str], timeout: int = 300) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        return subprocess.CompletedProcess(cmd, returncode=127, stdout="", stderr=str(exc))
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, returncode=124, stdout="", stderr=f"Timeout after {timeout}s")


# ── Job management ────────────────────────────────────────────────────────


def list_migration_jobs() -> list[dict[str, Any]]:
    """List all migration jobs."""
    state = _load_state()
    return list(state.get("jobs", {}).values())


def get_migration_status(job_id: str) -> dict[str, Any] | None:
    """Get status of a specific migration job."""
    state = _load_state()
    return state.get("jobs", {}).get(job_id)


def create_migration_job(
    app_id: str,
    source_node_id: str,
    target_node_id: str,
    target_domain: str | None = None,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a migration job record."""
    state = _load_state()
    if "jobs" not in state:
        state["jobs"] = {}

    job_id = str(uuid.uuid4())[:12]
    job: dict[str, Any] = {
        "job_id": job_id,
        "app_id": app_id,
        "source_node_id": source_node_id,
        "target_node_id": target_node_id,
        "target_domain": target_domain,
        "options": options or {},
        "status": "pending",
        "steps": [],
        "created_at": datetime.datetime.now().isoformat(),
        "updated_at": datetime.datetime.now().isoformat(),
    }
    state["jobs"][job_id] = job
    _save_state(state)
    return job


def _update_job(job_id: str, **kwargs: Any) -> dict[str, Any]:
    state = _load_state()
    job = state.get("jobs", {}).get(job_id)
    if not job:
        return {"error": f"Job {job_id} not found"}
    job.update(kwargs)
    job["updated_at"] = datetime.datetime.now().isoformat()
    state["jobs"][job_id] = job
    _save_state(state)
    return job


def _add_step(job_id: str, step: str, status: str, detail: str = "") -> None:
    state = _load_state()
    job = state.get("jobs", {}).get(job_id)
    if job:
        job.setdefault("steps", []).append({
            "step": step,
            "status": status,
            "detail": detail,
            "timestamp": datetime.datetime.now().isoformat(),
        })
        state["jobs"][job_id] = job
        _save_state(state)


# ── YunoHost-native backup/restore migration ─────────────────────────────


def _ynh_backup_app(app_id: str, backup_name: str) -> dict[str, Any]:
    """Create a YunoHost backup for a single app."""
    proc = _run(
        ["yunohost", "backup", "create", "--apps", app_id, "--name", backup_name, "--output-as", "json"],
        timeout=600,
    )
    if proc.returncode == 0:
        return {"success": True, "backup_name": backup_name}
    return {"success": False, "error": proc.stderr.strip() or proc.stdout.strip()}


def _ynh_backup_list() -> list[str]:
    """List available YunoHost backups."""
    proc = _run(["yunohost", "backup", "list", "--output-as", "json"])
    if proc.returncode == 0:
        try:
            data = json.loads(proc.stdout)
            return list(data.get("archives", {}).keys()) if isinstance(data, dict) else []
        except Exception:
            pass
    return []


def _rsync_backup_to_target(backup_name: str, target_host: str) -> dict[str, Any]:
    """rsync the backup archive to target node."""
    src = f"/home/yunohost.backup/archives/{backup_name}.tar.gz"
    dst = f"{target_host}:/home/yunohost.backup/archives/"
    proc = _run(
        ["rsync", "-az", "--progress", "-e", "ssh -o StrictHostKeyChecking=no", src, dst],
        timeout=600,
    )
    return {
        "success": proc.returncode == 0,
        "error": proc.stderr.strip() if proc.returncode != 0 else "",
    }


def _ynh_restore_on_target(target_host: str, backup_name: str, app_id: str) -> dict[str, Any]:
    """SSH to target node and restore the backup."""
    cmd = [
        "ssh", "-o", "StrictHostKeyChecking=no", target_host,
        f"yunohost backup restore {backup_name} --apps {app_id} --force --output-as json",
    ]
    proc = _run(cmd, timeout=600)
    if proc.returncode == 0:
        return {"success": True}
    return {"success": False, "error": proc.stderr.strip() or proc.stdout.strip()}


# ── Main execution ────────────────────────────────────────────────────────


def execute_migration(job_id: str, target_ssh_host: str | None = None) -> dict[str, Any]:
    """
    Execute a migration job step-by-step:
    1. Create YunoHost backup of app on source (local)
    2. rsync backup to target node
    3. Restore app on target via SSH
    4. (Optional) Update DNS/nginx

    Returns the updated job record.

    NOTE: This runs synchronously. In production, use a background thread/task.
    """
    job = get_migration_status(job_id)
    if not job:
        return {"error": f"Job {job_id!r} not found"}

    if job["status"] not in ("pending", "failed"):
        return {"error": f"Job is already in state: {job['status']}", "job": job}

    app_id = job["app_id"]
    source = job.get("source_node_id", "local")
    target = job.get("target_node_id", "")
    target_host = target_ssh_host or target  # e.g. "192.168.1.200" or "backup-node.local"

    _update_job(job_id, status="running")

    # Step 1: backup
    backup_name = f"nexora-migration-{app_id}-{job_id}"
    _add_step(job_id, "backup", "running", f"Creating backup '{backup_name}'")
    backup_result = _ynh_backup_app(app_id, backup_name)
    if not backup_result["success"]:
        _add_step(job_id, "backup", "failed", backup_result.get("error", ""))
        return _update_job(job_id, status="failed", error=backup_result.get("error", "Backup failed"))
    _add_step(job_id, "backup", "done", backup_name)

    # Step 2: rsync to target
    if target_host and source != target_host:
        _add_step(job_id, "rsync", "running", f"Transferring backup to {target_host}")
        rsync_result = _rsync_backup_to_target(backup_name, target_host)
        if not rsync_result["success"]:
            _add_step(job_id, "rsync", "failed", rsync_result.get("error", ""))
            return _update_job(job_id, status="failed", error=rsync_result.get("error", "rsync failed"))
        _add_step(job_id, "rsync", "done", f"Backup at {target_host}")

        # Step 3: restore on target
        _add_step(job_id, "restore", "running", f"Restoring {app_id} on {target_host}")
        restore_result = _ynh_restore_on_target(target_host, backup_name, app_id)
        if not restore_result["success"]:
            _add_step(job_id, "restore", "failed", restore_result.get("error", ""))
            return _update_job(job_id, status="failed", error=restore_result.get("error", "Restore failed"))
        _add_step(job_id, "restore", "done", "App restored on target")
    else:
        _add_step(job_id, "restore", "skipped", "Local migration — no transfer needed (same node)")

    # Done
    _add_step(job_id, "complete", "done", "Migration complete")
    return _update_job(
        job_id,
        status="completed",
        completed_at=datetime.datetime.now().isoformat(),
        backup_name=backup_name,
    )


# ── App discovery for UI ──────────────────────────────────────────────────


def list_migratable_apps() -> list[dict[str, Any]]:
    """List apps installed on this node that can be migrated."""
    proc = _run(["yunohost", "app", "list", "--output-as", "json"])
    if proc.returncode != 0:
        return []
    try:
        data = json.loads(proc.stdout)
        apps = data.get("apps", []) if isinstance(data, dict) else []
        return [
            {
                "id": a.get("id", ""),
                "name": a.get("label", a.get("id", "")),
                "domain": a.get("domain", ""),
                "path": a.get("path", "/"),
                "description": a.get("description", ""),
                "version": a.get("version", ""),
                "migratable": True,
            }
            for a in apps
        ]
    except Exception:
        return []
