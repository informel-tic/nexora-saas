#!/bin/bash
# bootstrap-full-platform.sh — Complete Nexora SaaS platform deployment
#
# Orchestrates:
#   1. bootstrap-node.sh (services, venv, systemd, YunoHost app)
#   2. deploy-subdomains.sh (3-domain nginx: saas.*, www.*, console.*)
#   3. Owner passphrase initialization (optional)
#
# Required env:
#   DOMAIN=<base-domain>     (e.g. srv2testrchon.nohost.me)
#
# Optional env:
#   MODE=auto|fresh|adopt|augment  (default: auto)
#   PROFILE=control-plane+node-agent|control-plane|node-agent-only  (default: control-plane+node-agent)
#   ENROLLMENT_MODE=push|pull  (default: pull)
#   PORT=<backend-port>  (default: 38120)
#   OWNER_PASSPHRASE=<secret>  (if set, configures owner auth automatically)
#   SKIP_SUBDOMAINS=yes  (skip subdomain deployment)
#
# Usage:
#   DOMAIN=srv2testrchon.nohost.me bash deploy/bootstrap-full-platform.sh
#   DOMAIN=srv2testrchon.nohost.me OWNER_PASSPHRASE=MySecret123 bash deploy/bootstrap-full-platform.sh

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${MODE:-auto}"
PROFILE="${PROFILE:-control-plane+node-agent}"
ENROLLMENT_MODE="${ENROLLMENT_MODE:-pull}"
DOMAIN="${DOMAIN:-}"
PORT="${PORT:-38120}"
SKIP_SUBDOMAINS="${SKIP_SUBDOMAINS:-no}"
OWNER_PASSPHRASE="${OWNER_PASSPHRASE:-}"

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

if [[ -z "$DOMAIN" ]]; then
  echo "ERROR: DOMAIN must be set. Example: DOMAIN=srv2testrchon.nohost.me" >&2
  exit 1
fi

echo "=== Nexora Full Platform Bootstrap ==="
echo "DOMAIN=$DOMAIN  MODE=$MODE  PROFILE=$PROFILE  PORT=$PORT"
echo ""

# --- Phase 1: Core bootstrap (services + YunoHost app) ---
echo "=== Phase 1/3: Core platform bootstrap ==="
if [[ "$MODE" == "auto" ]]; then
  MODE="$(bash "$ROOT/deploy/bootstrap-detect-mode.sh")"
fi

set +e
env MODE="$MODE" PROFILE="$PROFILE" ENROLLMENT_MODE="$ENROLLMENT_MODE" DOMAIN="$DOMAIN" \
  bash "$ROOT/deploy/bootstrap-node.sh"
rc=$?
set -e

if [[ "$rc" -ne 0 ]]; then
  print_incident_hints
  exit "$rc"
fi
echo ""
echo "Phase 1 complete: services running."

# --- Phase 2: 3-domain subdomain deployment ---
if [[ "$SKIP_SUBDOMAINS" == "yes" ]]; then
  echo "=== Phase 2/3: Subdomain deployment SKIPPED (SKIP_SUBDOMAINS=yes) ==="
else
  echo "=== Phase 2/3: Deploying 3-domain architecture ==="
  echo "  saas.${DOMAIN}     → Owner console (passphrase auth)"
  echo "  www.${DOMAIN}      → Public subscription site"
  echo "  console.${DOMAIN}  → Subscriber console (token auth)"
  echo ""
  bash "$ROOT/deploy/deploy-subdomains.sh" "$DOMAIN" "$PORT"
  echo ""
  echo "Phase 2 complete: nginx vhosts deployed."
fi

# --- Phase 3: Owner passphrase setup ---
echo "=== Phase 3/3: Post-install configuration ==="

# Wait for control plane to be ready
echo "Waiting for control plane to become ready..."
attempts=0
max_attempts=30
while ! curl -sf "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1; do
  attempts=$((attempts + 1))
  if [[ "$attempts" -ge "$max_attempts" ]]; then
    echo "WARNING: Control plane did not respond after ${max_attempts}s. Continuing anyway."
    break
  fi
  sleep 1
done

if [[ -n "$OWNER_PASSPHRASE" ]]; then
  echo "Setting owner passphrase..."
  http_code=$(curl -sf -o /dev/null -w '%{http_code}' \
    -X POST "http://127.0.0.1:${PORT}/api/auth/owner-passphrase" \
    -H 'Content-Type: application/json' \
    -H 'X-Nexora-Action: setup' \
    -d "{\"passphrase\": \"${OWNER_PASSPHRASE}\"}" 2>/dev/null || echo "000")
  if [[ "$http_code" == "200" || "$http_code" == "409" ]]; then
    echo "  Owner passphrase configured."
  else
    echo "  WARNING: Owner passphrase setup returned HTTP ${http_code}. Configure manually."
  fi
else
  echo "  OWNER_PASSPHRASE not set — skipping automatic owner passphrase setup."
  echo "  Set it manually:"
  echo "    curl -X POST https://saas.${DOMAIN}/api/auth/owner-passphrase \\"
  echo "      -H 'Content-Type: application/json' -H 'X-Nexora-Action: setup' \\"
  echo "      -d '{\"passphrase\": \"your-secret-passphrase\"}'"
fi

# Ensure operator tenant state
echo "Ensuring operator tenant state..."
curl -sf "http://127.0.0.1:${PORT}/api/console/access-context" \
  -H "Authorization: Bearer $(cat /opt/nexora/var/api-token 2>/dev/null || echo none)" \
  -H "X-Nexora-Actor-Role: admin" >/dev/null 2>&1 || true

echo ""
echo "============================================="
echo "  Nexora Full Platform — Deployment Complete"
echo "============================================="
echo ""
echo "  Public site:        https://www.${DOMAIN}/"
echo "  Subscriber console: https://console.${DOMAIN}/"
echo "  Owner console:      https://saas.${DOMAIN}/"
echo ""
echo "  API health:         https://saas.${DOMAIN}/api/health"
echo "  API token:          /opt/nexora/var/api-token"
echo ""
echo "  Logs:               journalctl -u nexora-control-plane -f"
echo "============================================="
