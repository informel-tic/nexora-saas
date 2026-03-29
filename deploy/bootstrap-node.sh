#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/deploy/lib/common.sh"
require_root

PROFILE="${PROFILE:-control-plane+node-agent}"
ENROLLMENT_MODE="${ENROLLMENT_MODE:-pull}"
TARGET_HOST="${TARGET_HOST:-localhost}"
DOMAIN="${DOMAIN:-}"
PATH_URL="${PATH_URL:-/nexora}"
MODE="${MODE:-augment}"
ALLOW_INSTALL_YUNOHOST="${ALLOW_INSTALL_YUNOHOST:-no}"
SKIP_NETWORK_PRECHECKS="${SKIP_NETWORK_PRECHECKS:-no}"
AUTO_INSTALL_BOOTSTRAP_DEPS="${NEXORA_AUTO_INSTALL_BOOTSTRAP_DEPS:-yes}"
ALLOW_NETWORK_PRECHECK_BYPASS="${NEXORA_ALLOW_NETWORK_PRECHECK_BYPASS:-yes}"
ALLOW_COHERENCE_BLOCKER_BYPASS="${NEXORA_ALLOW_COHERENCE_BLOCKER_BYPASS:-no}"
COHERENCE_BLOCKER_ALLOWLIST="${NEXORA_COHERENCE_BLOCKER_ALLOWLIST:-unsupported_distribution_non_debian}"
BOOTSTRAP_RETRY_ATTEMPTS="${NEXORA_BOOTSTRAP_RETRY_ATTEMPTS:-3}"
BOOTSTRAP_RETRY_DELAY_SECONDS="${NEXORA_BOOTSTRAP_RETRY_DELAY_SECONDS:-3}"
DEPLOYMENT_SCOPE="operator"
BOOTSTRAP_LOG="${BOOTSTRAP_LOG:-/var/log/nexora/bootstrap-node.log}"
BOOTSTRAP_SLO_LOG="${BOOTSTRAP_SLO_LOG:-/var/log/nexora/bootstrap-slo.jsonl}"
PACKAGE_DIR="$ROOT/ynh-package"
VENV_DIR="/opt/nexora/venv"
STATE_DIR="/opt/nexora/var"
SYSTEMD_DIR="/etc/systemd/system"
CERTS_DIR="$STATE_DIR/certs"

mkdir -p "$(dirname "$BOOTSTRAP_LOG")" "$STATE_DIR" "$CERTS_DIR"
exec > >(tee -a "$BOOTSTRAP_LOG") 2>&1

BOOTSTRAP_STARTED_AT="$(date +%s)"
emit_bootstrap_slo() {
  local exit_code="$1"
  local ended_at duration status reason
  ended_at="$(date +%s)"
  duration="$((ended_at - BOOTSTRAP_STARTED_AT))"
  status="success"
  reason=""
  if [[ "$exit_code" -ne 0 ]]; then
    status="failure"
    reason="$(tail -n1 "$BOOTSTRAP_LOG" 2>/dev/null | tr -d '\r' | sed 's/"/\\"/g')"
  fi
  mkdir -p "$(dirname "$BOOTSTRAP_SLO_LOG")"
  python3 - <<'PY' \
    "$BOOTSTRAP_SLO_LOG" "$status" "$duration" "$MODE" "$PROFILE" "$ENROLLMENT_MODE" "$DEPLOYMENT_SCOPE" "$reason"
import json
import sys
from datetime import datetime, timezone

path, status, duration, mode, profile, enrollment_mode, scope, reason = sys.argv[1:9]
record = {
    "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "status": status,
    "duration_seconds": int(duration),
    "mode": mode,
    "profile": profile,
    "enrollment_mode": enrollment_mode,
    "deployment_scope": scope,
    "reason": reason if status == "failure" else "",
}
with open(path, "a", encoding="utf-8") as fh:
    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
PY
}
trap 'emit_bootstrap_slo $?' EXIT

echo "==> Nexora bootstrap-node.sh"
echo "profile=$PROFILE enrollment_mode=$ENROLLMENT_MODE mode=$MODE target_host=$TARGET_HOST"

case "$PROFILE" in
  control-plane|node-agent-only|control-plane+node-agent) ;;
  *) echo "Unsupported PROFILE=$PROFILE" >&2; exit 1 ;;
esac


case "$ENROLLMENT_MODE" in
  push|pull) ;;
  *) echo "Unsupported ENROLLMENT_MODE=$ENROLLMENT_MODE" >&2; exit 1 ;;
esac

