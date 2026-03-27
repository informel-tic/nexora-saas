"""Node agent local API — minimal runtime stub.

Exposes health and status endpoints consumed by the SaaS control plane.
The node agent runs on every enrolled YunoHost node and bridges Layer A
(YunoHost) with Layer C (Nexora control plane).
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("nexora.node_agent.api")

app = FastAPI(title="Nexora Node Agent", version="2.0.0")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/api/v1/status")
async def status() -> dict:
    return {"agent": "running", "version": "2.0.0"}


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    logger.warning("HTTP %s at %s: %s", exc.status_code, request.url.path, exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
