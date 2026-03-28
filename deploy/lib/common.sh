#!/bin/bash
set -euo pipefail

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    echo "This script must run as root." >&2
    exit 1
  fi
}

get_repo_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd
}

count_existing_apps() {
  local raw
  raw="$(yunohost app list --output-as json 2>/dev/null || true)"
  python3 - <<'PY' "$raw"
import json, sys
raw = sys.argv[1]
try:
    data = json.loads(raw) if raw else {}
    print(len(data.get('apps', [])))
except Exception:
    print(0)
PY
}

path_conflict() {
  local domain="$1"
  local path="$2"
  local raw
  raw="$(yunohost app map --output-as json 2>/dev/null || true)"
  python3 - <<'PY' "$raw" "$domain" "$path"
import json, sys
raw, domain, path = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    data = json.loads(raw) if raw else {}
except Exception:
    print('no')
    raise SystemExit(0)
domain_map = data.get(domain, {}) if isinstance(data, dict) else {}
print('yes' if isinstance(domain_map, dict) and path in domain_map else 'no')
PY
}

suggest_path() {
  local domain="$1"
  local base="${2:-/nexora}"
  local candidate="$base"
  local n=1
  while [[ "$(path_conflict "$domain" "$candidate")" == "yes" ]]; do
    candidate="${base}-${n}"
    n=$((n+1))
  done
  echo "$candidate"
}

retry_cmd() {
  local max_attempts="$1"
  local sleep_seconds="$2"
  shift 2

  local attempt=1
  while true; do
    if "$@"; then
      return 0
    fi
    if [[ "$attempt" -ge "$max_attempts" ]]; then
      return 1
    fi
    echo "Command failed (attempt ${attempt}/${max_attempts}): $*"
    sleep "$sleep_seconds"
    attempt=$((attempt + 1))
  done
}

ensure_venv_with_pip() {
  local venv_dir="$1"
  local auto_install_python_venv_deps="${NEXORA_AUTO_INSTALL_PYTHON_VENV_DEPS:-yes}"

  if [[ ! -x "$venv_dir/bin/python" ]]; then
    if ! python3 -m venv "$venv_dir"; then
      if [[ "$auto_install_python_venv_deps" == "yes" ]]; then
        echo "python3 -m venv failed; installing python3-venv/python3-pip and retrying."
        DEBIAN_FRONTEND=noninteractive apt-get update -y
        DEBIAN_FRONTEND=noninteractive apt-get install -y python3-venv python3-pip
        python3 -m venv "$venv_dir"
      else
        echo "python3 -m venv failed and auto-install is disabled (NEXORA_AUTO_INSTALL_PYTHON_VENV_DEPS=no)." >&2
        echo "Install python3-venv and python3-pip, then re-run bootstrap." >&2
        exit 1
      fi
    fi
  fi

  if [[ ! -x "$venv_dir/bin/pip" ]]; then
    if ! "$venv_dir/bin/python" -m ensurepip --upgrade; then
      if [[ "$auto_install_python_venv_deps" == "yes" ]]; then
        echo "ensurepip is unavailable; reinstalling python3-venv/python3-pip and recreating venv."
        DEBIAN_FRONTEND=noninteractive apt-get update -y
        DEBIAN_FRONTEND=noninteractive apt-get install -y python3-venv python3-pip
        rm -rf "$venv_dir"
        python3 -m venv "$venv_dir"
      else
        echo "ensurepip is unavailable and auto-install is disabled (NEXORA_AUTO_INSTALL_PYTHON_VENV_DEPS=no)." >&2
        echo "Install python3-venv and python3-pip, then re-run bootstrap." >&2
        exit 1
      fi
    fi
  fi

  if [[ ! -x "$venv_dir/bin/pip" ]]; then
    echo "Unable to provision pip inside $venv_dir. Check python3-venv/python3-pip installation." >&2
    exit 1
  fi
}
