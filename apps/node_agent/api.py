"""Node agent local API — minimal runtime stub.

Exposes health and status endpoints consumed by the SaaS control plane.
The node agent runs on every enrolled YunoHost node and bridges Layer A
(YunoHost) with Layer C (Nexora control plane).
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from nexora_node_sdk.logging_config import setup_logging

setup_logging()

logger = logging.getLogger("nexora.node_agent.api")

app = FastAPI(title="Nexora Node Agent", version="2.0.0")


def _build_action_route(action_name: str, handler):
    """Register an action route on the node agent app."""
    path = f"/api/v1/actions/{action_name}"
    app.post(path)(handler)
    return path


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/api/v1/status")
async def status() -> dict:
    return {"agent": "running", "version": "2.0.0"}


async def _restart_service(request: Request) -> dict:
    return {"action": "restart_service", "status": "accepted"}


async def _sync_inventory(request: Request) -> dict:
    return {"action": "sync_inventory", "status": "accepted"}


action_routes = {
    "restart_service": _build_action_route("restart_service", _restart_service),
    "sync_inventory": _build_action_route("sync_inventory", _sync_inventory),
}


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    logger.warning("HTTP %s at %s: %s", exc.status_code, request.url.path, exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


def main():
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=38121)