if [[ -z "$DOMAIN" && "$PROFILE" != "node-agent-only" ]]; then
  echo "Warning: DOMAIN is empty for control-plane profile."
  echo "Control-plane and node-agent services will be installed, but YunoHost app exposure is skipped."
fi

if [[ ! -r /etc/os-release ]]; then
  echo "Cannot read /etc/os-release" >&2
  exit 1
fi
# shellcheck disable=SC1091
source /etc/os-release
if [[ "${ID:-}" != "debian" || ! "${VERSION_ID:-}" =~ ^(11|12|13)([.].*)?$ ]]; then
  echo "Nexora bootstrap supports Debian 11.x/12.x/13.x on YunoHost nodes. Detected: ${ID:-unknown} ${VERSION_ID:-unknown}" >&2
  exit 1
fi
DEBIAN_MAJOR="${VERSION_ID%%.*}"
echo "OS precheck OK: ${PRETTY_NAME:-$ID $VERSION_ID} (debian_major=$DEBIAN_MAJOR)"
arch="$(dpkg --print-architecture)"
case "$arch" in
  amd64|arm64) ;;
  *) echo "Unsupported architecture: $arch" >&2; exit 1 ;;
esac
echo "Architecture OK: $arch"

required_cmds=(python3 jq systemctl getent timeout)
if [[ "$SKIP_NETWORK_PRECHECKS" != "yes" ]]; then
  required_cmds+=(curl)
fi
missing_cmds=()
for cmd in "${required_cmds[@]}"; do
  command -v "$cmd" >/dev/null 2>&1 || missing_cmds+=("$cmd")
done

if [[ "${#missing_cmds[@]}" -gt 0 ]]; then
  echo "Missing required commands: ${missing_cmds[*]}"
  if [[ "$AUTO_INSTALL_BOOTSTRAP_DEPS" == "yes" ]]; then
    install_pkgs=()
    for cmd in "${missing_cmds[@]}"; do
      case "$cmd" in
        python3) install_pkgs+=(python3) ;;
        jq) install_pkgs+=(jq) ;;
        curl) install_pkgs+=(curl) ;;
        timeout) install_pkgs+=(coreutils) ;;
        getent) install_pkgs+=(libc-bin) ;;
        systemctl) install_pkgs+=(systemd) ;;
      esac
    done
    if [[ "${#install_pkgs[@]}" -gt 0 ]]; then
      unique_pkgs=( $(printf '%s\n' "${install_pkgs[@]}" | sort -u) )
      echo "Installing missing bootstrap dependencies: ${unique_pkgs[*]}"
      retry_cmd "$BOOTSTRAP_RETRY_ATTEMPTS" "$BOOTSTRAP_RETRY_DELAY_SECONDS" apt-get update -y
      retry_cmd "$BOOTSTRAP_RETRY_ATTEMPTS" "$BOOTSTRAP_RETRY_DELAY_SECONDS" env DEBIAN_FRONTEND=noninteractive apt-get install -y "${unique_pkgs[@]}"
    fi
    for cmd in "${missing_cmds[@]}"; do
      command -v "$cmd" >/dev/null 2>&1 || { echo "Missing required command after auto-install: $cmd" >&2; exit 1; }
    done
  else
    echo "Set NEXORA_AUTO_INSTALL_BOOTSTRAP_DEPS=yes to auto-install missing commands." >&2
    exit 1
  fi
fi

if [[ "$SKIP_NETWORK_PRECHECKS" == "yes" ]]; then
  echo "Warning: SKIP_NETWORK_PRECHECKS=yes -> external DNS/connectivity prechecks are skipped."
else
  network_prechecks_ok="yes"
  timeout 10 getent hosts deb.debian.org >/dev/null || network_prechecks_ok="no"
  timeout 10 curl -fsSI https://repo.yunohost.org >/dev/null || network_prechecks_ok="no"
  if [[ "$network_prechecks_ok" != "yes" ]]; then
    if [[ "$ALLOW_NETWORK_PRECHECK_BYPASS" == "yes" ]]; then
      SKIP_NETWORK_PRECHECKS="yes"
      echo "Warning: network prechecks failed; continuing with degraded mode (SKIP_NETWORK_PRECHECKS=yes)."
      echo "If online installation fails, provide NEXORA_WHEEL_BUNDLE_DIR for offline install."
    else
      echo "Network prechecks failed (DNS/reachability)." >&2
      echo "Set NEXORA_ALLOW_NETWORK_PRECHECK_BYPASS=yes or SKIP_NETWORK_PRECHECKS=yes to proceed in controlled environments." >&2
      exit 1
    fi
  fi
