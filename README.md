# Nexora SaaS Control Plane

**Sovereign SaaS control-plane for multi-node YunoHost orchestration.**

[![CI](https://github.com/informel-tic/nexora-saas/actions/workflows/ci-operator.yml/badge.svg)](https://github.com/informel-tic/nexora-saas/actions/workflows/ci-operator.yml)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)

---

Nexora is a **professional overlay** on top of YunoHost that adds multi-node fleet management, AI automation (MCP), PRA compliance, governance, and multi-tenancy — without modifying YunoHost core.

## Architecture

```
Layer C — Control Plane (FastAPI) + Console (vanilla JS) + MCP (AI adapter)
Layer B — Node Agent + overlay + identity/trust lifecycle
Layer A — YunoHost runtime (untouched)
```

### Component map

| Directory | Purpose |
|-----------|---------|
| `src/nexora_saas/` | Shared domain modules (fleet, security, blueprints, PRA, SLA…) |
| `src/yunohost_mcp/` | AI-facing automation interface (Model Context Protocol) |
| `apps/control_plane/` | FastAPI backend + entry point |
| `apps/console/` | Vanilla JS operator UI (no framework) |
| `blueprints/` | Business templates (MSP, PME, ecommerce, agency, training…) |
| `deploy/` | Bootstrap scripts, templates, SQL RLS |
| `ynh-package/` | YunoHost packaging (manifest, install/remove scripts) |

## Features

- **Fleet management** — enroll, monitor, and orchestrate multiple YunoHost nodes
- **Multi-tenancy** — strict tenant isolation with quota tiers (Free/Pro/Enterprise)
- **Docker overlay** — deploy Docker Hub services on fleet nodes with full rollback
- **AI automation** — MCP server for natural language infrastructure management
- **PRA compliance** — automated backup snapshots, SLA tracking, recovery procedures
- **Security** — CIS scoring, drift detection, timing-safe auth, mTLS, RBAC
- **Blueprints** — pre-built profiles for MSP, PME, ecommerce, agency, studio, training
- **Console** — zero-dependency operator dashboard (vanilla JS)

## Quick Start

```bash
# Deploy on a YunoHost server (operator mode)
bash deploy/bootstrap-full-platform.sh

# Resilient mode for constrained environments (network/deps/venv incidents)
NEXORA_AUTO_INSTALL_BOOTSTRAP_DEPS=yes \
NEXORA_AUTO_INSTALL_PYTHON_VENV_DEPS=yes \
NEXORA_ALLOW_NETWORK_PRECHECK_BYPASS=yes \
bash deploy/bootstrap-full-platform.sh

# Or install as YunoHost app
yunohost app install https://github.com/informel-tic/nexora-saas
```

## Build & Test

```bash
# Run all tests (PYTHONPATH=src is mandatory)
PYTHONPATH=src python -m pytest tests/ -v --tb=short

# Lint
ruff check src/ apps/

# Security scan
bandit -r src/ apps/ -ll

# Multi-tenant load test
PYTHONPATH=src python scripts/load_test_multitenant.py --tenants 12 --requests 1500
```

## Deployment Modes

| Mode | Description |
|------|-------------|
| `fresh` | New YunoHost server → Nexora installed from scratch |
| `adopt` | Existing YunoHost with apps → Nexora adopts and manages |
| `augment` | Running YunoHost → Nexora adds orchestration without disruption |

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for full procedures.

## API

REST API under `/api/v1*`. See [docs/API_SURFACE_REFERENCE.md](docs/API_SURFACE_REFERENCE.md).

Auth: `Authorization: Bearer <token>` or `X-Nexora-Token: <token>`

## Documentation

| Document | Content |
|----------|---------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 3-layer model, component boundaries |
| [docs/API_SURFACE_REFERENCE.md](docs/API_SURFACE_REFERENCE.md) | REST API contract |
| [docs/SECURITY.md](docs/SECURITY.md) | Threat model, auth, multi-tenant isolation |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Operator installation guide |
| [docs/RUNBOOKS.md](docs/RUNBOOKS.md) | Operational procedures |
| [docs/CONSOLE_OPERATOR_GUIDE.md](docs/CONSOLE_OPERATOR_GUIDE.md) | Console operator manual |
| [docs/SAAS_STRATEGY.md](docs/SAAS_STRATEGY.md) | SaaS business model |
| [docs/CI_QUALITY_GATES.md](docs/CI_QUALITY_GATES.md) | PR validation gates |
| [docs/TECH_DEBT_REGISTER.md](docs/TECH_DEBT_REGISTER.md) | Known issues and debt |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | Release notes |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Feature roadmap |

## License

AGPL-3.0-or-later
