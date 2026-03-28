"""MCP adapter helpers to keep MCP handlers thin and policy-oriented."""

from __future__ import annotations

from dataclasses import dataclass

from nexora_node_sdk.auth import get_api_token
from nexora_node_sdk.state import StateStore
from nexora_saas.orchestrator import NexoraService
from nexora_saas.runtime_context import build_service


@dataclass(slots=True)
class MCPAdapterContext:
    """Shared adapter context for MCP handlers."""

    service: NexoraService
    state_store: StateStore

    @classmethod
    def from_environment(cls) -> "MCPAdapterContext":
        service = build_service(__file__)
        return cls(service=service, state_store=service.state)

    def load_nodes(self) -> list[dict[str, object]]:
        state = self.state_store.load()
        nodes = state.get("nodes", [])
        return nodes if isinstance(nodes, list) else []

    def load_node_index(self) -> dict[str, dict[str, object]]:
        return {str(node.get("node_id")): node for node in self.load_nodes() if node.get("node_id")}

    def api_token(self) -> str:
        return get_api_token()

    def local_inventory(self) -> dict[str, object]:
        return self.service.local_inventory()
