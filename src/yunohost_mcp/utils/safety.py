"""Safety classification, input validation and path guards."""

from __future__ import annotations

import re
from pathlib import Path

SAFE_OPERATIONS = {
    "list",
    "info",
    "status",
    "show",
    "map",
    "catalog",
    "suggest",
    "--version",
    "version",
    "disk",
    "settings",
}
MODERATE_OPERATIONS = {
    "create",
    "add",
    "update",
    "install",
    "restart",
    "export",
    "snapshot",
}
DANGEROUS_OPERATIONS = {
    "remove",
    "delete",
    "restore",
    "upgrade",
    "ban",
    "unban",
}

# Patterns matched as regexes (case-insensitive) against the full command text.
_BLOCKED_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\breboot\b", re.I),
    re.compile(r"\bshutdown\b", re.I),
    re.compile(r"\bpoweroff\b", re.I),
    re.compile(r"\brm\s+.*-\s*r.*\s+/\s*$", re.I),
    re.compile(r"\brm\s+.*-\s*r.*\s+/[^a-zA-Z]", re.I),
    re.compile(r"\bmkfs\b", re.I),
    re.compile(r"\bfdisk\b", re.I),
    re.compile(r"\bparted\b", re.I),
    re.compile(r"\bdd\s+if\s*=", re.I),
    re.compile(r"\bchmod\s+777\b", re.I),
    re.compile(r"\bcurl\s.*\|\s*bash", re.I),
    re.compile(r"\bwget\s.*\|\s*bash", re.I),
    re.compile(r"\bsystemctl\s+disable\s+firewall", re.I),
]


def classify_tokens(tokens: tuple[str, ...]) -> str:
    text = " ".join(tokens).lower().strip()
    for pattern in _BLOCKED_PATTERNS:
        if pattern.search(text):
            return "blocked"
    for item in DANGEROUS_OPERATIONS:
        if f" {item}" in f" {text}" or text.endswith(item):
            return "dangerous"
    for item in MODERATE_OPERATIONS:
        if f" {item}" in f" {text}" or text.endswith(item):
            return "moderate"
    return "safe"


# -- Input validation --------------------------------------------------

_RE_SAFE_NAME = re.compile(r"^[a-zA-Z0-9._-]{1,200}$")
_RE_SAFE_IP = re.compile(
    r"^(?:\d{1,3}\.){3}\d{1,3}$"
    r"|^[0-9a-fA-F:]{2,45}$"
)
_RE_SAFE_ALPHANUM = re.compile(r"^[a-zA-Z0-9_-]{1,100}$")


def validate_name(value: str, label: str = "name") -> str:
    """Validate a backup name, app id, service name, etc."""
    if not _RE_SAFE_NAME.match(value):
        raise ValueError(f"Invalid {label}: must be alphanumeric/dash/dot, got {value!r}")
    return value


def validate_ip(value: str) -> str:
    """Validate an IPv4 or IPv6 address."""
    if not _RE_SAFE_IP.match(value):
        raise ValueError(f"Invalid IP address: {value!r}")
    return value


def validate_alphanum(value: str, label: str = "value") -> str:
    """Validate a simple alphanumeric identifier."""
    if not _RE_SAFE_ALPHANUM.match(value):
        raise ValueError(f"Invalid {label}: must be alphanumeric, got {value!r}")
    return value


def validate_positive_int(value: int, label: str = "value", maximum: int = 10000) -> int:
    """Validate a positive bounded integer."""
    if not isinstance(value, int) or value < 1 or value > maximum:
        raise ValueError(f"Invalid {label}: must be 1-{maximum}, got {value!r}")
    return value


# -- Path safety -------------------------------------------------------

_ALLOWED_EXPORT_DIRS = (
    "/tmp/nexora-export",  # nosec B108 - intentional restricted export path
    "/opt/nexora/exports",
)


def validate_output_path(path_str: str) -> Path:
    """Ensure an output path is under an allowed directory."""
    if ".." in path_str:
        raise ValueError(f"Path traversal detected in output path: {path_str!r}")
    path = Path(path_str).resolve()
    allowed = False
    for prefix in _ALLOWED_EXPORT_DIRS:
        prefix_resolved = Path(prefix).resolve()
        try:
            path.relative_to(prefix_resolved)
            allowed = True
            break
        except ValueError:
            continue
    if not allowed:
        safe_name = path.name
        if not _RE_SAFE_NAME.match(safe_name):
            safe_name = "export"
        default_dir = Path(_ALLOWED_EXPORT_DIRS[0])
        default_dir.mkdir(parents=True, exist_ok=True)
        path = default_dir / safe_name
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
