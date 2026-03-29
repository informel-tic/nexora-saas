"""Owner passphrase authentication and session management.

The SaaS owner authenticates via a passphrase (not the API token).
After validation, the backend issues a short-lived session token that
the owner console uses for subsequent requests.

Passphrase is stored as a SHA-256 hash in /etc/nexora/owner-passphrase
or the path specified by NEXORA_OWNER_PASSPHRASE_FILE.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
import threading
from pathlib import Path
from typing import Any

# Session store: { session_token: { tenant_id, role, issued_at, expires_at } }
_sessions: dict[str, dict[str, Any]] = {}
_sessions_lock = threading.Lock()

_SESSION_MAX_AGE = int(os.environ.get("NEXORA_OWNER_SESSION_TTL", "28800"))  # 8h default

_OWNER_TENANT_ID_ENV = "NEXORA_OWNER_TENANT_ID"
_DEFAULT_OWNER_TENANT = "nexora-owner"


def _passphrase_path_candidates() -> list[str]:
    return [
        os.environ.get("NEXORA_OWNER_PASSPHRASE_FILE", ""),
        "/etc/nexora/owner-passphrase",
        "/opt/nexora/var/owner-passphrase",
    ]


def _load_passphrase_hash() -> str | None:
    """Load the stored passphrase hash from disk."""
    for path_str in _passphrase_path_candidates():
        if not path_str:
            continue
        p = Path(path_str)
        if p.exists():
            try:
                return p.read_text(encoding="utf-8").strip()
            except OSError:
                continue
    return None


def _hash_passphrase(passphrase: str) -> str:
    """Hash a passphrase using SHA-256 (hex digest)."""
    return hashlib.sha256(passphrase.encode("utf-8")).hexdigest()


def set_owner_passphrase(passphrase: str) -> dict[str, str]:
    """Hash and persist a new owner passphrase.

    Returns the path where it was stored.
    """
    hashed = _hash_passphrase(passphrase)
    for path_str in _passphrase_path_candidates():
        if not path_str:
            continue
        p = Path(path_str)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(hashed, encoding="utf-8")
            p.chmod(0o600)
            return {"path": str(p), "stored": True}
        except (OSError, PermissionError):
            continue
    return {"path": "", "stored": False}


def verify_passphrase(passphrase: str) -> bool:
    """Verify a passphrase against the stored hash."""
    stored_hash = _load_passphrase_hash()
    if not stored_hash:
        return False
    candidate_hash = _hash_passphrase(passphrase)
    return hmac.compare_digest(candidate_hash, stored_hash)


def owner_tenant_id() -> str:
    return os.environ.get(_OWNER_TENANT_ID_ENV, _DEFAULT_OWNER_TENANT).strip() or _DEFAULT_OWNER_TENANT


def create_owner_session() -> dict[str, Any]:
    """Create a new authenticated owner session."""
    token = secrets.token_urlsafe(48)
    now = int(time.time())
    session = {
        "tenant_id": owner_tenant_id(),
        "role": "owner",
        "issued_at": now,
        "expires_at": now + _SESSION_MAX_AGE,
    }
    with _sessions_lock:
        # Garbage-collect expired sessions
        expired = [k for k, v in _sessions.items() if v["expires_at"] < now]
        for k in expired:
            del _sessions[k]
        _sessions[token] = session
    return {"session_token": token, **session}


def validate_owner_session(session_token: str) -> dict[str, Any] | None:
    """Return session data if the token is valid and not expired."""
    if not session_token:
        return None
    now = int(time.time())
    with _sessions_lock:
        session = _sessions.get(session_token)
        if session is None:
            return None
        if session["expires_at"] < now:
            del _sessions[session_token]
            return None
        return dict(session)


def revoke_owner_session(session_token: str) -> bool:
    """Revoke an owner session."""
    with _sessions_lock:
        return _sessions.pop(session_token, None) is not None


def has_passphrase_configured() -> bool:
    """Check if an owner passphrase has been set."""
    return _load_passphrase_hash() is not None
