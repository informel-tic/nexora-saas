# deploy — Deployment Scripts & Templates

## Purpose

Bootstrap scripts, systemd/nginx templates, and SQL RLS schemas for deploying Nexora on YunoHost nodes and the SaaS control plane.

## Entry Point

- `bootstrap-node.sh` — core node bootstrap (called by fresh/adopt/augment variants).
- `bootstrap-detect-mode.sh` — auto-detects the appropriate bootstrap mode.

## Script Map

| Script | Purpose |
|--------|---------|
| `bootstrap-fresh.sh` | Fresh install bootstrap |
| `bootstrap-adopt.sh` | Adopt existing YunoHost installation |
| `bootstrap-augment.sh` | Augment mode: add Nexora to running YunoHost |
| `bootstrap-node.sh` | Core node bootstrap logic |
| `bootstrap-full-platform.sh` | Full platform bootstrap (control plane + nodes) |
| `bootstrap-detect-mode.sh` | Auto-detect fresh/adopt/augment mode |
| `bootstrap-ynh-local.sh` | Local YunoHost bootstrap |
| `bootstrap-common.inc.sh` | Shared constants and functions (sourced by other scripts) |
| `deploy-subdomains.sh` | Subdomain deployment |
| `prepare-local-package.sh` | Build local package for install |
| `adoption-report.sh` | Generate adoption compatibility report |

## Subdirectories

### `lib/`
- `common.sh` — shared shell library sourced by bootstrap scripts.

### `sql_rls/`
- `init/001_base_schema.sql` — PostgreSQL base schema.
- `init/002_rls_policies.sql` — Row-Level Security policies for tenant isolation.
- `init/003_rls_operator_bypass.sql` — Operator bypass policies.
- `README.md` — RLS documentation.

### `templates/`
- `nexora-control-plane.service` / `nexora-node-agent.service` — systemd unit templates.
- `nginx-console.conf` / `nginx-saas.conf` / `nginx-www.conf` — nginx configuration templates.

## Conventions

- Shell scripts use `set -euo pipefail`.
- Environment variables control behavior: `MODE`, `PROFILE`, `ENROLLMENT_MODE`.
- Bootstrap scripts emit `/opt/nexora/var/node-coherence-report.json`.
- SQL RLS enforces tenant isolation at the database level.
- On isolated VMs, use `SKIP_NETWORK_PRECHECKS=yes`.
