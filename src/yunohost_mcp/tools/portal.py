"""MCP tools for portal design system and theming."""

from __future__ import annotations

import json
from mcp.server.fastmcp import FastMCP


def register_portal_tools(mcp: FastMCP, settings=None):

    @mcp.tool()
    async def ynh_portal_list_palettes() -> str:
        """Liste toutes les palettes de thèmes disponibles."""
        from nexora_core.portal import list_available_palettes

        return json.dumps(list_available_palettes(), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_portal_list_sectors() -> str:
        """Liste tous les thèmes sectoriels disponibles (agence, PME, MSP, etc.)."""
        from nexora_core.portal import list_sector_themes

        return json.dumps(list_sector_themes(), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_portal_generate_theme(
        brand_name: str, palette: str = "corporate", tagline: str = ""
    ) -> str:
        """Génère un thème de portail complet.
        Args:
            brand_name: Nom de la marque
            palette: Palette de couleurs (corporate, creative, nature, warm, dark_pro, neutral)
            tagline: Slogan / sous-titre
        """
        from nexora_core.portal import generate_theme

        theme = generate_theme(brand_name, palette_name=palette, tagline=tagline)
        return json.dumps(theme, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_portal_generate_sector_theme(sector: str, brand_name: str) -> str:
        """Génère un thème adapté à un secteur d'activité.
        Args:
            sector: Secteur (agency, pme, msp, association, training, ecommerce, collective)
            brand_name: Nom de la marque
        """
        from nexora_core.portal import generate_sector_theme

        theme = generate_sector_theme(sector, brand_name)
        return json.dumps(theme, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_portal_multi_profile(brand_name: str, profiles: str = "") -> str:
        """Génère un portail multi-profils (admin, salariés, clients, partenaires).
        Args:
            brand_name: Nom de la marque
            profiles: Profils JSON (optionnel, défaut: admin + users + visitors)
        """
        from nexora_core.portal import generate_theme, generate_multi_profile_portal

        base = generate_theme(brand_name)
        if profiles:
            try:
                profile_list = json.loads(profiles)
            except json.JSONDecodeError:
                profile_list = []
        else:
            profile_list = [
                {
                    "name": "admin",
                    "display_name": "Administration",
                    "sections": ["fleet", "security", "monitoring", "pra"],
                },
                {
                    "name": "users",
                    "display_name": "Collaborateurs",
                    "sections": ["apps", "people"],
                },
                {"name": "visitors", "display_name": "Visiteurs", "sections": ["apps"]},
            ]
        result = generate_multi_profile_portal(profile_list, base)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_portal_check_contrast(foreground: str, background: str) -> str:
        """Vérifie le contraste entre deux couleurs (WCAG).
        Args:
            foreground: Couleur du texte (hex, ex: #1e293b)
            background: Couleur de fond (hex, ex: #f8fafc)
        """
        from nexora_core.portal import validate_contrast

        result = validate_contrast(foreground, background)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_portal_apply_theme(
        brand_name: str, palette: str = "corporate"
    ) -> str:
        """Applique un thème au state Nexora (branding persistant).
        Args:
            brand_name: Nom de la marque
            palette: Palette de couleurs
        """
        from nexora_core.portal import generate_theme
        from nexora_core.state import StateStore

        theme = generate_theme(brand_name, palette_name=palette)
        store = StateStore("/opt/nexora/var/state.json")
        state = store.load()
        state["branding"] = {
            "brand_name": brand_name,
            "accent": theme["palette"]["accent"],
            "portal_title": theme["brand_name"],
            "tagline": theme["tagline"],
            "palette": theme["palette"],
            "sections": ["apps", "security", "monitoring", "pra", "fleet"],
        }
        store.save(state)
        return f"✅ Thème '{palette}' appliqué pour '{brand_name}'."
