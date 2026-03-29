"""Runtime mode manager: switch, escalate, audit all mode transitions.

Modes hierarchy: observer < operator < architect < admin
Each higher mode includes all tools from lower modes.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MODES = {
    "observer": {
        "level": 0,
        "description": "Lecture seule — audit, monitoring, documentation, scoring",
        "capabilities": ["read", "audit", "score", "document", "preview"],
    },
    "operator": {
        "level": 1,
        "description": "Actions sûres — restart, backup, branding, sync non-destructive",
        "capabilities": [
            "read",
            "audit",
            "score",
            "document",
            "preview",
            "restart_service",
            "create_backup",
            "apply_branding",
            "sync_config",
            "register_node",
            "verify_backup",
        ],
    },
    "architect": {
        "level": 2,
        "description": "Génération — topologies, blueprints, deploy plans, PRA plans",
        "capabilities": [
            "read",
            "audit",
            "score",
            "document",
            "preview",
            "restart_service",
            "create_backup",
            "apply_branding",
            "sync_config",
            "register_node",
            "verify_backup",
            "generate_topology",
            "generate_deploy_plan",
            "generate_lb_config",
            "generate_failover_config",
            "generate_pra_plan",
            "generate_tenant",
            "generate_hooks",
        ],
    },
    "admin": {
        "level": 3,
        "description": "Toutes opérations — install, remove, upgrade, restore, deploy",
        "capabilities": [
            "read",
            "audit",
            "score",
            "document",
            "preview",
            "restart_service",
            "create_backup",
            "apply_branding",
            "sync_config",
            "register_node",
            "verify_backup",
            "generate_topology",
            "generate_deploy_plan",
            "generate_lb_config",
            "generate_failover_config",
            "generate_pra_plan",
            "generate_tenant",
            "generate_hooks",
            "install_app",
            "remove_app",
            "upgrade_app",
            "restore_backup",
            "delete_backup",
            "deploy_blueprint",
            "create_user",
            "delete_user",
            "modify_domain",
            "system_upgrade",
            "execute_failover",
            "execute_sync",
        ],
    },
}

# Escalation tokens: short-lived tokens for temporary mode elevation
_escalation_tokens: dict[str, dict[str, Any]] = {}
_ESCALATION_TTL = 3600  # 1 hour


class ModeManager:
    """Manages the current operating mode and mode transitions."""

    def __init__(self, state_path: str | Path = "/opt/nexora/var/state.json"):
        self._state_path = Path(state_path)
        self._current_mode = "observer"
        self._mode_history: list[dict[str, Any]] = []
        self._load_mode()

    def _load_mode(self):
        """Load current mode from state file."""
        try:
            if self._state_path.exists():
                data = json.loads(self._state_path.read_text())
                self._current_mode = data.get("runtime_mode", "observer")
                self._mode_history = data.get("mode_history", [])
        except Exception as exc:
            logger.warning(
                "failed to load runtime mode; falling back to observer",
                extra={"error": str(exc)},
            )
            self._current_mode = "observer"

    def _save_mode(self):
        """Persist current mode to state file."""
        try:
            data = {}
            if self._state_path.exists():
                data = json.loads(self._state_path.read_text())
            data["runtime_mode"] = self._current_mode
            data["mode_history"] = self._mode_history[-50:]  # Keep last 50 transitions
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            self._state_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        except Exception as e:
            logger.warning("Failed to save mode: %s", e)

    @property
    def current_mode(self) -> str:
        return self._current_mode

    @property
    def current_level(self) -> int:
        return MODES.get(self._current_mode, MODES["observer"])["level"]

    def get_mode_info(self) -> dict[str, Any]:
        mode = MODES.get(self._current_mode, MODES["observer"])
        return {
            "mode": self._current_mode,
            "level": mode["level"],
            "description": mode["description"],
            "capabilities": mode["capabilities"],
            "available_modes": list(MODES.keys()),
            "history": self._mode_history[-10:],
        }

    def switch_mode(self, target_mode: str, *, reason: str = "", operator: str = "system") -> dict[str, Any]:
        """Switch to a different mode. Returns the transition result."""
        if target_mode not in MODES:
            return {
                "success": False,
                "error": f"Unknown mode: {target_mode}",
                "available": list(MODES.keys()),
            }

        old_mode = self._current_mode
        old_level = self.current_level
        new_level = MODES[target_mode]["level"]

        # Record transition
        transition = {
            "from": old_mode,
            "to": target_mode,
            "direction": "escalation"
            if new_level > old_level
            else "de-escalation"
            if new_level < old_level
            else "same",
            "reason": reason,
            "operator": operator,
            "timestamp": datetime.datetime.now().isoformat(),
        }

        self._current_mode = target_mode
        self._mode_history.append(transition)
        self._save_mode()

        logger.info(
            "Mode switched: %s -> %s (by %s: %s)",
            old_mode,
            target_mode,
            operator,
            reason,
        )

        return {
            "success": True,
            "previous_mode": old_mode,
            "current_mode": target_mode,
            "level": new_level,
            "direction": transition["direction"],
            "capabilities": MODES[target_mode]["capabilities"],
        }

    def can_perform(self, capability: str) -> bool:
        """Check if the current mode allows a specific capability."""
        mode = MODES.get(self._current_mode, MODES["observer"])
        return capability in mode["capabilities"]

    def require_mode(self, minimum_mode: str) -> bool:
        """Check if current mode is at least the specified level."""
        min_level = MODES.get(minimum_mode, {"level": 99})["level"]
        return self.current_level >= min_level

    # ── Escalation tokens ─────────────────────────────────────────────

    def create_escalation_token(
        self, target_mode: str, *, duration_seconds: int = 3600, reason: str = ""
    ) -> dict[str, Any]:
        """Create a temporary escalation token."""
        if target_mode not in MODES:
            return {"error": f"Unknown mode: {target_mode}"}

        token = secrets.token_urlsafe(32)
        _escalation_tokens[token] = {
            "target_mode": target_mode,
            "expires_at": time.time() + duration_seconds,
            "reason": reason,
            "created_at": datetime.datetime.now().isoformat(),
        }

        return {
            "token": token,
            "target_mode": target_mode,
            "expires_in_seconds": duration_seconds,
            "note": "Use this token in the X-Nexora-Escalation header to temporarily operate in the target mode.",
        }

    def validate_escalation(self, token: str) -> str | None:
        """Validate an escalation token. Returns the target mode or None."""
        entry = _escalation_tokens.get(token)
        if not entry:
            return None
        if time.time() > entry["expires_at"]:
            del _escalation_tokens[token]
            return None
        return entry["target_mode"]

    def revoke_escalation(self, token: str) -> bool:
        """Revoke an escalation token."""
        if token in _escalation_tokens:
            del _escalation_tokens[token]
            return True
        return False

    def list_escalation_tokens(self) -> list[dict[str, Any]]:
        """List active escalation tokens (without the actual token values)."""
        now = time.time()
        active = []
        for tok, entry in list(_escalation_tokens.items()):
            if now > entry["expires_at"]:
                del _escalation_tokens[tok]
            else:
                active.append(
                    {
                        "token_prefix": tok[:8] + "...",
                        "target_mode": entry["target_mode"],
                        "remaining_seconds": int(entry["expires_at"] - now),
                        "reason": entry.get("reason", ""),
                    }
                )
        return active


# ── Confirmation workflow ─────────────────────────────────────────────

_pending_confirmations: dict[str, dict[str, Any]] = {}
_CONFIRMATION_TTL = 300  # 5 minutes


TOOL_MODE_MATRIX = {
    "app": "admin",
    "automation": "architect",
    "backup": "operator",
    "blueprints": "architect",
    "docker": "admin",
    "documentation": "observer",
    "domain": "admin",
    "edge": "architect",
    "failover": "admin",
    "fleet": "observer",
    "governance": "observer",
    "hooks": "architect",
    "migration": "architect",
    "modes": "admin",
    "monitoring": "observer",
    "multitenant": "architect",
    "notifications": "operator",
    "packaging": "architect",
    "portal": "operator",
    "pra": "operator",
    "security": "admin",
    "sla": "observer",
    "storage": "operator",
    "sync": "admin",
    "system": "admin",
    "user": "admin",
}


TOOL_PREFIX_ALIASES = {
    "admin": "app",
    "auto": "automation",
    "blueprint": "blueprints",
    "diagnosis": "monitoring",
    "disk": "storage",
    "doc": "documentation",
    "firewall": "security",
    "gov": "governance",
    "migrate": "migration",
    "mode": "modes",
    "monitor": "monitoring",
    "notify": "notifications",
    "op": "system",
    "pkg": "packaging",
    "service": "system",
    "settings": "system",
    "tenant": "multitenant",
    "version": "system",
}


def classify_tool_name(tool_name: str) -> str:
    """Classify a tool name based on its module prefix."""

    prefix = tool_name.removeprefix("ynh_").split("_", 1)[0]
    return TOOL_PREFIX_ALIASES.get(prefix, prefix)


def get_required_mode_for_tool(tool_name: str) -> str:
    """Return the minimum mode required for a tool name."""

    return TOOL_MODE_MATRIX.get(classify_tool_name(tool_name), "observer")


def validate_authorization_matrix(
    tools_dir: str | Path = Path(__file__).resolve().parents[1] / "yunohost_mcp" / "tools",
) -> dict[str, Any]:
    """Verify that all MCP tools map to an official authorization level."""

    tool_names: list[str] = []
    for path in sorted(Path(tools_dir).glob("*.py")):
        if path.name == "__init__.py":
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("async def ynh_"):
                tool_names.append(stripped.split()[2].split("(")[0])
    missing = [tool for tool in tool_names if classify_tool_name(tool) not in TOOL_MODE_MATRIX]
    return {"classified_tools": len(tool_names), "missing_tools": missing}


def _confirmation_fingerprint(action: str, target: str, params: dict[str, Any], operator: str) -> str:
    payload = json.dumps(
        {"action": action, "target": target, "params": params, "operator": operator},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def create_bound_confirmation(action: str, target: str, params: dict[str, Any], *, operator: str = "system") -> str:
    """Create a confirmation token bound to action, target, params and operator."""

    token = secrets.token_urlsafe(16)
    _pending_confirmations[token] = {
        "action": action,
        "target": target,
        "params": params,
        "operator": operator,
        "fingerprint": _confirmation_fingerprint(action, target, params, operator),
        "created_at": time.time(),
        "expires_at": time.time() + _CONFIRMATION_TTL,
    }
    return token


def validate_bound_confirmation(
    token: str,
    action: str,
    target: str,
    params: dict[str, Any],
    *,
    operator: str = "system",
) -> bool:
    """Validate (and consume) a confirmation token bound to a specific payload."""

    entry = _pending_confirmations.get(token)
    if not entry or time.time() > entry["expires_at"]:
        return False
    expected = _confirmation_fingerprint(action, target, params, operator)
    if not secrets.compare_digest(entry.get("fingerprint", ""), expected):
        return False
    _pending_confirmations.pop(token, None)
    return True


def request_confirmation(action: str, details: dict[str, Any], *, operator: str = "system") -> dict[str, Any]:
    """Request confirmation for a dangerous action. Returns a confirmation token."""
    token = create_bound_confirmation(action, str(details.get("target") or "unknown"), details, operator=operator)
    return {
        "confirmation_required": True,
        "confirmation_token": token,
        "action": action,
        "details": details,
        "expires_in_seconds": _CONFIRMATION_TTL,
        "instruction": "Re-send the request with X-Nexora-Confirm: <token> to execute.",
    }


def validate_confirmation(token: str) -> dict[str, Any] | None:
    """Validate and consume a confirmation token."""
    entry = _pending_confirmations.pop(token, None)
    if not entry:
        return None
    if time.time() > entry["expires_at"]:
        return None
    return entry


def list_pending_confirmations() -> list[dict[str, Any]]:
    """List pending confirmations."""
    now = time.time()
    active = []
    for tok, entry in list(_pending_confirmations.items()):
        if now > entry["expires_at"]:
            del _pending_confirmations[tok]
        else:
            active.append(
                {
                    "token_prefix": tok[:8] + "...",
                    "action": entry["action"],
                    "remaining_seconds": int(entry["expires_at"] - now),
                }
            )
    return active


# ── Singleton mode manager ────────────────────────────────────────────

_mode_manager: ModeManager | None = None


def get_mode_manager(state_path: str | Path | None = None) -> ModeManager:
    global _mode_manager
    resolved_state_path = Path(state_path or os.environ.get("NEXORA_STATE_PATH", "/opt/nexora/var/state.json"))
    if _mode_manager is None:
        _mode_manager = ModeManager(resolved_state_path)
    elif state_path is not None and Path(_mode_manager._state_path) != resolved_state_path:
        _mode_manager = ModeManager(resolved_state_path)
    return _mode_manager


def list_modes() -> list[dict[str, Any]]:
    return [{"mode": k, **v} for k, v in MODES.items()]


# ── Dynamic mode enforcement for MCP ─────────────────────────────────


def get_effective_mode(escalation_header: str | None = None) -> str:
    """Get the effective operating mode, considering escalation tokens."""
    mm = get_mode_manager()
    if escalation_header:
        target = mm.validate_escalation(escalation_header)
        if target:
            return target
    return mm.current_mode
