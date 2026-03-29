# scripts — CI & Utility Scripts

## Purpose

CI quality gates, build automation, and operational utility scripts.

## Script Map

### Python CI Gates

| Script | Purpose |
|--------|---------|
| `ci_check_saas_isolation.py` | Verify no `nexora_core` references leak into SaaS code |
| `ci_cost_report.py` | Parse JUnit XML to compute CI cost/timing reports |
| `docs_obsolescence_audit.py` | Detect obsolete docs (CI quality gate, `--enforce-removal`) |
| `load_test_multitenant.py` | Multi-tenant load testing with concurrent futures |
| `node_coherence_audit.py` | Audit node state coherence across fleet |
| `sync_version.py` | Sync `NEXORA_VERSION` across manifest files |
| `bootstrap_slo_summary.py` | Summarize bootstrap SLO metrics from JSONL logs |

### Shell Build/Release

| Script | Purpose |
|--------|---------|
| `build_offline_bundle.sh` | Build offline wheel installation bundle |
| `build_vm_offline_kit.sh` | Build VM-uploadable offline artifact |
| `check-root-test-artifacts.sh` | Check for stale test artifacts in root |
| `dev-compile-check.sh` | Dev-time syntax/compile check |
| `e2e_operator_matrix.sh` | End-to-end operator test matrix |
| `packagecheck-local.sh` | Local package validation |
| `release.sh` | Release automation |

## Conventions

- Python scripts are standalone CLIs with `argparse`.
- Shell scripts use `set -euo pipefail`.
- CI gates return non-zero exit code on failure for pipeline integration.
