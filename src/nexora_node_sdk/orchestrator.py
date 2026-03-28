"""Orchestrator for node registration and lifecycle actions.

Provides fleet-level node registration and lifecycle coordination
used by both the node SDK and the SaaS control plane.
"""

from __future__ import annotations

import logging
from typing import Any

from .persistence import build_state_repository

logger = logging.getLogger(__name__)


def register_enrolled_node(state_path: str | None = None, *, node_record: dict[str, Any]) -> dict[str, Any]:
    """Register a newly enrolled node in the fleet state."""
    repo = build_state_repository(state_path)
    state = repo.load()
    nodes = state.setdefault("nodes", [])
    node_id = node_record.get("node_id")
    for existing in nodes:
        if isinstance(existing, dict) and existing.get("node_id") == node_id:
            existing.update(node_record)
            repo.save(state)
            return {"status": "updated", "node_id": node_id}
    nodes.append(node_record)
    repo.save(state)
    return {"status": "registered", "node_id": node_id}


def run_lifecycle_action(state_path: str | None = None, *, node_id: str, action: str) -> dict[str, Any]:
    """Execute a lifecycle action on a fleet node."""
    repo = build_state_repository(state_path)
    state = repo.load()
    nodes = state.get("nodes", [])
    for node in nodes:
        if isinstance(node, dict) and node.get("node_id") == node_id:
            node["last_action"] = action
            repo.save(state)
            return {"status": "ok", "node_id": node_id, "action": action}
    return {"status": "not_found", "node_id": node_id, "action": action}


def persistence_status(state_path: str | None = None) -> dict[str, Any]:
    """Expose the active persistence backend status."""
    repo = build_state_repository(state_path)
    return repo.describe()


def placeholder_orchestrator() -> dict[str, Any]:
    return {"status": "stub"}
