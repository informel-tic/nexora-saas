"""Minimal orchestrator stub for CI guardrail tests.

This file intentionally contains a small, well-formed stub so
that repository-level static checks that inspect guarded files
can run without requiring the full node SDK implementation.
"""

from __future__ import annotations

from typing import Any


def placeholder_orchestrator() -> dict[str, Any]:
    return {"status": "stub"}
