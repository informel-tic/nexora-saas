"""MCP tools for synchronization between nodes."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from yunohost_mcp.adapter import MCPAdapterContext


def register_sync_tools(mcp: FastMCP, settings=None):
    adapter = MCPAdapterContext.from_environment()

    @mcp.tool()
    async def ynh_fleet_sync_plan(scope: str = "all") -> str:
        """Génère un plan de synchronisation entre le nœud de référence et les cibles.
        Args:
            scope: Périmètre de sync (all, governance, inventory, branding, pra)
        """
        from nexora_core.sync import build_sync_plan

        nodes = adapter.load_nodes()
        if len(nodes) < 2:
            return "Il faut au moins 2 nœuds pour synchroniser."
        ref = {"node_id": nodes[0].get("node_id"), "inventory": {}}
        targets = [{"node_id": n.get("node_id"), "inventory": {}} for n in nodes[1:]]
        plan = build_sync_plan(ref, targets, scope)
        return json.dumps(plan, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_fleet_sync_policy() -> str:
        """Affiche la politique de synchronisation par défaut."""
        from nexora_core.sync import generate_sync_policy

        policy = generate_sync_policy({})
        return json.dumps(policy, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_fleet_sync_branding() -> str:
        """Synchronise le branding/thème du nœud de référence vers les cibles."""
        state = adapter.state_store.load()
        branding = state.get("branding", {})
        nodes = state.get("fleet", {}).get("managed_nodes", [])
        return json.dumps(
            {
                "action": "sync_branding",
                "branding": branding,
                "target_nodes": nodes,
                "status": "plan_generated",
                "note": "Appliquer via l'agent de chaque nœud cible.",
            },
            indent=2,
            ensure_ascii=False,
        )

    @mcp.tool()
    async def ynh_fleet_sync_permissions() -> str:
        """Synchronise les permissions du nœud de référence vers les cibles."""
        perms = adapter.local_inventory().get("permissions", {})
        return json.dumps(
            {
                "action": "sync_permissions",
                "permissions_snapshot": perms,
                "status": "plan_generated",
                "note": "Comparer avec chaque nœud cible avant d'appliquer.",
            },
            indent=2,
            ensure_ascii=False,
        )
