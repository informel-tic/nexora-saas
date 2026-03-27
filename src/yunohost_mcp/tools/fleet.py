"""MCP tools for fleet management, drift detection and topology."""

from __future__ import annotations

import json
from mcp.server.fastmcp import FastMCP
from yunohost_mcp.adapter import MCPAdapterContext


def register_fleet_tools(mcp: FastMCP, settings=None):
    adapter = MCPAdapterContext.from_environment()

    @mcp.tool()
    async def ynh_fleet_status() -> str:
        """Affiche le statut global de la flotte Nexora.
        Résume les nœuds enregistrés, leurs scores et leur état."""
        return json.dumps(
            adapter.service.fleet_summary().model_dump(), indent=2, ensure_ascii=False
        )

    @mcp.tool()
    async def ynh_fleet_drift_report(
        reference_node: str = "", target_node: str = ""
    ) -> str:
        """Détecte la dérive de configuration entre deux nœuds.
        Args:
            reference_node: ID du nœud de référence (vide = nœud local)
            target_node: ID du nœud cible à comparer
        """
        from nexora_core.fleet import detect_drift

        local_inv = adapter.local_inventory()
        # For now, compare local with itself (multi-node requires agent connectivity)
        drift = detect_drift(local_inv, local_inv)
        return json.dumps(drift, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_fleet_topology() -> str:
        """Génère la topologie de la flotte avec les rôles des nœuds."""
        from nexora_core.fleet import generate_fleet_topology

        nodes = [
            {"node_id": n.get("node_id"), "inventory": {}} for n in adapter.load_nodes()
        ]
        if not nodes:
            return "Aucun nœud enregistré."
        topo = generate_fleet_topology(nodes)
        return json.dumps(topo, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_fleet_compatibility() -> str:
        """Expose le rapport de compatibilité fleet/control-plane."""
        return json.dumps(
            adapter.service.compatibility_report(), indent=2, ensure_ascii=False
        )

    @mcp.tool()
    async def ynh_fleet_lifecycle() -> str:
        """Expose la vue de lifecycle officielle de la flotte."""
        return json.dumps(
            adapter.service.fleet_lifecycle(), indent=2, ensure_ascii=False
        )

    @mcp.tool()
    async def ynh_fleet_enrollment_request(
        requested_by: str = "mcp",
        mode: str = "pull",
        ttl_minutes: int = 30,
        node_id: str = "",
    ) -> str:
        """Émet un token d'enrollement via le service canonique."""
        result = adapter.service.request_enrollment_token(
            requested_by=requested_by,
            mode=mode,
            ttl_minutes=ttl_minutes,
            node_id=node_id or None,
        )
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_fleet_enrollment_attest(
        token: str,
        challenge: str,
        challenge_response: str,
        hostname: str,
        node_id: str,
        agent_version: str = "2.0.0",
        yunohost_version: str = "",
        debian_version: str = "12",
        observed_at: str = "",
    ) -> str:
        """Valide l'attestation d'un nœud via le service canonique."""
        from datetime import datetime, timezone

        result = adapter.service.attest_enrollment(
            token=token,
            challenge=challenge,
            challenge_response=challenge_response,
            hostname=hostname,
            node_id=node_id,
            agent_version=agent_version,
            yunohost_version=yunohost_version,
            debian_version=debian_version,
            observed_at=observed_at or datetime.now(timezone.utc).isoformat(),
        )
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_fleet_enrollment_register(
        token: str,
        hostname: str,
        node_id: str,
        enrollment_mode: str = "pull",
        profile: str = "",
    ) -> str:
        """Finalise l'inscription d'un nœud via le service canonique."""
        result = adapter.service.register_enrolled_node(
            token=token,
            hostname=hostname,
            node_id=node_id,
            enrollment_mode=enrollment_mode,
            profile=profile or None,
            roles=None,
        )
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_fleet_lifecycle_action(
        node_id: str,
        action: str,
        operator: str = "mcp",
        confirmation: bool = False,
    ) -> str:
        """Exécute une action lifecycle via le service canonique."""
        result = adapter.service.run_lifecycle_action(
            node_id=node_id,
            action=action,
            operator=operator,
            confirmation=confirmation,
        )
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_fleet_compare_nodes() -> str:
        """Compare les nœuds enregistrés dans la flotte."""
        nodes = adapter.load_nodes()
        if len(nodes) < 2:
            return "Il faut au moins 2 nœuds pour comparer. Actuellement: " + str(
                len(nodes)
            )
        from nexora_core.fleet import compare_nodes

        result = compare_nodes(
            {"node_id": nodes[0].get("node_id"), "inventory": {}},
            {"node_id": nodes[1].get("node_id"), "inventory": {}},
        )
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_fleet_register_node(
        node_id: str,
        host: str = "",
        port: int = 38121,
        enrollment_mode: str = "push",
        enrolled_by: str = "mcp",
        token_id: str = "",
        agent_version: str = "2.0.0",
        ynh_version: str = "",
        debian_version: str = "",
        target_status: str = "registered",
    ) -> str:
        """Enregistre un nœud distant dans la flotte.
        Args:
            node_id: Identifiant unique du nœud
            host: Adresse IP ou hostname du nœud
            port: Port de l'agent Nexora (défaut: 38121)
            enrollment_mode: push ou pull
            enrolled_by: opérateur ou système ayant déclenché l'enrollement
            token_id: identifiant de jeton par nœud
            agent_version: version de l'agent Nexora
            ynh_version: version YunoHost observée
            debian_version: version Debian observée
            target_status: état cible officiel du nœud
        """
        from yunohost_mcp.utils.safety import validate_name
        from nexora_core.operator_actions import register_fleet_node

        validate_name(node_id, "node_id")
        result = register_fleet_node(
            node_id=node_id,
            host=host or node_id,
            port=port,
            enrollment_mode=enrollment_mode,
            enrolled_by=enrolled_by,
            token_id=token_id or None,
            agent_version=agent_version or None,
            ynh_version=ynh_version or None,
            debian_version=debian_version or None,
            target_status=target_status,
        )
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_fleet_fetch_remote(node_id: str = "") -> str:
        """Récupère l'inventaire d'un nœud distant via son agent Nexora.
        Args:
            node_id: ID du nœud (vide = tous les nœuds enregistrés)
        """
        from nexora_core.fleet import fetch_fleet_inventories

        token = adapter.api_token()
        nodes = adapter.load_nodes()
        if node_id:
            nodes = [n for n in nodes if n.get("node_id") == node_id]
        if not nodes:
            return (
                "Aucun nœud trouvé. Enregistrez d'abord avec ynh_fleet_register_node."
            )
        results = fetch_fleet_inventories(nodes, token)
        return json.dumps(results, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_fleet_drift_remote(reference_node: str, target_node: str) -> str:
        """Détecte la dérive entre deux nœuds distants (via agents).
        Args:
            reference_node: ID du nœud de référence
            target_node: ID du nœud cible
        """
        from nexora_core.fleet import fetch_remote_inventory, detect_drift

        token = adapter.api_token()
        nodes = adapter.load_node_index()
        ref = nodes.get(reference_node)
        tgt = nodes.get(target_node)
        if not ref or not tgt:
            return f"Nœud(s) non trouvé(s). Disponibles: {list(nodes.keys())}"
        ref_inv = fetch_remote_inventory(
            ref.get("hostname", ""), ref.get("agent_port", 38121), token
        )
        tgt_inv = fetch_remote_inventory(
            tgt.get("hostname", ""), tgt.get("agent_port", 38121), token
        )
        if not ref_inv.get("success") or not tgt_inv.get("success"):
            return json.dumps(
                {
                    "error": "Cannot reach one or both nodes",
                    "ref": ref_inv,
                    "tgt": tgt_inv,
                },
                indent=2,
            )
        drift = detect_drift(ref_inv.get("inventory", {}), tgt_inv.get("inventory", {}))
        return json.dumps(drift, indent=2, ensure_ascii=False)
