# nexora_node_sdk — Shared Node SDK

## Purpose

Foundation package shared by both the SaaS control plane and node agents. Provides node identity, state management, authentication, and all domain primitives that don't depend on a specific deployment context.

## Entry Point

- `NodeService` in `node_service.py` — base service class (extended by SaaS `NexoraService`).
- `NEXORA_IDENTITY` exported from `__init__.py`.
- `NEXORA_VERSION` in `version.py` — single source of truth for project version.

## Key Subpackages

### `auth/` — Authentication & Security (7 modules)

Refactored from a monolithic `auth.py` into focused submodules. All symbols re-exported at `auth/__init__.py` for backward compatibility.

| Module | Responsibility |
|--------|---------------|
| `_token.py` | Token I/O, rotation, session helpers |
| `_scopes.py` | Tenant & actor scope resolution, role validators |
| `_rate_limit.py` | Auth failure rate limiting (file-backed) |
| `_middleware.py` | HTTP middlewares (TokenAuth, SecurityHeaders, CSRF) |
| `_secret_store.py` | SecretStore with scoped secret isolation |
| `_owner_session.py` | Owner passphrase-based session management |

### Other Key Modules

| Module | Responsibility |
|--------|---------------|
| `state.py` | JSON state store, node record normalization |
| `identity.py` / `identity_lifecycle.py` | Node identity management |
| `capabilities.py` + `capabilities.yaml` | Canonical capability catalog |
| `compatibility.py` + `compatibility.yaml` | Nexora↔YunoHost compatibility matrix |
| `persistence.py` | Persistence abstraction layer |
| `trust.py` / `trust_policy.py` | Trust lifecycle management |
| `fleet.py` | Fleet-level operations |
| `governance.py` | Governance primitives |
| `pra.py` | PRA (Plan de Reprise d'Activité) |

## Conventions

- **Timing-safe token comparison**: always `secrets.compare_digest()`, never `==`.
- **Token file permissions**: `0o600`.
- **Backward compatibility**: `auth/__init__.py` re-exports all symbols from submodules.
- **YAML catalogs**: capabilities and compatibility data stored as YAML, loaded at import time.

## Testing

```bash
PYTHONPATH=src python -m pytest tests/ -v --tb=short
```
