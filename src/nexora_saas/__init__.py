"""Nexora SaaS control-plane package.

This package contains modules exclusive to the SaaS control plane:
fleet orchestration, enrollment issuance, governance, multi-tenancy,
quotas, and operator tooling.

It depends on ``nexora_node_sdk`` for shared domain modules.
"""

from __future__ import annotations

__all__ = ["NexoraService"]


def __getattr__(name: str):
    """Lazy-load heavy exports."""

    if name == "NexoraService":
        from .orchestrator import NexoraService

        return NexoraService
    raise AttributeError(name)
