"""Portal design system: theming, branding, multi-profile portals."""

from __future__ import annotations

import datetime
from typing import Any

# Predefined theme palettes
THEME_PALETTES = {
    "corporate": {
        "primary": "#2563eb",
        "accent": "#2563eb",
        "surface": "#f8fafc",
        "text": "#1e293b",
        "muted": "#64748b",
    },
    "creative": {
        "primary": "#8b5cf6",
        "accent": "#8b5cf6",
        "surface": "#faf5ff",
        "text": "#1e1b4b",
        "muted": "#7c3aed",
    },
    "nature": {
        "primary": "#059669",
        "accent": "#059669",
        "surface": "#f0fdf4",
        "text": "#064e3b",
        "muted": "#6ee7b7",
    },
    "warm": {
        "primary": "#ea580c",
        "accent": "#ea580c",
        "surface": "#fff7ed",
        "text": "#431407",
        "muted": "#fb923c",
    },
    "dark_pro": {
        "primary": "#2dd4bf",
        "accent": "#2dd4bf",
        "surface": "#0f172a",
        "text": "#e5eefb",
        "muted": "#94a3b8",
    },
    "neutral": {
        "primary": "#6366f1",
        "accent": "#6366f1",
        "surface": "#fafafa",
        "text": "#18181b",
        "muted": "#a1a1aa",
    },
}

SECTOR_THEMES = {
    "agency": {
        "palette": "creative",
        "layout": "cards",
        "sections": ["apps", "clients", "projects", "security"],
    },
    "pme": {
        "palette": "corporate",
        "layout": "grid",
        "sections": ["apps", "people", "security", "backups"],
    },
    "msp": {
        "palette": "dark_pro",
        "layout": "dashboard",
        "sections": ["fleet", "clients", "security", "pra"],
    },
    "association": {
        "palette": "nature",
        "layout": "simple",
        "sections": ["apps", "members", "communication"],
    },
    "training": {
        "palette": "warm",
        "layout": "cards",
        "sections": ["apps", "courses", "people", "resources"],
    },
    "ecommerce": {
        "palette": "neutral",
        "layout": "grid",
        "sections": ["apps", "orders", "security", "monitoring"],
    },
    "collective": {
        "palette": "nature",
        "layout": "simple",
        "sections": ["apps", "governance", "communication", "resources"],
    },
}


def generate_theme(
    brand_name: str,
    *,
    palette_name: str = "corporate",
    logo_url: str = "",
    tagline: str = "",
) -> dict[str, Any]:
    """Generate a complete portal theme."""
    palette = THEME_PALETTES.get(palette_name, THEME_PALETTES["corporate"])
    return {
        "brand_name": brand_name,
        "tagline": tagline or f"Portail {brand_name}",
        "logo_url": logo_url,
        "palette": palette,
        "palette_name": palette_name,
        "typography": {
            "heading": "Inter, system-ui, sans-serif",
            "body": "Inter, system-ui, sans-serif",
            "mono": "JetBrains Mono, monospace",
        },
        "layout": {
            "max_width": "1200px",
            "sidebar": True,
            "header_style": "fixed",
        },
        "css_variables": {
            "--accent": palette["accent"],
            "--surface": palette["surface"],
            "--text": palette["text"],
            "--muted": palette["muted"],
        },
        "timestamp": datetime.datetime.now().isoformat(),
    }


def generate_sector_theme(sector: str, brand_name: str, **kwargs) -> dict[str, Any]:
    """Generate a theme tailored to a business sector."""
    config = SECTOR_THEMES.get(sector, SECTOR_THEMES["pme"])
    theme = generate_theme(brand_name, palette_name=config["palette"], **kwargs)
    theme["sector"] = sector
    theme["layout"]["style"] = config["layout"]
    theme["sections"] = config["sections"]
    return theme


def generate_multi_profile_portal(profiles: list[dict[str, Any]], base_theme: dict[str, Any]) -> dict[str, Any]:
    """Generate a multi-profile portal configuration."""
    portal_profiles = []
    for p in profiles:
        portal_profiles.append(
            {
                "profile_name": p.get("name", "default"),
                "display_name": p.get("display_name", p.get("name", "Default")),
                "sections": p.get("sections", base_theme.get("sections", ["apps"])),
                "visible_apps": p.get("visible_apps", []),
                "theme_overrides": p.get("theme_overrides", {}),
            }
        )

    return {
        "base_theme": base_theme,
        "profiles": portal_profiles,
        "default_profile": profiles[0].get("name", "default") if profiles else "default",
        "timestamp": datetime.datetime.now().isoformat(),
    }


def validate_contrast(foreground: str, background: str) -> dict[str, Any]:
    """Basic contrast ratio check (simplified WCAG)."""

    def _hex_to_luminance(hex_color: str) -> float:
        hex_color = hex_color.lstrip("#")
        if len(hex_color) == 3:
            hex_color = "".join(c * 2 for c in hex_color)
        if len(hex_color) != 6:
            return 0.5
        r, g, b = (
            int(hex_color[:2], 16) / 255,
            int(hex_color[2:4], 16) / 255,
            int(hex_color[4:6], 16) / 255,
        )

        def _lin(c):
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

        return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)

    l1 = _hex_to_luminance(foreground)
    l2 = _hex_to_luminance(background)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    ratio = (lighter + 0.05) / (darker + 0.05)

    return {
        "ratio": round(ratio, 2),
        "aa_normal": ratio >= 4.5,
        "aa_large": ratio >= 3.0,
        "aaa_normal": ratio >= 7.0,
        "foreground": foreground,
        "background": background,
    }


def list_available_palettes() -> list[dict[str, Any]]:
    """List all available theme palettes."""
    return [{"name": k, "primary": v.get("accent"), **v} for k, v in THEME_PALETTES.items()]


def list_sector_themes() -> list[dict[str, Any]]:
    """List all available sector theme configurations."""
    return [{"sector": k, **v} for k, v in SECTOR_THEMES.items()]
