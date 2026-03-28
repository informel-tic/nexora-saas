#!/bin/bash
# Shared helpers for Nexora YunoHost package lifecycle scripts.

NEXORA_PORT="${NEXORA_CONTROL_PLANE_PORT:-38120}"
NEXORA_VENV="/opt/nexora/venv"
NEXORA_WHEEL_BUNDLE_DIR="${NEXORA_WHEEL_BUNDLE_DIR:-}"

# Ensure python3 resolves nexora_saas modules via the Nexora venv
export PATH="${NEXORA_VENV}/bin:${PATH}"

nexora_validate_yunohost_version() {
  local ynh_version
  ynh_version="$(yunohost tools version --output-as json 2>/dev/null \
    | python3 -c 'import json,sys; print(json.load(sys.stdin).get("yunohost",{}).get("version",""))' 2>/dev/null || true)"
  if [ -z "$ynh_version" ]; then
    ynh_version="$(yunohost --version 2>/dev/null | grep -oP '\d+\.\d+(\.\d+)?' | head -1 || true)"
  fi
  if [ -z "$ynh_version" ]; then
    ynh_die --message="Cannot detect YunoHost version."
  fi
  python3 -m nexora_saas.bootstrap assess-package-lifecycle \
    --operation install \
    --yunohost-version "$ynh_version" || ynh_die --message="YunoHost version $ynh_version is not compatible."
}

nexora_abort_if_port_busy() {
  if ss -tlnp | grep -q ":${NEXORA_PORT} "; then
    ynh_die --message="Port ${NEXORA_PORT} is already in use."
  fi
}

nexora_setup_operator_role_lock() {
  local role_file="/etc/nexora/api-token-roles.json"
  mkdir -p "$(dirname "$role_file")"
  if [ ! -f "$role_file" ]; then
    printf '{}\n' > "$role_file"
  fi
  chown root:root "$role_file"
  chmod 600 "$role_file"
}

nexora_setup_venv() {
  local venv_dir="$1"
  local repo_dir="$2"
  python3 -m venv "$venv_dir" || {
    apt-get install -y python3-venv python3-pip
    python3 -m venv "$venv_dir"
  }
  "$venv_dir/bin/python" -m pip install --upgrade pip setuptools wheel

  if [ -n "$NEXORA_WHEEL_BUNDLE_DIR" ] && compgen -G "$NEXORA_WHEEL_BUNDLE_DIR/wheels/*.whl" > /dev/null 2>&1; then
    local nexora_wheel
    nexora_wheel="$(find "$NEXORA_WHEEL_BUNDLE_DIR/wheels" -maxdepth 1 -name 'nexora_platform-*.whl' | head -n1)"
    if [ -n "$nexora_wheel" ]; then
      "$venv_dir/bin/python" -m pip install --no-index --find-links "$NEXORA_WHEEL_BUNDLE_DIR/wheels" "$nexora_wheel"
      return
    fi
  fi
  "$venv_dir/bin/python" -m pip install "$repo_dir"
}
