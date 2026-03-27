"""MCP tools for custom hooks and event system."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP


def register_hooks_tools(mcp: FastMCP, settings=None):

    @mcp.tool()
    async def ynh_hooks_list_events() -> str:
        """Liste tous les événements auxquels des hooks peuvent être attachés."""
        from nexora_core.hooks import list_hook_events

        return json.dumps(list_hook_events(), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_hooks_list_presets() -> str:
        """Liste les presets de hooks (minimal, standard, professional)."""
        from nexora_core.hooks import list_hook_presets

        return json.dumps(list_hook_presets(), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_hooks_generate_config(preset: str = "standard") -> str:
        """Génère une configuration de hooks à partir d'un preset.
        Args:
            preset: Preset (minimal, standard, professional)
        """
        from nexora_core.hooks import HOOK_PRESETS, generate_hooks_config

        hooks = HOOK_PRESETS.get(preset, HOOK_PRESETS["standard"])
        return json.dumps(generate_hooks_config(hooks), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_hooks_generate_script(event: str, actions: str) -> str:
        """Génère un script de hook pour un événement spécifique.
        Args:
            event: Événement (post_backup, health_check_failed, etc.)
            actions: Commandes séparées par des points-virgules
        """
        from nexora_core.hooks import generate_hook_script

        action_list = [a.strip() for a in actions.split(";") if a.strip()]
        return json.dumps(generate_hook_script(event, action_list), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_hooks_install_preset(preset: str = "standard") -> str:
        """[OPERATOR] Installe tous les hooks d'un preset sur le serveur.
        Args:
            preset: Preset (minimal, standard, professional)
        """
        from nexora_core.hooks import install_hooks_preset

        return json.dumps(install_hooks_preset(preset), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_hooks_install_script(event: str, actions: str) -> str:
        """[OPERATOR] Génère et installe un hook sur le serveur.
        Args:
            event: Événement (post_backup, health_check_failed, etc.)
            actions: Commandes séparées par des points-virgules
        """
        from nexora_core.hooks import install_hook

        action_list = [a.strip() for a in actions.split(";") if a.strip()]
        return json.dumps(install_hook(event, action_list), indent=2, ensure_ascii=False)
