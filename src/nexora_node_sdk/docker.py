"""Docker container management alongside YunoHost apps.

Philosophy: YunoHost apps remain the preferred deployment method.
Docker is for services that have no YNH package or need isolation.
Nexora manages Docker containers through the MCP without breaking YNH.
"""

from __future__ import annotations

import datetime
import json
import subprocess
from pathlib import Path
from typing import Any


def _run(cmd: list[str], timeout: int = 30) -> dict[str, Any]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {
            "success": proc.returncode == 0,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    except FileNotFoundError:
        return {"success": False, "stdout": "", "stderr": "Docker not installed"}
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": f"Timeout after {timeout}s"}


def docker_available() -> bool:
    r = _run(["docker", "version", "--format", "{{.Server.Version}}"])
    return r["success"]


def docker_info() -> dict[str, Any]:
    r = _run(["docker", "info", "--format", "{{json .}}"])
    if not r["success"]:
        return {"available": False, "error": r["stderr"]}
    try:
        info = json.loads(r["stdout"])
        return {
            "available": True,
            "version": info.get("ServerVersion", ""),
            "containers_running": info.get("ContainersRunning", 0),
            "containers_total": info.get("Containers", 0),
            "images": info.get("Images", 0),
            "storage_driver": info.get("Driver", ""),
            "memory_total_mb": round(info.get("MemTotal", 0) / 1024 / 1024),
        }
    except json.JSONDecodeError:
        return {"available": True, "raw": r["stdout"]}


def list_containers(all_containers: bool = False) -> list[dict[str, Any]]:
    fmt = '{"id":"{{.ID}}","name":"{{.Names}}","image":"{{.Image}}","status":"{{.Status}}","ports":"{{.Ports}}","state":"{{.State}}"}'
    cmd = ["docker", "ps", f"--format={fmt}"]
    if all_containers:
        cmd.append("-a")
    r = _run(cmd)
    if not r["success"]:
        return []
    containers = []
    for line in r["stdout"].splitlines():
        if line.strip():
            try:
                containers.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return containers


def container_stats() -> list[dict[str, Any]]:
    fmt = '{"name":"{{.Name}}","cpu":"{{.CPUPerc}}","mem":"{{.MemUsage}}","mem_perc":"{{.MemPerc}}","net":"{{.NetIO}}","block":"{{.BlockIO}}"}'
    r = _run(["docker", "stats", "--no-stream", f"--format={fmt}"])
    if not r["success"]:
        return []
    stats = []
    for line in r["stdout"].splitlines():
        if line.strip():
            try:
                stats.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return stats


def container_logs(name: str, lines: int = 50) -> str:
    r = _run(["docker", "logs", "--tail", str(lines), name], timeout=10)
    return r["stdout"] or r["stderr"]


def generate_compose_file(services: list[dict[str, Any]], project_name: str = "nexora") -> str:
    """Generate a docker-compose.yml from a service list."""
    compose = {
        "version": "3.8",
        "services": {},
        "networks": {
            "nexora_net": {"driver": "bridge"},
        },
    }
    for svc in services:
        name = svc.get("name", "service")
        service_def: dict[str, Any] = {
            "image": svc.get("image", ""),
            "container_name": f"nexora_{name}",
            "restart": svc.get("restart", "unless-stopped"),
            "networks": ["nexora_net"],
        }
        if svc.get("ports"):
            service_def["ports"] = svc["ports"]
        if svc.get("volumes"):
            service_def["volumes"] = svc["volumes"]
        if svc.get("environment"):
            service_def["environment"] = svc["environment"]
        if svc.get("labels"):
            service_def["labels"] = svc["labels"]
        if svc.get("mem_limit"):
            service_def["mem_limit"] = svc["mem_limit"]
        if svc.get("cpus"):
            service_def["cpus"] = svc["cpus"]
        compose["services"][name] = service_def

    import yaml

    return yaml.dump(compose, default_flow_style=False, sort_keys=False)


def generate_nginx_proxy_for_container(container_name: str, domain: str, internal_port: int, *, path: str = "/") -> str:
    """Generate nginx reverse proxy config for a Docker container."""
    return f"""# Nexora Docker proxy: {container_name} -> {domain}{path}
location {path} {{
    proxy_pass http://127.0.0.1:{internal_port};
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}}
"""


# Pre-built Docker service templates for common needs
DOCKER_TEMPLATES = {
    "redis": {
        "image": "redis:7-alpine",
        "ports": ["127.0.0.1:6379:6379"],
        "volumes": ["nexora_redis_data:/data"],
        "mem_limit": "256m",
        "description": "Cache / message broker",
    },
    "postgres": {
        "image": "postgres:16-alpine",
        "ports": ["127.0.0.1:5432:5432"],
        "volumes": ["nexora_pg_data:/var/lib/postgresql/data"],
        "environment": {"POSTGRES_PASSWORD": "__CHANGE_ME__"},
        "mem_limit": "512m",
        "description": "PostgreSQL database",
    },
    "minio": {
        "image": "minio/minio:latest",
        "ports": ["127.0.0.1:9000:9000", "127.0.0.1:9001:9001"],
        "volumes": ["nexora_minio_data:/data"],
        "environment": {
            "MINIO_ROOT_USER": "nexora",
            "MINIO_ROOT_PASSWORD": "__CHANGE_ME__",
        },
        "command": "server /data --console-address :9001",
        "mem_limit": "512m",
        "description": "S3-compatible object storage",
    },
    "uptime-kuma": {
        "image": "louislam/uptime-kuma:1",
        "ports": ["127.0.0.1:3001:3001"],
        "volumes": ["nexora_uptime_data:/app/data"],
        "mem_limit": "256m",
        "description": "Uptime monitoring dashboard",
    },
    "n8n": {
        "image": "n8nio/n8n:latest",
        "ports": ["127.0.0.1:5678:5678"],
        "volumes": ["nexora_n8n_data:/home/node/.n8n"],
        "mem_limit": "512m",
        "description": "Workflow automation",
    },
    "grafana": {
        "image": "grafana/grafana-oss:latest",
        "ports": ["127.0.0.1:3000:3000"],
        "volumes": ["nexora_grafana_data:/var/lib/grafana"],
        "mem_limit": "256m",
        "description": "Monitoring dashboards",
    },
    "prometheus": {
        "image": "prom/prometheus:latest",
        "ports": ["127.0.0.1:9090:9090"],
        "volumes": ["nexora_prom_data:/prometheus"],
        "mem_limit": "512m",
        "description": "Metrics collection",
    },
    "plausible": {
        "image": "plausible/analytics:latest",
        "ports": ["127.0.0.1:8000:8000"],
        "mem_limit": "512m",
        "description": "Privacy-friendly web analytics",
    },
    "portainer": {
        "image": "portainer/portainer-ce:latest",
        "ports": ["127.0.0.1:9443:9443"],
        "volumes": [
            "/var/run/docker.sock:/var/run/docker.sock",
            "nexora_portainer_data:/data",
        ],
        "mem_limit": "256m",
        "description": "Docker management UI",
    },
    "watchtower": {
        "image": "containrrr/watchtower:latest",
        "volumes": ["/var/run/docker.sock:/var/run/docker.sock"],
        "environment": {
            "WATCHTOWER_CLEANUP": "true",
            "WATCHTOWER_SCHEDULE": "0 0 4 * * *",
        },
        "mem_limit": "128m",
        "description": "Auto-update Docker containers",
    },
}


def list_docker_templates() -> list[dict[str, Any]]:
    return [{"name": k, **v} for k, v in DOCKER_TEMPLATES.items()]


def get_docker_template(name: str) -> dict[str, Any] | None:
    return DOCKER_TEMPLATES.get(name)


def estimate_docker_resources(services: list[str]) -> dict[str, Any]:
    total_mem = 0
    details = []
    for svc in services:
        tpl = DOCKER_TEMPLATES.get(svc)
        if tpl:
            mem = int(tpl.get("mem_limit", "256m").rstrip("m"))
            total_mem += mem
            details.append(
                {
                    "service": svc,
                    "mem_mb": mem,
                    "description": tpl.get("description", ""),
                }
            )
        else:
            total_mem += 256
            details.append(
                {
                    "service": svc,
                    "mem_mb": 256,
                    "description": "Custom service (estimate)",
                }
            )

    return {
        "services": details,
        "total_mem_mb": total_mem,
        "recommended_ram_gb": max(2, (total_mem + 1024) // 1024 + 1),
        "timestamp": datetime.datetime.now().isoformat(),
    }


# ── Container lifecycle operations ────────────────────────────────────


def docker_pull(image: str) -> dict[str, Any]:
    r = _run(["docker", "pull", image], timeout=300)
    return {
        "action": "pull",
        "image": image,
        "success": r["success"],
        "output": r["stdout"] or r["stderr"],
    }


def docker_run(
    image: str,
    name: str,
    *,
    ports: list[str] | None = None,
    volumes: list[str] | None = None,
    environment: dict[str, str] | None = None,
    detach: bool = True,
    restart: str = "unless-stopped",
) -> dict[str, Any]:
    cmd = ["docker", "run"]
    if detach:
        cmd.append("-d")
    cmd.extend(["--name", name, "--restart", restart])
    for p in ports or []:
        cmd.extend(["-p", p])
    for v in volumes or []:
        cmd.extend(["-v", v])
    for k, val in (environment or {}).items():
        cmd.extend(["-e", f"{k}={val}"])
    cmd.append(image)
    r = _run(cmd, timeout=120)
    return {
        "action": "run",
        "name": name,
        "image": image,
        "success": r["success"],
        "container_id": r["stdout"][:12] if r["success"] else "",
        "error": r["stderr"],
    }


def docker_start(name: str) -> dict[str, Any]:
    r = _run(["docker", "start", name])
    return {
        "action": "start",
        "name": name,
        "success": r["success"],
        "error": r["stderr"],
    }


def docker_stop(name: str) -> dict[str, Any]:
    r = _run(["docker", "stop", name], timeout=30)
    return {
        "action": "stop",
        "name": name,
        "success": r["success"],
        "error": r["stderr"],
    }


def docker_remove(name: str, force: bool = False) -> dict[str, Any]:
    cmd = ["docker", "rm"]
    if force:
        cmd.append("-f")
    cmd.append(name)
    r = _run(cmd)
    return {
        "action": "remove",
        "name": name,
        "success": r["success"],
        "error": r["stderr"],
    }


def docker_compose_up(compose_path: str, detach: bool = True) -> dict[str, Any]:
    cmd = ["docker", "compose", "-f", compose_path, "up"]
    if detach:
        cmd.append("-d")
    r = _run(cmd, timeout=300)
    return {
        "action": "compose_up",
        "path": compose_path,
        "success": r["success"],
        "output": r["stdout"],
        "error": r["stderr"],
    }


def docker_compose_down(compose_path: str) -> dict[str, Any]:
    r = _run(["docker", "compose", "-f", compose_path, "down"], timeout=60)
    return {
        "action": "compose_down",
        "path": compose_path,
        "success": r["success"],
        "output": r["stdout"],
        "error": r["stderr"],
    }


def write_compose_file(content: str, path: str = "/opt/nexora/docker/docker-compose.yml") -> dict[str, Any]:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return {"written": str(p), "size_bytes": p.stat().st_size}


# ── Docker Hub integration ─────────────────────────────────────────

def docker_hub_search(query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Search Docker Hub for images via the public registry API."""
    import urllib.parse
    import urllib.request

    q = urllib.parse.quote_plus(query.strip())
    url = f"https://hub.docker.com/v2/search/repositories/?query={q}&page_size={min(limit, 100)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "nexora-saas/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        results = data.get("results", [])
        return [
            {
                "name": r.get("repo_name", ""),
                "description": r.get("short_description", ""),
                "official": r.get("is_official", False),
                "automated": r.get("is_automated", False),
                "stars": r.get("star_count", 0),
                "pulls": r.get("pull_count", 0),
            }
            for r in results
        ]
    except Exception as exc:
        return [{"error": str(exc), "query": query}]


def docker_hub_tags(image: str, limit: int = 20) -> list[dict[str, Any]]:
    """List tags for a Docker Hub image."""
    import urllib.request

    # Support namespaced images (org/image) and library images
    parts = image.split("/")
    if len(parts) == 1:
        namespace, repo = "library", parts[0]
    else:
        namespace, repo = parts[0], "/".join(parts[1:])

    url = f"https://hub.docker.com/v2/repositories/{namespace}/{repo}/tags/?page_size={min(limit, 100)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "nexora-saas/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        results = data.get("results", [])
        return [
            {
                "name": t.get("name", ""),
                "size_mb": round(t.get("full_size", 0) / 1024 / 1024, 1),
                "last_updated": t.get("last_updated", ""),
                "digest": t.get("digest", ""),
            }
            for t in results
        ]
    except Exception as exc:
        return [{"error": str(exc), "image": image}]


# ── Container lifecycle management ────────────────────────────────

def docker_restart(name: str) -> dict[str, Any]:
    r = _run(["docker", "restart", name], timeout=30)
    return {"action": "restart", "name": name, "success": r["success"], "error": r["stderr"]}


def docker_inspect(name: str) -> dict[str, Any]:
    r = _run(["docker", "inspect", name])
    if not r["success"]:
        return {"error": r["stderr"]}
    try:
        data = json.loads(r["stdout"])
        return data[0] if data else {}
    except json.JSONDecodeError:
        return {"raw": r["stdout"]}


def container_logs_extended(name: str, lines: int = 100) -> str:
    """Like container_logs but with timestamps and more lines (for streaming)."""
    r = _run(["docker", "logs", "--tail", str(lines), "--timestamps", name], timeout=15)
    return r["stdout"] or r["stderr"]


def container_logs_stream_last(name: str, lines: int = 50) -> list[str]:
    """Return last N log lines as a list for API consumption."""
    raw = container_logs_extended(name, lines)
    return [line for line in raw.splitlines() if line.strip()]


# ── Compose stack management ───────────────────────────────────────

NEXORA_COMPOSE_DIR = Path("/opt/nexora/docker")
NEXORA_COMPOSE_FILE = NEXORA_COMPOSE_DIR / "docker-compose.yml"


def list_compose_stacks() -> list[dict[str, Any]]:
    """List all running compose stacks via `docker compose ls`."""
    r = _run(["docker", "compose", "ls", "--format", "json"])
    if not r["success"]:
        return []
    try:
        return json.loads(r["stdout"])
    except json.JSONDecodeError:
        return []


def get_compose_file_content(path: str | None = None) -> dict[str, Any]:
    """Read the current compose file content."""
    p = Path(path) if path else NEXORA_COMPOSE_FILE
    if not p.exists():
        return {"exists": False, "content": "", "path": str(p)}
    try:
        return {"exists": True, "content": p.read_text(encoding="utf-8"), "path": str(p)}
    except Exception as exc:
        return {"exists": False, "error": str(exc), "path": str(p)}


def apply_compose(content: str, path: str | None = None) -> dict[str, Any]:
    """Write compose content to disk and bring it up."""
    p = Path(path) if path else NEXORA_COMPOSE_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    r = _run(["docker", "compose", "-f", str(p), "up", "-d", "--remove-orphans"], timeout=300)
    return {
        "action": "compose_up",
        "path": str(p),
        "success": r["success"],
        "output": r["stdout"],
        "error": r["stderr"],
    }


def destroy_compose(path: str | None = None, remove_volumes: bool = False) -> dict[str, Any]:
    """Bring compose stack down."""
    p = Path(path) if path else NEXORA_COMPOSE_FILE
    cmd = ["docker", "compose", "-f", str(p), "down"]
    if remove_volumes:
        cmd.append("-v")
    r = _run(cmd, timeout=120)
    return {
        "action": "compose_down",
        "path": str(p),
        "success": r["success"],
        "output": r["stdout"],
        "error": r["stderr"],
    }


# ── Docker system info & cleanup ───────────────────────────────────

def docker_images() -> list[dict[str, Any]]:
    """List local Docker images."""
    fmt = '{"id":"{{.ID}}","repository":"{{.Repository}}","tag":"{{.Tag}}","size":"{{.Size}}","created":"{{.CreatedAt}}"}'
    r = _run(["docker", "images", f"--format={fmt}"])
    if not r["success"]:
        return []
    images = []
    for line in r["stdout"].splitlines():
        if line.strip():
            try:
                images.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return images


def docker_system_prune(dry_run: bool = True) -> dict[str, Any]:
    """Prune unused Docker resources."""
    if dry_run:
        r = _run(["docker", "system", "df"])
        return {"dry_run": True, "disk_usage": r["stdout"]}
    r = _run(["docker", "system", "prune", "-f"], timeout=120)
    return {"action": "prune", "success": r["success"], "output": r["stdout"], "error": r["stderr"]}


def docker_network_list() -> list[dict[str, Any]]:
    """List Docker networks."""
    fmt = '{"id":"{{.ID}}","name":"{{.Name}}","driver":"{{.Driver}}","scope":"{{.Scope}}"}'
    r = _run(["docker", "network", "ls", f"--format={fmt}"])
    if not r["success"]:
        return []
    networks = []
    for line in r["stdout"].splitlines():
        if line.strip():
            try:
                networks.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return networks


def docker_volume_list() -> list[dict[str, Any]]:
    """List Docker volumes."""
    fmt = '{"name":"{{.Name}}","driver":"{{.Driver}}","mountpoint":"{{.Mountpoint}}"}'
    r = _run(["docker", "volume", "ls", f"--format={fmt}"])
    if not r["success"]:
        return []
    volumes = []
    for line in r["stdout"].splitlines():
        if line.strip():
            try:
                volumes.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return volumes


def deploy_from_template(template_name: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Deploy a container from a built-in template with optional overrides."""
    tpl = get_docker_template(template_name)
    if not tpl:
        return {"success": False, "error": f"Template '{template_name}' not found"}
    merged = {**tpl, **(overrides or {})}
    name = f"nexora_{template_name}"
    return docker_run(
        image=merged.get("image", ""),
        name=name,
        ports=merged.get("ports"),
        volumes=merged.get("volumes"),
        environment=merged.get("environment"),
        restart=merged.get("restart", "unless-stopped"),
    )


def get_docker_config() -> dict[str, Any]:
    """Read persisted Docker configuration."""
    cfg_path = NEXORA_COMPOSE_DIR / "nexora-docker.json"
    if not cfg_path.exists():
        return {"registry": "docker.io", "compose_dir": str(NEXORA_COMPOSE_DIR), "auto_update": False}
    try:
        return json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_docker_config(config: dict[str, Any]) -> dict[str, Any]:
    """Persist Docker configuration."""
    NEXORA_COMPOSE_DIR.mkdir(parents=True, exist_ok=True)
    cfg_path = NEXORA_COMPOSE_DIR / "nexora-docker.json"
    # Sanitize: only allow known keys
    safe = {k: v for k, v in config.items() if k in {"registry", "compose_dir", "auto_update", "registry_mirrors", "default_restart"}}
    cfg_path.write_text(json.dumps(safe, indent=2), encoding="utf-8")
    return {"saved": True, "path": str(cfg_path)}
