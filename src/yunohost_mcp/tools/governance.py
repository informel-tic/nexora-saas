"""MCP tools for governance, compliance, scoring and executive reporting."""

from __future__ import annotations

import json
from mcp.server.fastmcp import FastMCP
from yunohost_mcp.utils.runner import run_ynh_command


def register_governance_tools(mcp: FastMCP, settings=None):

    async def _local_inventory():
        inv = {}
        for key, cmd in [
            ("apps", ["app", "list"]),
            ("domains", ["domain", "list"]),
            ("permissions", ["user", "permission", "list", "--full"]),
            ("services", ["service", "status"]),
            ("backups", ["backup", "list"]),
            ("certs", ["domain", "cert", "status"]),
            ("version", ["--version"]),
        ]:
            r = await run_ynh_command(*cmd)
            inv[key] = r.data if r.success else {}
        return inv

    @mcp.tool()
    async def ynh_gov_security_score() -> str:
        """Calcule le score de sécurité du serveur (0-100, grade A-F)."""
        from nexora_core.scoring import compute_security_score

        inv = await _local_inventory()
        return json.dumps(compute_security_score(inv), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_gov_pra_score() -> str:
        """Calcule le score PRA/continuité du serveur (0-100, grade A-F)."""
        from nexora_core.scoring import compute_pra_score

        inv = await _local_inventory()
        return json.dumps(compute_pra_score(inv), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_gov_health_score() -> str:
        """Calcule le score de santé du serveur (0-100, grade A-D)."""
        from nexora_core.scoring import compute_health_score

        inv = await _local_inventory()
        return json.dumps(compute_health_score(inv), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_gov_compliance_score() -> str:
        """Calcule le score de conformité/maturité (0-100, niveau enterprise/professional/standard/basic)."""
        from nexora_core.scoring import compute_compliance_score

        inv = await _local_inventory()
        return json.dumps(
            compute_compliance_score(inv, has_pra=True, has_monitoring=True),
            indent=2,
            ensure_ascii=False,
        )

    @mcp.tool()
    async def ynh_gov_executive_report() -> str:
        """Génère un rapport exécutif complet avec tous les scores et priorités."""
        from nexora_core.governance import executive_report

        inv = await _local_inventory()
        return json.dumps(
            executive_report(inv, has_pra=True, has_monitoring=True),
            indent=2,
            ensure_ascii=False,
        )

    @mcp.tool()
    async def ynh_gov_risk_register() -> str:
        """Génère le registre des risques du serveur, triés par sévérité."""
        from nexora_core.governance import risk_register

        inv = await _local_inventory()
        return json.dumps(risk_register(inv), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_gov_change_log() -> str:
        """Génère le journal des changements à partir des snapshots d'inventaire."""
        from nexora_core.governance import change_log
        from nexora_core.state import StateStore

        store = StateStore("/opt/nexora/var/state.json")
        state = store.load()
        snapshots = state.get("inventory_snapshots", [])
        if len(snapshots) < 2:
            return "Pas assez de snapshots pour générer un changelog. Faites d'abord plusieurs imports."
        return json.dumps(change_log(snapshots), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_gov_snapshot_diff() -> str:
        """Compare le dernier snapshot d'inventaire avec l'avant-dernier."""
        from nexora_core.scoring import diff_snapshots
        from nexora_core.state import StateStore

        store = StateStore("/opt/nexora/var/state.json")
        state = store.load()
        snapshots = state.get("inventory_snapshots", [])
        if len(snapshots) < 2:
            return "Pas assez de snapshots pour comparer."
        before = snapshots[-2].get("inventory", {})
        after = snapshots[-1].get("inventory", {})
        return json.dumps(diff_snapshots(before, after), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_gov_all_scores() -> str:
        """Affiche tous les scores en une seule vue (sécurité, PRA, santé, conformité)."""
        from nexora_core.scoring import (
            compute_security_score,
            compute_pra_score,
            compute_health_score,
            compute_compliance_score,
        )

        inv = await _local_inventory()
        sec = compute_security_score(inv)
        pra = compute_pra_score(inv)
        health = compute_health_score(inv)
        comp = compute_compliance_score(inv, has_pra=True, has_monitoring=True)
        overall = int(
            (sec["score"] + pra["score"] + health["score"] + comp["score"]) / 4
        )
        return json.dumps(
            {
                "security": {"score": sec["score"], "grade": sec["grade"]},
                "pra": {"score": pra["score"], "grade": pra["grade"]},
                "health": {"score": health["score"], "grade": health["grade"]},
                "compliance": {"score": comp["score"], "level": comp["maturity_level"]},
                "overall": overall,
            },
            indent=2,
            ensure_ascii=False,
        )