fi

timedatectl status --no-pager >/dev/null 2>&1 || echo "Warning: timedatectl unavailable, NTP check skipped"
disk_kb="$(df --output=avail / | tail -1 | tr -d ' ')"
if [[ -z "$disk_kb" || "$disk_kb" -lt 1048576 ]]; then
  echo "At least 1 GiB free disk space is required." >&2
  exit 1
fi
echo "Disk space OK: ${disk_kb} KiB available"

extract_semver() {
  python3 -c 'import re,sys; raw=sys.stdin.read().strip(); m=re.search(r"(\d+\.\d+(?:\.\d+)?)", raw); print(m.group(1) if m else "")'
}

yunohost_version=""
yunohost_present="no"
if command -v yunohost >/dev/null 2>&1; then
  yunohost_present="yes"
  yunohost_version="$(
    (yunohost tools version --output-as json 2>/dev/null || true) \
      | python3 -c 'import json,sys; raw=sys.stdin.read().strip(); data=json.loads(raw) if raw else {}; print(data.get("yunohost",{}).get("version",""))' 2>/dev/null
  )"
  if [[ -z "$yunohost_version" ]]; then
    yunohost_version="$( (yunohost --version 2>/dev/null || true) | extract_semver )"
  fi
fi
if [[ -z "$yunohost_version" ]]; then
  dpkg_yunohost_version="$( (dpkg-query -W -f='${Version}\n' yunohost 2>/dev/null || true) | extract_semver )"
  if [[ -n "$dpkg_yunohost_version" ]]; then
    yunohost_present="yes"
    yunohost_version="$dpkg_yunohost_version"
  fi
fi

if [[ -z "$yunohost_version" ]]; then
  if [[ "$yunohost_present" == "yes" ]]; then
    echo "YunoHost appears installed but version detection failed (tried: yunohost tools version, yunohost --version, dpkg-query)." >&2
    echo "Please verify YunoHost CLI health, then rerun bootstrap." >&2
    exit 1
  fi
  if [[ "$ALLOW_INSTALL_YUNOHOST" != "yes" ]]; then
    echo "YunoHost is not installed. Refusing to continue without ALLOW_INSTALL_YUNOHOST=yes." >&2
    echo "Official sequence: Debian 12 prechecks -> install YunoHost -> validate versions -> install Nexora -> attest -> register fleet." >&2
    exit 1
  fi
  echo "Installing YunoHost (fresh Debian 12 bootstrap)..."
  bash <(curl -fsSL https://install.yunohost.org)
  yunohost_version="$(yunohost tools version --output-as json | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data.get("yunohost",{}).get("version",""))')"
fi

echo "Detected YunoHost version: ${yunohost_version:-unknown}"
compat_json="$(PYTHONPATH="$ROOT/src" python3 -m nexora_saas.bootstrap assess \
  --repo-root "$ROOT" \
  --state-path "$STATE_DIR/state.json" \
  --profile "$PROFILE" \
  --enrollment-mode "$ENROLLMENT_MODE" \
  --mode "$MODE" \
  --yunohost-version "$yunohost_version" \
  --target-host "$TARGET_HOST" \
  --domain "$DOMAIN" \
  --path-url "$PATH_URL"
)"
echo "Compatibility assessment: $compat_json"
if ! python3 - <<'PY' "$compat_json"
import json, sys
report=json.loads(sys.argv[1])
raise SystemExit(0 if report.get('success') and report.get('compatibility', {}).get('bootstrap_allowed') else 1)
PY
then
  echo "Bootstrap aborted: YunoHost version is not compatible with Nexora 2.0.0 baseline." >&2
  exit 1
fi

COHERENCE_REPORT_PATH="$STATE_DIR/node-coherence-report.json"
set +e
python3 "$ROOT/scripts/node_coherence_audit.py" \
  --scope "$DEPLOYMENT_SCOPE" \
  --profile "$PROFILE" \
  --mode "$MODE" \
  --yunohost-version "$yunohost_version" \
  --output "$COHERENCE_REPORT_PATH"
coherence_rc=$?
set -e
echo "Node coherence report: $COHERENCE_REPORT_PATH"

if [[ "$coherence_rc" -ne 0 ]]; then
  if [[ "$ALLOW_COHERENCE_BLOCKER_BYPASS" == "yes" ]]; then
    if python3 - <<'PY' "$COHERENCE_REPORT_PATH" "$COHERENCE_BLOCKER_ALLOWLIST"
import json
import sys
from pathlib import Path

