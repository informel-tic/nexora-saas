"""MCP tools for application failover."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP


def register_failover_tools(mcp: FastMCP, settings=None):

    @mcp.tool()
    async def ynh_failover_list_strategies() -> str:
        """Liste les stratégies de health check disponibles."""
        from nexora_node_sdk.failover import list_health_check_strategies

        return json.dumps(list_health_check_strategies(), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_failover_generate_pair(app_id: str, domain: str, primary_host: str, secondary_host: str) -> str:
        """Génère une configuration failover active/passive pour une app.
        Args:
            app_id: Identifiant de l'application
            domain: Domaine frontal
            primary_host: Host:port du serveur principal
            secondary_host: Host:port du serveur secondaire
        """
        from nexora_node_sdk.failover import generate_failover_pair

        result = generate_failover_pair(
            app_id,
            {"node_id": "primary", "host": primary_host},
            {"node_id": "secondary", "host": secondary_host},
            domain,
        )
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_failover_generate_nginx(app_id: str, domain: str, primary_host: str, secondary_host: str) -> str:
        """Génère une configuration nginx avec failover automatique.
        Args:
            app_id: Identifiant de l'app
            domain: Domaine
            primary_host: Backend principal (host:port)
            secondary_host: Backend secondaire (host:port)
        """
        from nexora_node_sdk.failover import generate_failover_nginx_config

        return generate_failover_nginx_config(app_id, primary_host, secondary_host, domain)

    @mcp.tool()
    async def ynh_failover_plan() -> str:
        """Génère un plan de failover pour les apps critiques du serveur."""
        from nexora_node_sdk.failover import generate_failover_plan
        from yunohost_mcp.utils.runner import run_ynh_command

        result = await run_ynh_command("app", "list")
        apps = []
        if result.success and isinstance(result.data, dict):
            for a in result.data.get("apps", []):
                apps.append(
                    {
                        "id": a.get("id"),
                        "domain": a.get("domain_path", "").split("/")[0],
                        "critical": True,
                    }
                )
        from nexora_node_sdk.state import StateStore

        store = StateStore("/opt/nexora/var/state.json")
        state = store.load()
        nodes = [{"node_id": n.get("node_id")} for n in state.get("nodes", [])]
        if len(nodes) < 2:
            return json.dumps(
                {
                    "success": False,
                    "error": "failover requires at least two enrolled nodes",
                    "required_nodes": 2,
                    "detected_nodes": len(nodes),
                },
                indent=2,
                ensure_ascii=False,
            )
        plan = generate_failover_plan(apps, nodes)
        return json.dumps(plan, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_failover_generate_keepalived(vip: str, primary_host: str, secondary_host: str) -> str:
        """Génère une configuration keepalived pour failover IP.
        Args:
            vip: IP virtuelle flottante
            primary_host: IP du serveur principal
            secondary_host: IP du serveur secondaire
        """
        from nexora_node_sdk.failover import generate_keepalived_config

        return generate_keepalived_config(vip, primary_host, secondary_host)

    @mcp.tool()
    async def ynh_failover_apply_nginx(app_id: str, domain: str, primary_host: str, secondary_host: str) -> str:
        """[OPERATOR] Applique une config nginx failover et recharge nginx.
        Args:
            app_id: Identifiant de l'app
            domain: Domaine
            primary_host: Backend principal (host:port)
            secondary_host: Backend secondaire (host:port)
        """
        from nexora_node_sdk.failover import apply_failover_nginx

        return json.dumps(
            apply_failover_nginx(app_id, primary_host, secondary_host, domain),
            indent=2,
            ensure_ascii=False,
        )

    @mcp.tool()
    async def ynh_failover_apply_maintenance(domain: str, message: str = "Maintenance en cours") -> str:
        """[OPERATOR] Active le mode maintenance sur un domaine (503).
        Args:
            domain: Domaine
            message: Message affiché
        """
        from nexora_node_sdk.failover import apply_maintenance_mode

        return json.dumps(apply_maintenance_mode(domain, message), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_failover_remove_maintenance(domain: str) -> str:
        """[OPERATOR] Désactive le mode maintenance sur un domaine.
        Args:
            domain: Domaine
        """
        from nexora_node_sdk.failover import remove_maintenance_mode

        return json.dumps(remove_maintenance_mode(domain), indent=2, ensure_ascii=False)
