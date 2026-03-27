"""
Nexora operator-mode deployment script.
Uploads the wheel + service files to the test YunoHost server and runs installation.
"""
from __future__ import annotations

import io
import os
import sys
import time
import paramiko

# ── Config ────────────────────────────────────────────────────────────────────
HOST = "192.168.1.52"
USER = "chonsrv1test"
PASS = "Leila112//!!&"

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
WHEEL_PATH = os.path.join(REPO_ROOT, "dist", "nexora_platform-2.0.0-py3-none-any.whl")
CP_SERVICE  = os.path.join(REPO_ROOT, "deploy", "templates", "nexora-control-plane.service")
NA_SERVICE  = os.path.join(REPO_ROOT, "deploy", "templates", "nexora-node-agent.service")

REMOTE_WHEEL = "/tmp/nexora_platform-2.0.0-py3-none-any.whl"
REMOTE_CP    = "/tmp/nexora-control-plane.service"
REMOTE_NA    = "/tmp/nexora-node-agent.service"
REMOTE_SCRIPT = "/tmp/nexora_install.sh"

# ── Install script (runs as root) ─────────────────────────────────────────────
INSTALL_SH = r"""#!/bin/bash
set -euo pipefail

WHEEL=/tmp/nexora_platform-2.0.0-py3-none-any.whl
VENV=/opt/nexora/venv
STATE=/opt/nexora/var
ETC=/etc/nexora
SYSTEMD=/etc/systemd/system
LOG=/var/log/nexora

echo "=== [1/8] Creating system user 'nexora' ==="
if ! id nexora &>/dev/null; then
  useradd --system --home-dir /opt/nexora --shell /usr/sbin/nologin nexora
  echo "  User created."
else
  echo "  User already exists."
fi

echo "=== [2/8] Creating directories ==="
mkdir -p "$STATE" "$ETC" "$LOG" /tmp/nexora-export
chown nexora:nexora "$STATE" "$LOG" /tmp/nexora-export

echo "=== [3/8] Creating Python venv ==="
if [[ ! -x "$VENV/bin/python" ]]; then
  python3 -m venv "$VENV"
  echo "  Venv created."
else
  echo "  Venv already exists."
fi

echo "=== [4/8] Installing wheel and dependencies ==="
"$VENV/bin/pip" install --upgrade pip --quiet
"$VENV/bin/pip" install "$WHEEL" --quiet
chown -R nexora:nexora /opt/nexora
echo "  Installation complete."

echo "=== [5/8] Writing operator role file ==="
cat > "$ETC/api-token-roles.json" << 'ROLES'
{}
ROLES
# Will be populated at first admin setup; file must exist for the service
chmod 600 "$ETC/api-token-roles.json"

echo "=== [6/8] Generating API token ==="
if [[ ! -f "$STATE/api-token" ]]; then
  python3 -c "import secrets; print(secrets.token_urlsafe(32))" > "$STATE/api-token"
  chmod 600 "$STATE/api-token"
  chown nexora:nexora "$STATE/api-token"
  echo "  Token generated."
else
  echo "  Token already present."
fi
echo "  API token is: $(cat $STATE/api-token)"

echo "=== [7/8] Installing systemd service files ==="
cp /tmp/nexora-control-plane.service "$SYSTEMD/nexora-control-plane.service"
cp /tmp/nexora-node-agent.service    "$SYSTEMD/nexora-node-agent.service"
systemctl daemon-reload

echo "=== [8/8] Enabling and starting services ==="
systemctl enable nexora-control-plane nexora-node-agent
systemctl restart nexora-control-plane nexora-node-agent
sleep 3

echo ""
echo "=== Service status ==="
systemctl status nexora-control-plane --no-pager -l || true
echo "---"
systemctl status nexora-node-agent --no-pager -l || true

echo ""
echo "=== Health check ==="
sleep 2
curl -sf http://127.0.0.1:38120/api/health || echo "  Control plane health FAILED"
echo ""
curl -sf http://127.0.0.1:38121/health || echo "  Node agent health FAILED"
echo ""
echo "=== DONE ==="
"""


def run_root_command(client: paramiko.SSHClient, cmd: str, label: str = "") -> tuple[str, str, int]:
    """Run a command with sudo -i, handling the password prompt."""
    transport = client.get_transport()
    chan = transport.open_session()
    chan.get_pty()
    # Wrap with sudo -i -S (reads password from stdin)
    full_cmd = f'echo {_sh_quote(PASS)} | sudo -S -i bash -c {_sh_quote(cmd)}'
    chan.exec_command(full_cmd)
    out_buf = io.BytesIO()
    while True:
        if chan.recv_ready():
            data = chan.recv(4096)
            if data:
                out_buf.write(data)
                sys.stdout.buffer.write(data)
                sys.stdout.flush()
        if chan.exit_status_ready() and not chan.recv_ready():
            break
        time.sleep(0.05)
    exit_code = chan.recv_exit_status()
    chan.close()
    return out_buf.getvalue().decode(errors="replace"), "", exit_code


def _sh_quote(s: str) -> str:
    """Single-quote a string safely for shell."""
    return "'" + s.replace("'", "'\"'\"'") + "'"


def main() -> None:
    print(f"Connecting to {HOST} as {USER}...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASS, timeout=15,
                   allow_agent=False, look_for_keys=False)
    print("Connected.")

    # ── Upload files via SFTP ────────────────────────────────────────────────
    print("\nUploading files via SFTP...")
    sftp = client.open_sftp()

    print(f"  wheel ({os.path.getsize(WHEEL_PATH)//1024} KB) → {REMOTE_WHEEL}")
    sftp.put(WHEEL_PATH, REMOTE_WHEEL)

    print(f"  control-plane service → {REMOTE_CP}")
    sftp.put(CP_SERVICE, REMOTE_CP)

    print(f"  node-agent service → {REMOTE_NA}")
    sftp.put(NA_SERVICE, REMOTE_NA)

    # Write install script
    with sftp.open(REMOTE_SCRIPT, "w") as f:
        f.write(INSTALL_SH)
    sftp.chmod(REMOTE_SCRIPT, 0o755)
    print(f"  install script → {REMOTE_SCRIPT}")

    sftp.close()
    print("Upload complete.\n")

    # ── Run install as root ──────────────────────────────────────────────────
    print("=" * 60)
    print("Running install script as root (sudo -S)...")
    print("=" * 60)

    # Use sudo -S to read password from stdin via echo
    install_cmd = (
        f"echo {_sh_quote(PASS)} | sudo -S bash {REMOTE_SCRIPT} 2>&1"
    )
    _, stdout, stderr = client.exec_command(install_cmd, timeout=300)
    for line in stdout:
        print(line, end="")
    err = stderr.read().decode(errors="replace").strip()
    if err:
        print("\nSTDERR:", err, file=sys.stderr)
    rc = stdout.channel.recv_exit_status()
    print(f"\nInstall script exited with code {rc}")

    # ── Final health check from local side ──────────────────────────────────
    if rc == 0:
        print("\nFinal check: are ports listening?")
        _, chk, _ = client.exec_command(
            "ss -tlnp 2>/dev/null | grep -E '38120|38121' || echo 'ports not found'"
        )
        print(chk.read().decode())

    client.close()
    print("Deployment complete." if rc == 0 else "Deployment FAILED.")
    sys.exit(rc)


if __name__ == "__main__":
    main()
