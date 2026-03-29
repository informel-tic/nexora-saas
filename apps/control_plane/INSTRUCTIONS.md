# control_plane — FastAPI Backend

## Purpose

HTTP API backend for the Nexora SaaS control plane. Exposes all `/api/*` routes, mounts middleware, and serves the console and owner console static files.

## Entry Points

- `app` FastAPI instance in `api.py` — all route definitions and middleware setup.
- `backend.py` — thin launcher that imports and runs `api.py`.

## Architecture

- All routes namespaced under `/api/v1*` or `/api/*`.
- Auth via `Authorization: Bearer <token>` or `X-Nexora-Token: <token>`.
- Role-based route gating: `OPERATOR_ROLES`, `SUBSCRIBER_DENIED_PREFIXES`.
- Serves `apps/console/` and `apps/owner_console/` as static file mounts.
- Uses `TokenAuthMiddleware`, `SecurityHeadersMiddleware`, and `CSRFProtectionMiddleware` from `nexora_node_sdk.auth`.

## Configuration

- `NEXORA_STATE_PATH` — path to JSON state file.
- `NEXORA_API_TOKEN_FILE` — path to API bearer token file.
- `NEXORA_DEPLOYMENT_SCOPE` — `operator` to restrict surfaces.
- `NEXORA_OPERATOR_ONLY_ENFORCE` — enforce operator-only mode.

## Conventions

- Strict tenant isolation via `tenant_id` enforcement on all routes.
- Token comparison: `secrets.compare_digest()`.
- No business logic in route handlers — delegate to `NexoraService`.

## Testing

```bash
PYTHONPATH=src python -m pytest tests/ -v --tb=short
```

API behavioral tests in `tests/test_p8_behavioral.py` and `tests/test_api_contract.py`.
