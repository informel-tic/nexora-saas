# Nexora SaaS

`nexora-saas` is the Layer C repository for Nexora: the FastAPI control plane, the vanilla JS operator console, the MCP automation surface, and the SaaS-specific orchestration modules.

## Scope

- `apps/control_plane/` - central API and control-plane entrypoint
- `apps/console/` - operator console served by the control plane
- `src/yunohost_mcp/` - AI-facing MCP server and tool registry
- `src/nexora_core/` - shared domain core plus SaaS-only modules such as fleet, multitenancy, quotas, governance, failover, blueprints, and sync
- `blueprints/` - sector deployment templates consumed by the control plane

This repository intentionally excludes the YunoHost node package and the node agent runtime app.

## Architecture

```text
Layer A - YunoHost runtime (untouched)
Layer B - Nexora node runtime (lives in nexora-node_ynh)
Layer C - Control plane API + Console + MCP + SaaS orchestration
```

## Run locally

```bash
PYTHONPATH=src python -m pytest tests/ -q
python -m uvicorn apps.control_plane.api:app --host 127.0.0.1 --port 38120
python -m yunohost_mcp.cli
```

## Packaging

- `nexora-control-plane` starts the FastAPI backend
- `yunohost-mcp-server` starts the MCP adapter
- deployment helpers stay in `deploy/` for operator-side bootstrap flows

## Key invariants

- `/api/v1*` remains the public API namespace
- multitenant isolation stays enforced through `tenant_id`
- token comparison stays timing-safe via `secrets.compare_digest()`
- token files remain mode `0o600`

## Documentation

- `docs/ARCHITECTURE.md`
- `docs/API_SURFACE_REFERENCE.md`
- `docs/CONSOLE_OPERATOR_GUIDE.md`
- `docs/DEPLOYMENT.md`
- `docs/SECURITY.md`
- `docs/CI_QUALITY_GATES.md`

## License

AGPL-3.0-or-later
