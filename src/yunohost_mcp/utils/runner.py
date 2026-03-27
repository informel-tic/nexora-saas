from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

from yunohost_mcp.config import load_settings
from yunohost_mcp.utils.safety import classify_tokens

logger = logging.getLogger(__name__)

# -- Audit logging -----------------------------------------------------

_audit_logger: logging.Logger | None = None


def _get_audit_logger() -> logging.Logger:
    global _audit_logger
    if _audit_logger is not None:
        return _audit_logger
    settings = load_settings()
    _audit_logger = logging.getLogger("yunohost_mcp.audit")
    _audit_logger.setLevel(logging.INFO)
    log_path = settings.audit_log_path
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        _audit_logger.addHandler(handler)
    except Exception as exc:
        logger.warning("Audit file logger disabled (path not writable): %s", exc)
    return _audit_logger


def _audit(action: str, detail: str, level: str = "safe") -> None:
    try:
        _get_audit_logger().info(json.dumps({"action": action, "detail": detail, "level": level}, ensure_ascii=False))
    except Exception as exc:
        logger.warning("Audit event write failed for action '%s': %s", action, exc)


# -- Helpers -----------------------------------------------------------


@dataclass
class YnhResult:
    success: bool
    data: Optional[dict | list | str] = None
    error: Optional[str] = None
    raw_output: str = ""
    return_code: int = 0
    safety_warning: str = ""


def _clean_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["PATH"] = "/usr/bin:/usr/sbin:/bin:/sbin:/usr/local/bin"
    return env


def _warning_for(level: str, what: str, destructive_allowed: bool) -> str:
    if level == "blocked":
        return f"\U0001f6ab Opération bloquée: {what}"
    if level == "dangerous" and not destructive_allowed:
        return f"\U0001f6ab Outil destructif désactivé par configuration: {what}"
    if level == "dangerous":
        return f"\u26a0\ufe0f Opération destructive: {what}"
    if level == "moderate":
        return f"\u2139\ufe0f Opération de modification: {what}"
    return ""


# -- YunoHost command runner -------------------------------------------


async def run_ynh_command(*args: str, json_output: bool = True, timeout: int = 300) -> YnhResult:
    settings = load_settings()
    level = classify_tokens(tuple(args))
    warning = _warning_for(level, " ".join(args), settings.allow_destructive_tools)
    _audit("ynh_command", " ".join(args), level)
    if level == "blocked" or (level == "dangerous" and not settings.allow_destructive_tools):
        return YnhResult(False, error=warning, safety_warning=warning)
    candidate = "/usr/bin/yunohost" if os.path.exists("/usr/bin/yunohost") else "yunohost"
    cmd = [candidate, *args]
    if json_output:
        cmd.extend(["--output-as", "json"])
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_clean_env(),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        return YnhResult(False, error=f"Timeout après {timeout}s", safety_warning=warning)
    except FileNotFoundError:
        return YnhResult(False, error="Commande yunohost introuvable", safety_warning=warning)
    except Exception as exc:
        return YnhResult(False, error=str(exc), safety_warning=warning)
    out = stdout.decode("utf-8", errors="replace").strip()
    err = stderr.decode("utf-8", errors="replace").strip()
    if proc.returncode == 0:
        data: object = out
        if json_output and out:
            try:
                data = json.loads(out)
            except json.JSONDecodeError:
                data = out
        return YnhResult(
            True,
            data=data,
            raw_output=out,
            return_code=proc.returncode,
            safety_warning=warning,
        )
    return YnhResult(
        False,
        error=err or out or f"Code retour: {proc.returncode}",
        raw_output=out,
        return_code=proc.returncode,
        safety_warning=warning,
    )


# -- Safe shell command runner -----------------------------------------
# NEVER interpolate user input into shell strings. Use this function
# which takes an argument list and passes it via subprocess_exec.


async def run_shell_command_safe(args: list[str], timeout: int = 120) -> str:
    """Execute a command as an argument list — no shell interpolation."""
    settings = load_settings()
    level = classify_tokens(tuple(args))
    warning = _warning_for(level, " ".join(args), settings.allow_destructive_tools)
    _audit("shell_command", " ".join(args), level)
    if level == "blocked" or (level == "dangerous" and not settings.allow_destructive_tools):
        return warning
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_clean_env(),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        out = stdout.decode("utf-8", errors="replace").strip()
        err = stderr.decode("utf-8", errors="replace").strip()
        return (warning + "\n\n" if warning else "") + (out or err or "")
    except Exception as exc:
        return f"❌ Erreur shell: {exc}"


async def run_shell_command(command: str, timeout: int = 120) -> str:
    """Execute a shell command string. Only for STATIC commands with no user input.

    If the command contains user-supplied values, use run_shell_command_safe()
    with a proper argument list instead.
    """
    settings = load_settings()
    level = classify_tokens(tuple(command.split()))
    warning = _warning_for(level, command, settings.allow_destructive_tools)
    _audit("shell_command_raw", command, level)
    if level == "blocked" or (level == "dangerous" and not settings.allow_destructive_tools):
        return warning
    try:
        proc = await asyncio.create_subprocess_exec(
            "bash",
            "-lc",
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_clean_env(),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        out = stdout.decode("utf-8", errors="replace").strip()
        err = stderr.decode("utf-8", errors="replace").strip()
        return (warning + "\n\n" if warning else "") + (out or err or "")
    except Exception as exc:
        return f"❌ Erreur shell: {exc}"


def format_result(result: YnhResult) -> str:
    parts: list[str] = []
    if result.safety_warning:
        parts.append(result.safety_warning)
    if result.success:
        if isinstance(result.data, (dict, list)):
            parts.append(json.dumps(result.data, indent=2, ensure_ascii=False))
        else:
            parts.append(str(result.data))
    else:
        parts.append(f"❌ Erreur: {result.error}")
    return "\n\n".join(p for p in parts if p)
