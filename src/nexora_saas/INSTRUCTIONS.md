# nexora_saas — SaaS Control-Plane Domain Modules

## Purpose

This package contains the domain logic for Nexora's sovereign SaaS control plane. It extends `nexora_node_sdk.NodeService` with multi-tenant fleet orchestration, governance, quotas, and SLA management.

## Entry Point

- `NexoraService` in `orchestrator.py` — main service class.
- `build_service()` in `runtime_context.py` — factory that creates a `NexoraService` from environment variables.

## Module Map

| Module | Responsibility |
|--------|---------------|
| `orchestrator.py` | `NexoraService` — top-level SaaS service |
| `fleet.py` | Multi-node inventory, drift detection, topology |
| `enrollment.py` | One-time enrollment tokens, challenge-response attestation |
| `multitenant.py` | Tenant isolation config |
| `subscription.py` | Organizations, plans (free/pro/enterprise) |
| `quotas.py` | Per-tier quota enforcement (nodes, apps, storage) |
| `feature_provisioning.py` | HMAC-signed feature push to enrolled nodes |
| `node_connector.py` | HTTP client pushing commands to node agents |
| `node_lifecycle.py` | Lifecycle state machine (register, suspend, revoke, retire) |
| `node_actions.py` | Production execution backends for node-agent actions |
| `security_audit.py` | Append-only SecurityJournal with HMAC tamper detection |
| `modes.py` | Runtime mode manager (observer < operator < architect < admin) |
| `governance.py` | Compliance scoring, risk assessment, executive reporting |
| `scoring.py` | Multi-axis scoring engine (security, PRA, health, compliance) |
| `sla.py` | SLA tiers, uptime tracking, compliance reporting |
| `automation.py` | Scheduled jobs, workflow templates |
| `notifications.py` | Alerting: webhooks, email, ntfy, gotify |
| `failover.py` | Health checks, automatic switchover |
| `migration.py` / `app_migration.py` | Docker↔YunoHost conversion, app migration between nodes |
| `preflight.py` | Unified mutation preflight checks |
| `bootstrap.py` | Bootstrap orchestration service |
| `adoption.py` | Adoption report for existing YunoHost installs |
| `admin_actions.py` | Destructive admin ops with audit trail |
| `operator_actions.py` | Safe, non-destructive operator-level actions |

## Conventions

- **Dataclasses + Pydantic** for models; no web framework coupling in domain logic.
- **Tenant isolation**: all records tagged with `tenant_id`; enforce strict scoping.
- **Security**: use `secrets.compare_digest()` for token comparison, `0o600` for token files.
- **Scoring engine** (`scoring.py`) is shared across governance, fleet, and SLA modules.

## Testing

```bash
PYTHONPATH=src python -m pytest tests/ -v --tb=short
```

Tests use `unittest.TestCase`. Domain modules are tested indirectly via API behavioral tests in `tests/test_p8_behavioral.py` and dedicated unit tests.
