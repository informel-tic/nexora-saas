"""Final health checks on both Nexora services."""
import paramiko, sys, json

HOST = "192.168.1.52"
USER = "chonsrv1test"
PASS = "Leila112//!!&"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASS, timeout=15,
               allow_agent=False, look_for_keys=False)

cmds = [
    # Control plane: correct path
    "curl -sf http://127.0.0.1:38120/api/health | python3 -m json.tool --no-ensure-ascii 2>/dev/null | head -5",
    # Node agent: correct path is /health not /api/health
    "curl -sf http://127.0.0.1:38121/health | python3 -m json.tool --no-ensure-ascii 2>/dev/null | head -5",
    # Service states
    "systemctl is-active nexora-control-plane nexora-node-agent",
    # Logs last 5 lines each
    "journalctl -u nexora-control-plane -n 5 --no-pager 2>/dev/null",
    "journalctl -u nexora-node-agent -n 5 --no-pager 2>/dev/null",
]

for cmd in cmds:
    print(f"\n>>> {cmd[:80]}")
    _, stdout, stderr = client.exec_command(cmd)
    print(stdout.read().decode(errors="replace").strip())
    err = stderr.read().decode(errors="replace").strip()
    if err: print("STDERR:", err)

client.close()
