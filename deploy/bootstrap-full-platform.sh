#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${MODE:-auto}"
PROFILE="${PROFILE:-control-plane+node-agent}"
ENROLLMENT_MODE="${ENROLLMENT_MODE:-pull}"
print_incident_hints() {
  cat <<'EOF'
Bootstrap failed. Common bypass knobs for controlled environments:
- Missing commands/deps: set NEXORA_AUTO_INSTALL_BOOTSTRAP_DEPS=yes
- Network prechecks failing: set NEXORA_ALLOW_NETWORK_PRECHECK_BYPASS=yes or SKIP_NETWORK_PRECHECKS=yes
- Coherence blockers (lab only): set NEXORA_ALLOW_COHERENCE_BLOCKER_BYPASS=yes and tune NEXORA_COHERENCE_BLOCKER_ALLOWLIST
- Missing YunoHost on fresh host: set ALLOW_INSTALL_YUNOHOST=yes
- Python venv/pip bootstrap issues: set NEXORA_AUTO_INSTALL_PYTHON_VENV_DEPS=yes
- Flaky package installs: tune NEXORA_BOOTSTRAP_RETRY_ATTEMPTS / NEXORA_BOOTSTRAP_RETRY_DELAY_SECONDS

See docs/DEPLOYMENT.md (section incidents bloquants full plateforme SaaS).
EOF
}

if [[ "$MODE" == "auto" ]]; then
  MODE="$(bash "$ROOT/deploy/bootstrap-detect-mode.sh")"
fi

set +e
env MODE="$MODE" PROFILE="$PROFILE" ENROLLMENT_MODE="$ENROLLMENT_MODE" bash "$ROOT/deploy/bootstrap-node.sh"
rc=$?
set -e

if [[ "$rc" -ne 0 ]]; then
  print_incident_hints
  exit "$rc"
fi
