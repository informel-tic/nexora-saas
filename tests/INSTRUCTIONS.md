# tests — Test Suite

## Purpose

Comprehensive test suite covering API contracts, domain logic, behavioral scenarios, documentation integrity, and CI guardrails.

## Running Tests

```bash
PYTHONPATH=src python -m pytest tests/ -v --tb=short
```

## Conventions

- **All tests use `unittest.TestCase`** (class-based). Do not use pytest-style functions.
- **`pythonpath = ["src"]`** configured in `pyproject.toml`.
- **No pytest fixtures** — use `unittest.setUp()` / `unittest.mock` patterns.
- **Naming**: `test_<domain>.py` for domain tests, `test_<phase>_behavioral.py` for phase-specific behavioral tests.

## Test Categories

| Category | Files | Purpose |
|----------|-------|---------|
| API contracts | `test_api_contract.py`, `test_stub_free_endpoints.py` | Verify API surface correctness |
| Behavioral | `test_p8_behavioral.py`, `test_orchestrator_behavior.py` | Phase-specific end-to-end behavior |
| Domain | `test_enrollment.py`, `test_subscription.py`, `test_node_lifecycle.py`, etc. | Unit tests for domain modules |
| Multi-tenancy | `test_multitenant_extended.py`, `test_ws9_multitenancy.py` | Tenant isolation verification |
| Documentation | `test_docs_completeness.py`, `test_docs_inventory_contract.py`, `test_docs_obsolescence_contract.py` | Docs quality gates |
| CI | `test_ci_guardrails.py` | CI pipeline integrity |
| Packaging | `test_packaging.py`, `test_runtime_boundaries.py` | Package structure and boundaries |

## Fixtures

- `fixtures/inventory_experimental.json` — experimental inventory data for testing.
- `fixtures/inventory_healthy.json` — healthy inventory data for testing.

## Documentation Tests (Critical)

These tests enforce documentation hygiene and will fail if docs are inconsistent:

- `test_docs_inventory_contract.py` — `docs_inventory.yaml` must exactly match real docs files and count.
- `test_docs_completeness.py` — all docs must have titles and no broken relative links.
- `test_docs_obsolescence_contract.py` — no docs may contain obsolescence markers.
