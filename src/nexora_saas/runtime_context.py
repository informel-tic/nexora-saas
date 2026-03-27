"""Shared runtime context helpers for Nexora SaaS control plane."""

from __future__ import annotations

import os

from nexora_node_sdk.runtime_context import resolve_repo_root

from .orchestrator import NexoraService


def build_service(current_file: str, state_path: str | None = None) -> NexoraService:
    """Build a NexoraService instance for the SaaS control plane."""

    repo_root = resolve_repo_root(current_file)
    return NexoraService(repo_root, state_path or os.environ.get("NEXORA_STATE_PATH"))