report_path = Path(sys.argv[1])
allowlist = {item.strip() for item in sys.argv[2].split(',') if item.strip()}
report = json.loads(report_path.read_text(encoding='utf-8'))
blockers = set(report.get('blockers', []))
unknown = blockers - allowlist
if unknown:
    print(json.dumps({'status': 'blocked', 'unknown_blockers': sorted(unknown)}, ensure_ascii=False))
    raise SystemExit(1)
print(json.dumps({'status': 'bypass_allowed', 'blockers': sorted(blockers)}, ensure_ascii=False))
PY
    then
      echo "Warning: coherence blockers bypassed by policy allowlist: $COHERENCE_BLOCKER_ALLOWLIST"
    else
      echo "Node coherence audit blocked bootstrap with non-allowlisted blockers." >&2
      exit 1
    fi
  else
    echo "Node coherence audit blocked bootstrap. Set NEXORA_ALLOW_COHERENCE_BLOCKER_BYPASS=yes for controlled bypass." >&2
    exit 1
  fi
fi

if ! id nexora >/dev/null 2>&1; then
  useradd --system --home-dir /opt/nexora --shell /usr/sbin/nologin nexora
fi
mkdir -p /opt/nexora "$STATE_DIR" /tmp/nexora-export /var/log/yunohost-mcp-server "$CERTS_DIR"
chown -R nexora:nexora /opt/nexora /tmp/nexora-export /var/log/yunohost-mcp-server
# Ensure /tmp/nexora-export is recreated on reboot via tmpfiles.d
echo "d /tmp/nexora-export 0755 nexora nexora -" > /etc/tmpfiles.d/nexora.conf
mkdir -p /etc/nexora
if [[ ! -f /etc/nexora/api-token-roles.json ]]; then
  printf '{}\n' > /etc/nexora/api-token-roles.json
fi
chown root:root /etc/nexora/api-token-roles.json
chmod 600 /etc/nexora/api-token-roles.json

ensure_venv_with_pip "$VENV_DIR"

install_nexora_online() {
  retry_cmd "$BOOTSTRAP_RETRY_ATTEMPTS" "$BOOTSTRAP_RETRY_DELAY_SECONDS" "$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel
  retry_cmd "$BOOTSTRAP_RETRY_ATTEMPTS" "$BOOTSTRAP_RETRY_DELAY_SECONDS" "$VENV_DIR/bin/python" -m pip install "$ROOT"
}

BUNDLE_DIR="${NEXORA_WHEEL_BUNDLE_DIR:-$ROOT/dist/offline-bundle}"
WHEEL_DIR="$BUNDLE_DIR/wheels"
ALLOW_ONLINE_WHEEL_FALLBACK="${NEXORA_ALLOW_ONLINE_WHEEL_FALLBACK:-yes}"
if [[ -d "$WHEEL_DIR" ]] && compgen -G "$WHEEL_DIR/*.whl" > /dev/null; then
  NEXORA_WHEEL="$(find "$WHEEL_DIR" -maxdepth 1 -name 'nexora_platform-*.whl' | head -n1)"
  if [[ -z "$NEXORA_WHEEL" ]]; then
    if [[ "$ALLOW_ONLINE_WHEEL_FALLBACK" == "yes" ]]; then
      echo "Offline bundle found but nexora_platform wheel is missing in $WHEEL_DIR; falling back to online install."
      install_nexora_online
    else
      echo "Offline bundle found but nexora_platform wheel is missing in $WHEEL_DIR" >&2
      echo "Set NEXORA_ALLOW_ONLINE_WHEEL_FALLBACK=yes to allow online fallback for test environments." >&2
      exit 1
    fi
  else
    echo "Installing Nexora from offline wheel bundle: $WHEEL_DIR"
    retry_cmd "$BOOTSTRAP_RETRY_ATTEMPTS" "$BOOTSTRAP_RETRY_DELAY_SECONDS" "$VENV_DIR/bin/python" -m pip install --no-index --find-links "$WHEEL_DIR" "$NEXORA_WHEEL"
  fi
else
  install_nexora_online
fi

install_service() {
  local service_name="$1"
  install -m 0644 "$ROOT/deploy/templates/${service_name}.service" "$SYSTEMD_DIR/${service_name}.service"
  systemctl daemon-reload
  systemctl enable --now "$service_name"
}

disable_service() {
  local service_name="$1"
  if systemctl list-unit-files | grep -q "^${service_name}\.service"; then
    systemctl disable --now "$service_name" || true
  fi
}

