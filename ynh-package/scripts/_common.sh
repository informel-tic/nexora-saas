#!/bin/bash
# Shared helpers for Nexora YunoHost package lifecycle scripts.

# $port is auto-set by YunoHost from [resources.ports]; fall back for pre-install checks
NEXORA_PORT="${port:-${NEXORA_CONTROL_PLANE_PORT:-38120}}"
NEXORA_VENV="/opt/nexora/venv"
NEXORA_WHEEL_BUNDLE_DIR="${NEXORA_WHEEL_BUNDLE_DIR:-}"

nexora_validate_yunohost_version() {
  local ynh_version operation="${1:-install}"

  # Primary: dpkg-query (no YunoHost CLI lock — safe inside lifecycle scripts)
  ynh_version="$(dpkg-query -W -f='${Version}' yunohost 2>/dev/null \
    | grep -oP '\d+\.\d+(\.\d+)?' | head -1 || true)"

  # Fallback 1: yunohost CLI JSON (works outside lifecycle scripts)
  if [ -z "$ynh_version" ]; then
    ynh_version="$(yunohost tools version --output-as json 2>/dev/null \
      | python3 -c 'import json,sys; print(json.load(sys.stdin).get("yunohost",{}).get("version",""))' 2>/dev/null || true)"
  fi

  # Fallback 2: yunohost --version
  if [ -z "$ynh_version" ]; then
    ynh_version="$(yunohost --version 2>/dev/null | grep -oP '\d+\.\d+(\.\d+)?' | head -1 || true)"
  fi

  if [ -z "$ynh_version" ]; then
    ynh_die --message="Cannot detect YunoHost version."
  fi

  # Delegate exact version policy to the bootstrap compatibility service.
  # $install_dir / $data_dir are set by YunoHost resource provisioning before script body.
  local _repo_root="${install_dir:-/opt/nexora}/repo"
  local _state_path="${data_dir:-/opt/nexora/var}/state.json"
  local _venv_python="${NEXORA_VENV}/bin/python3"
  if [ -x "$_venv_python" ] && "$_venv_python" -c "import nexora_saas.bootstrap" 2>/dev/null; then
    "$_venv_python" -m nexora_saas.bootstrap assess-package-lifecycle \
      --repo-root "$_repo_root" \
      --state-path "$_state_path" \
      --operation "$operation" \
      --yunohost-version "$ynh_version" || ynh_die --message="YunoHost version $ynh_version is not compatible."
  else
    echo "Info: nexora_saas.bootstrap not available; skipping detailed compatibility check for YunoHost $ynh_version."
  fi
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
  chown root:"$app" "$role_file"
  chmod 640 "$role_file"
}

nexora_setup_venv() {
  local venv_dir="$1"
  local repo_dir="$2"
  # Use system python3 (not the bootstrap venv's) to create a clean virtualenv
  local sys_python3="/usr/bin/python3"
  "$sys_python3" -m venv "$venv_dir" || {
    apt-get install -y python3-venv python3-pip
    "$sys_python3" -m venv "$venv_dir"
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
