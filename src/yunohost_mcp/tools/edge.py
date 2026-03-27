"""MCP tools for edge/load balancer configuration."""

from __future__ import annotations

import json
from mcp.server.fastmcp import FastMCP


def register_edge_tools(mcp: FastMCP, settings=None):

    @mcp.tool()
    async def ynh_edge_generate_nginx_lb(
        domain: str, backends: str, mode: str = "round_robin"
    ) -> str:
        """Génère une configuration nginx load balancer.
        Args:
            domain: Domaine frontal
            backends: Backends au format JSON (liste de {host, port, weight})
            mode: Algorithme (round_robin, least_conn, ip_hash)
        """
        from nexora_core.edge import generate_nginx_lb_config

        try:
            backend_list = json.loads(backends)
        except json.JSONDecodeError:
            return "❌ Format backends invalide. Attendu: JSON array [{host, port, weight}]"
        result = generate_nginx_lb_config(backend_list, domain, mode=mode)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_edge_generate_haproxy(backends: str, mode: str = "roundrobin") -> str:
        """Génère une configuration HAProxy.
        Args:
            backends: Backends au format JSON
            mode: Algorithme (roundrobin, leastconn, source)
        """
        from nexora_core.edge import generate_haproxy_config

        try:
            backend_list = json.loads(backends)
        except json.JSONDecodeError:
            return "❌ Format backends invalide."
        result = generate_haproxy_config(backend_list, mode=mode)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_edge_dns_failover(
        domain: str, primary_ip: str, secondary_ip: str
    ) -> str:
        """Génère une configuration DNS failover active/passive.
        Args:
            domain: Domaine à protéger
            primary_ip: IP du serveur principal
            secondary_ip: IP du serveur secondaire
        """
        from nexora_core.edge import generate_dns_failover

        result = generate_dns_failover(
            {"node_id": "primary", "ip": primary_ip},
            {"node_id": "secondary", "ip": secondary_ip},
            domain,
        )
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_edge_maintenance_mode(
        domain: str, message: str = "Maintenance en cours"
    ) -> str:
        """Génère une configuration de mode maintenance pour un domaine.
        Args:
            domain: Domaine à mettre en maintenance
            message: Message à afficher
        """
        from nexora_core.edge import generate_maintenance_config

        result = generate_maintenance_config(domain, message)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_edge_network_map() -> str:
        """Génère la carte réseau logique de la flotte."""
        from nexora_core.edge import generate_network_map
        from nexora_core.state import StateStore

        store = StateStore("/opt/nexora/var/state.json")
        state = store.load()
        nodes = [
            {
                "node_id": n.get("node_id"),
                "role": "apps",
                "ip": n.get("hostname", ""),
                "inventory": {},
            }
            for n in state.get("nodes", [])
        ]
        result = generate_network_map(nodes)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_edge_apply_nginx_lb(
        domain: str, backends: str, mode: str = "round_robin"
    ) -> str:
        """[OPERATOR] Génère ET applique une config nginx load balancer, puis recharge nginx.
        Args:
            domain: Domaine frontal
            backends: Backends JSON [{host, port, weight}]
            mode: Algorithme (round_robin, least_conn, ip_hash)
        """
        from nexora_core.edge import generate_nginx_lb_config, apply_nginx_lb

        try:
            backend_list = json.loads(backends)
        except json.JSONDecodeError:
            return "❌ Format backends invalide."
        result = generate_nginx_lb_config(backend_list, domain, mode=mode)
        apply = apply_nginx_lb(result["config"], domain)
        return json.dumps({**result, "applied": apply}, indent=2, ensure_ascii=False)