case "$PROFILE" in
  control-plane)
    install_service nexora-control-plane
    disable_service nexora-node-agent
    ;;
  node-agent-only)
    install_service nexora-node-agent
    disable_service nexora-control-plane
    ;;
  control-plane+node-agent)
    install_service nexora-control-plane
    install_service nexora-node-agent
    ;;
esac

bootstrap_result="$(PYTHONPATH="$ROOT/src" python3 -m nexora_saas.bootstrap bootstrap-node \
  --repo-root "$ROOT" \
  --state-path "$STATE_DIR/state.json" \
  --profile "$PROFILE" \
  --enrollment-mode "$ENROLLMENT_MODE" \
  --mode "$MODE" \
  --yunohost-version "$yunohost_version" \
  --target-host "$TARGET_HOST" \
  --domain "$DOMAIN" \
  --path-url "$PATH_URL" \
  --enrolled-by "bootstrap-node.sh"
)"
echo "$bootstrap_result"
if ! python3 - <<'PY' "$bootstrap_result"
import json, sys
report=json.loads(sys.argv[1])
raise SystemExit(0 if report.get('success') else 1)
PY
then
  echo "Bootstrap state orchestration failed." >&2
  exit 1
fi

if [[ "$PROFILE" != "node-agent-only" && -n "$DOMAIN" ]]; then
  # YunoHost app service binds the same control-plane port; stop bootstrap unit first.
  disable_service nexora-control-plane
  if [[ "$MODE" == "fresh" ]]; then
    if [[ "$(path_conflict "$DOMAIN" "$PATH_URL")" == "yes" ]]; then
      echo "Requested DOMAIN/PATH already used by another YunoHost app." >&2
      echo "Suggested free path: $(suggest_path "$DOMAIN" "$PATH_URL")" >&2
      exit 1
    fi
    # Prepare local source archive and inject placeholders in manifest for offline-safe app install.
    SRC_ARCHIVE="$(bash "$ROOT/deploy/prepare-local-package.sh")"
    SRC_DIR="$(dirname "$SRC_ARCHIVE")"
    SRC_FILE="$(basename "$SRC_ARCHIVE")"
    SRC_HTTP_PORT="$(python3 - <<'PY'
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
PY
)"
    python3 -m http.server "$SRC_HTTP_PORT" --bind 127.0.0.1 --directory "$SRC_DIR" >/tmp/nexora-source-http.log 2>&1 &
    SRC_HTTP_PID="$!"
    sleep 1
    if ! kill -0 "$SRC_HTTP_PID" 2>/dev/null; then
      echo "Failed to start local source HTTP server for YunoHost package install." >&2
      exit 1
    fi
    SRC_URL="http://127.0.0.1:${SRC_HTTP_PORT}/${SRC_FILE}"
    MANIFEST_PATH="$PACKAGE_DIR/manifest.toml"
    MANIFEST_BAK="$PACKAGE_DIR/manifest.toml.bak"
    cp "$MANIFEST_PATH" "$MANIFEST_BAK"
    python3 - "$MANIFEST_PATH" "$SRC_ARCHIVE" "$SRC_URL" <<'PY'
from pathlib import Path
import hashlib
import sys

manifest = Path(sys.argv[1])
src = Path(sys.argv[2])
src_url = sys.argv[3]
sha = hashlib.sha256(src.read_bytes()).hexdigest()
text = manifest.read_text()
text = text.replace("__LOCAL_SOURCE_URL__", src_url)
text = text.replace("__LOCAL_SOURCE_SHA256__", sha)
manifest.write_text(text)
PY
    if ! yunohost app install "$PACKAGE_DIR" -a "domain=${DOMAIN}&path=${PATH_URL}" --force; then
      kill "$SRC_HTTP_PID" 2>/dev/null || true
      mv "$MANIFEST_BAK" "$MANIFEST_PATH"
      exit 1
    fi
    kill "$SRC_HTTP_PID" 2>/dev/null || true
    mv "$MANIFEST_BAK" "$MANIFEST_PATH"
  elif [[ "$MODE" == "adopt" ]]; then
    bash "$ROOT/deploy/bootstrap-adopt.sh"
  elif [[ "$MODE" == "augment" ]]; then
    bash "$ROOT/deploy/bootstrap-augment.sh"
  else
    echo "Unknown MODE=$MODE" >&2
    exit 1
  fi
elif [[ "$PROFILE" != "node-agent-only" ]]; then
  echo "Skipping YunoHost package installation because DOMAIN is not set."
fi

echo "Bootstrap completed successfully. Log: $BOOTSTRAP_LOG"
