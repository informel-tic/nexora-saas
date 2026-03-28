# Nexora SaaS & Multi-Tenancy Strategy

This document defines Nexora's sovereign SaaS architecture, including recursive internal hosting, strict multi-tenancy and subscription enforcement.

## 0. Recursive Sovereign SaaS Reference Architecture

- **Internal infrastructure**: Nexora operates an internal YunoHost fleet.
- **Dogfooding**: Nexora manages this fleet through Nexora itself.
- **SaaS runtime**: Control Plane + Console + MCP are deployed on that internal fleet.
- **Client perimeter**: customers enroll external YunoHost nodes; they do not self-host the full Nexora product.

## 1. Multi-Tenancy Model

Nexora uses a "Logical Isolation" model on a shared control plane with strict tenant scoping:
- **Organization**: Legal entity owning one or more tenants.
- **Tenant**: Isolated environment (fleet) with its own nodes, secrets, and audit logs.
- **Data Isolation**: All records (nodes, events, secrets, telemetry, jobs) are tagged with `tenant_id`. API access is restricted by tenant scope.

### Execution status (2026-03-24 refresh)

- **Implemented**: fleet-level tenant isolation, tenant-aware snapshot diff, optional token→tenant scope binding.
- **In progress**: full governance/security route scoping and complete cross-tenant contract tests.
- **Planned (Phase 9)**: auth claim binding, runtime app/storage quotas, and tenant usage-vs-quota observability endpoint.

## 2. Horizontal Scaling Strategy (WS9-T03)

To support thousands of tenants and nodes, the Nexora Control Plane will transition from a local JSON state to a distributed architecture.

### Database Transition
- **Current**: mixed local state backends (`state.json`) and progressive durable stores.
- **Target**: **PostgreSQL** with Row-Level Security (RLS).
- **Rationale**: PostgreSQL provides the consistency and concurrency needed for multiple API instances. RLS adds a secondary layer of tenant isolation at the database level.

### Stateless API
- The FastAPI control plane will be fully stateless.
- Session state (if any) will be moved to **Redis**.
- Background tasks (orchestration, heartbeats) will be handled by a distributed task queue (e.g., **Celery** or **Temporal**).

### Load Balancing
- **Nginx/HAProxy** or an Ingress Controller will distribute traffic across multiple Control Plane instances.
- Sticky sessions are not required due to statelessness.

## 3. Resource Quotas & Entitlements (WS9-T04)

Tenants are subject to limits based on their subscription tier.

| Tier | Max Nodes | Max Apps | Features |
| :--- | :--- | :--- | :--- |
| **Free** | 5 | 10 | Basic monitoring, local backups |
| **Pro** | 50 | 100 | Advanced observability, PRA, Support |
| **Enterprise** | Unlimited | Unlimited | Custom compliance, Multi-region, 24/7 Support |

Current implementation note: node quota (`max_nodes`) is enforced on enrollment. Runtime enforcement for `max_apps_per_node` and `max_storage_gb` is tracked in active Phase 9 tasks.

## 4. Support Model (client-facing)

| Metric | Client Experience |
| :--- | :--- |
| **Maintenance** | Nexora-managed SaaS control plane |
| **Data Residency** | Sovereign cloud operated by Nexora |
| **Updates** | Continuous deployment by operator |
| **Control** | Managed interface with tenant-scoped permissions |

Operator self-hosting remains internal and is not a client product offering.

## 5. Compliance & Governance (WS9-T06)

- **Audit**: Every action is recorded in a tenant-scoped security journal with HMAC integrity.
- **Encryption**: Secrets are isolated per tenant in the `SecretStore` and encrypted at rest.
- **GDPR**: Data deletion (offboarding) is guaranteed via tenant-scoped purging logic.
