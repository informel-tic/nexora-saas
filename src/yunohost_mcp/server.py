from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

from yunohost_mcp.config import load_settings
from yunohost_mcp.policy import tool_allowed

# Phase 1 — Core admin
from yunohost_mcp.tools.app import register_app_tools
from yunohost_mcp.tools.automation import register_automation_tools
from yunohost_mcp.tools.backup import register_backup_tools

# Phase 2 — YunoHost Pro
from yunohost_mcp.tools.blueprints import register_blueprint_tools

# Phase 5 — Plateforme sur mesure
from yunohost_mcp.tools.docker import register_docker_tools
from yunohost_mcp.tools.documentation import register_documentation_tools
from yunohost_mcp.tools.domain import register_domain_tools

# Phase 4 — Edge / infra avancée
from yunohost_mcp.tools.edge import register_edge_tools
from yunohost_mcp.tools.failover import register_failover_tools

# Phase 3 — Fleet
from yunohost_mcp.tools.fleet import register_fleet_tools
from yunohost_mcp.tools.governance import register_governance_tools
from yunohost_mcp.tools.hooks import register_hooks_tools
from yunohost_mcp.tools.migration import register_migration_tools
from yunohost_mcp.tools.modes import register_mode_tools
from yunohost_mcp.tools.monitoring import register_monitoring_tools
from yunohost_mcp.tools.multitenant import register_multitenant_tools
from yunohost_mcp.tools.notifications import register_notification_tools
from yunohost_mcp.tools.packaging import register_packaging_tools
from yunohost_mcp.tools.portal import register_portal_tools
from yunohost_mcp.tools.pra import register_pra_tools
from yunohost_mcp.tools.security import register_security_tools
from yunohost_mcp.tools.sla import register_sla_tools
from yunohost_mcp.tools.storage import register_storage_tools
from yunohost_mcp.tools.sync import register_sync_tools
from yunohost_mcp.tools.system import register_system_tools
from yunohost_mcp.tools.user import register_user_tools

logger = logging.getLogger(__name__)
settings = load_settings()

mcp = FastMCP("yunohost-mcp-server")

# ── Register all 25 tool modules ──────────────────────────────────────
_registrars = [
    register_app_tools,
    register_backup_tools,
    register_domain_tools,
    register_user_tools,
    register_system_tools,
    register_pra_tools,
    register_security_tools,
    register_monitoring_tools,
    register_documentation_tools,
    register_packaging_tools,
    register_blueprint_tools,
    register_portal_tools,
    register_governance_tools,
    register_automation_tools,
    register_fleet_tools,
    register_sync_tools,
    register_edge_tools,
    register_failover_tools,
    register_storage_tools,
    register_docker_tools,
    register_notification_tools,
    register_sla_tools,
    register_migration_tools,
    register_multitenant_tools,
    register_hooks_tools,
    register_mode_tools,
]

for registrar in _registrars:
    registrar(mcp, settings)

# ── Policy enforcement ────────────────────────────────────────────────
_registered_tools = [tool.name for tool in mcp.list_tools()]
_blocked = []
for tool_name in _registered_tools:
    if not tool_allowed(tool_name, settings):
        try:
            mcp.remove_tool(tool_name)
            _blocked.append(tool_name)
        except Exception as exc:
            logger.warning("Policy filtering failed for tool '%s': %s", tool_name, exc)

if _blocked:
    logger.info("Policy blocked %d tool(s): %s", len(_blocked), ", ".join(_blocked))

_final_count = len(mcp.list_tools())
logger.info("MCP server ready: %d tool(s) across 26 modules", _final_count)
