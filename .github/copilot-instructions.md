# Nexora SaaS Control Plane — Copilot Instructions

Nexora is a **sovereign SaaS control-plane** layered on top of YunoHost. It adds multi-node orchestration, AI automation, PRA, governance, and multi-tenancy — without modifying YunoHost core.

## Architecture

```
Layer C — Control Plane (FastAPI API) + Console (vanilla JS) + MCP (AI adapter)
Layer B — Node Agent + overlay + identity/trust lifecycle
Layer A — YunoHost runtime (untouched)
```

**Component map:**
- `src/nexora_saas/` — shared domain modules (fleet, security, blueprints, PRA, SLA…)
- `src/yunohost_mcp/` — AI-facing automation interface
- `apps/control_plane/` — FastAPI backend + entry point
- `apps/console/` — vanilla JS operator UI (no framework)
- `blueprints/` — business templates (MSP, PME, ecommerce, agency…)

## Build & Test

```bash
PYTHONPATH=src python -m pytest tests/ -v --tb=short
```

## Conventions

- `unittest.TestCase` (class-based) for all tests
- Domain logic uses **dataclasses** + `pydantic` models; REST APIs use **FastAPI**
- Console: vanilla JavaScript — no framework. Tokens in `sessionStorage`
- API routes: `/api/v1*` namespace
- Token comparison: `secrets.compare_digest()` — never `==`
- Token files: `0o600`
- Multi-tenancy: strict `tenant_id` enforcement everywhere

## Security Invariants

- Timing-safe token comparison (`secrets.compare_digest()`)
- Token file permissions `0o600`
- Strict tenant isolation across API, orchestration, logs, metrics, secrets
- Auth via `Authorization: Bearer <token>` or `X-Nexora-Token: <token>`
