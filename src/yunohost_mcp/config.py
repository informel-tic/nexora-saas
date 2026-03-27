from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os
import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


@dataclass
class MCPSettings:
    bind_host: str = "127.0.0.1"
    bind_port: int = 8001
    base_path: str = "/"
    log_level: str = "INFO"
    profile: str = "observer"
    allow_destructive_tools: bool = False
    require_explicit_confirmation: bool = True
    enabled_modules: list[str] = field(
        default_factory=lambda: [
            "app",
            "backup",
            "domain",
            "user",
            "system",
            "pra",
            "security",
            "monitoring",
            "documentation",
            "packaging",
            "fleet",
            "sync",
            "edge",
            "portal",
            "governance",
            "automation",
            "blueprints",
            "docker",
            "failover",
            "storage",
            "notifications",
            "sla",
            "migration",
            "multitenant",
            "hooks",
        ]
    )
    audit_log_path: str = "/var/log/yunohost-mcp-server/audit.log"


def load_settings() -> MCPSettings:
    settings = MCPSettings()
    paths = []
    if os.environ.get("YUNOHOST_MCP_CONFIG"):
        paths.append(Path(os.environ["YUNOHOST_MCP_CONFIG"]))
    paths += [
        Path("/etc/yunohost-mcp-server/config.toml"),
        Path("/opt/yunohost-mcp-server/config.toml"),
        Path("./config.toml"),
    ]
    for path in paths:
        if path.exists() and path.is_file():
            with path.open("rb") as fh:
                data = tomllib.load(fh)
            for key, value in data.items():
                if hasattr(settings, key):
                    setattr(settings, key, value)
            break
    settings.bind_host = os.environ.get("YUNOHOST_MCP_BIND_HOST", settings.bind_host)
    settings.bind_port = int(
        os.environ.get("YUNOHOST_MCP_BIND_PORT", settings.bind_port)
    )
    settings.profile = os.environ.get("YUNOHOST_MCP_PROFILE", settings.profile)
    if os.environ.get("YUNOHOST_MCP_ALLOW_DESTRUCTIVE"):
        settings.allow_destructive_tools = os.environ[
            "YUNOHOST_MCP_ALLOW_DESTRUCTIVE"
        ].lower() in {"1", "true", "yes"}
    return settings
