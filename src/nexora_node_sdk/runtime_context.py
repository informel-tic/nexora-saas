"""Shared runtime context helpers for Nexora node agent."""

from __future__ import annotations

import os
from pathlib import Path

from .node_service import NodeService



def resolve_repo_root(current_file: str) -> Path:
    """Resolve the repository root from an adapter module path.

    In production (pip-installed into a venv), the file hierarchy no longer
    mirrors the source tree.  Callers set ``NEXORA_REPO_ROOT`` to point at
    the extracted source directory (e.g. ``/var/www/nexora/repo``).
    """
    env = os.environ.get("NEXORA_REPO_ROOT")
    if env:
        return Path(env)
    return Path(current_file).resolve().parents[2]


def build_service(current_file: str, state_path: str | None = None) -> NodeService:
    """Build a NodeService instance for the node agent."""

    repo_root = resolve_repo_root(current_file)
    return NodeService(repo_root, state_path or os.environ.get("NEXORA_STATE_PATH"))
