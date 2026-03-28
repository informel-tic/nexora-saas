"""Fleet management client for Nexora node SDK.

Provides fleet node communication, remote inventory fetching, and
fleet-wide lifecycle coordination.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_RETRIES = 3
_DEFAULT_TIMEOUT = 10.0


@dataclass
class FleetEndpoint:
    """Remote fleet node connection descriptor."""

    host: str
    port: int = 38120
    scheme: str = "https"
    token: str | None = None

    @property
    def base_url(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}"


@dataclass
class FleetNodeCache:
    """Cached inventory data for a remote fleet node."""

    node_id: str
    data: dict[str, Any] = field(default_factory=dict)
    fetched_at: str | None = None

    def is_stale(self, ttl: float = 30.0) -> bool:
        if self.fetched_at is None:
            return True
        try:
            ts = datetime.fromisoformat(self.fetched_at)
            age = (datetime.now(timezone.utc) - ts).total_seconds()
            return age > ttl
        except ValueError:
            return True


def _request_with_retries(
    method: str,
    url: str,
    *,
    retries: int = _DEFAULT_RETRIES,
    timeout: float = _DEFAULT_TIMEOUT,
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
) -> httpx.Response:
    """Issue an HTTP request with retry logic."""
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with httpx.Client(timeout=timeout, verify=True) as client:
                response = client.request(method, url, headers=headers, json=json_body)
                response.raise_for_status()
                return response
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            last_exc = exc
            logger.warning("Fleet request attempt %d/%d failed: %s", attempt, retries, exc)
            if attempt < retries:
                time.sleep(min(2 ** (attempt - 1), 8))
    raise RuntimeError(f"Fleet request to {url} failed after {retries} retries") from last_exc


def fetch_node_inventory(endpoint: FleetEndpoint) -> dict[str, Any]:
    """Fetch remote node inventory and track 'fetched_at' timestamp."""
    headers: dict[str, str] = {}
    if endpoint.token:
        headers["Authorization"] = f"Bearer {endpoint.token}"
    url = f"{endpoint.base_url}/api/v1/status"
    response = _request_with_retries("GET", url, headers=headers)
    data = response.json()
    data["fetched_at"] = datetime.now(timezone.utc).isoformat()
    return data
