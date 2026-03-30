"""Automation: scheduled job definitions, workflow templates, checklists."""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Canonical templates now live in nexora_node_sdk.automation_engine.
# Re-export here for backward compatibility.
from nexora_node_sdk.automation_engine import (
    AUTOMATION_TEMPLATES,
    generate_automation_plan,
    generate_crontab,
)

__all__ = [
    "AUTOMATION_TEMPLATES",
    "generate_automation_plan",
    "generate_crontab",
    "list_automation_templates",
    "CHECKLISTS",
]



def list_automation_templates() -> list[dict[str, Any]]:
    """List all available automation templates."""
    return [{"id": k, **v} for k, v in AUTOMATION_TEMPLATES.items()]


# ── Checklists ────────────────────────────────────────────────────────

CHECKLISTS = {
    "pre_deployment": {
        "name": "Pre-deployment checklist",
        "items": [
            "Backup complet réalisé",
            "Espace disque suffisant (> 20% libre)",
            "Services critiques opérationnels",
            "Certificats SSL valides",
            "DNS configuré correctement",
            "Permissions vérifiées",
            "Tests en environnement de staging",
        ],
    },
    "post_deployment": {
        "name": "Post-deployment checklist",
        "items": [
            "Application accessible via navigateur",
            "Authentification SSO fonctionnelle",
            "Permissions correctes",
            "Logs sans erreur critique",
            "Backup post-installation réalisé",
            "Documentation mise à jour",
        ],
    },
    "incident_response": {
        "name": "Incident response checklist",
        "items": [
            "Identifier le service impacté",
            "Vérifier les logs récents",
            "Vérifier l'espace disque",
            "Vérifier la mémoire et le CPU",
            "Vérifier les certificats",
            "Tenter un redémarrage du service",
            "Vérifier après redémarrage",
            "Documenter l'incident",
            "Planifier une action corrective",
        ],
    },
    "monthly_review": {
        "name": "Monthly review checklist",
        "items": [
            "Revoir les scores de sécurité",
            "Revoir les scores PRA",
            "Vérifier la fraîcheur des backups",
            "Appliquer les mises à jour en attente",
            "Revoir les permissions publiques",
            "Vérifier les certificats (< 30 jours)",
            "Générer le rapport exécutif",
            "Planifier les actions du mois suivant",
        ],
    },
}


def list_checklists() -> list[dict[str, Any]]:
    return [{"id": k, **v} for k, v in CHECKLISTS.items()]


def get_checklist(checklist_id: str) -> dict[str, Any]:
    if checklist_id in CHECKLISTS:
        return {"id": checklist_id, **CHECKLISTS[checklist_id]}
    return {
        "error": f"Unknown checklist: {checklist_id}",
        "available": list(CHECKLISTS.keys()),
    }


def install_crontab(profile: str = "standard", user: str = "nexora") -> dict[str, Any]:
    """Generate and install the crontab to /etc/cron.d/nexora."""
    plan = generate_automation_plan(profile)
    content = generate_crontab(plan["jobs"], user)
    path = Path("/etc/cron.d/nexora")
    try:
        path.write_text(content)
        path.chmod(0o644)
        return {
            "installed": True,
            "path": str(path),
            "jobs": plan["job_count"],
            "profile": profile,
        }
    except PermissionError:
        # Fallback: write to /opt/nexora/var/
        fallback = Path("/opt/nexora/var/crontab-nexora")
        fallback.parent.mkdir(parents=True, exist_ok=True)
        fallback.write_text(content)
        return {
            "installed": False,
            "fallback_path": str(fallback),
            "jobs": plan["job_count"],
            "profile": profile,
            "note": "Permission denied for /etc/cron.d/. Copy manually: sudo cp "
            + str(fallback)
            + " /etc/cron.d/nexora",
        }
