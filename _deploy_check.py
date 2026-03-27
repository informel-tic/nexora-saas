"""Quick SSH reachability + environment check for the YunoHost test server."""
import paramiko
import sys

HOST = "192.168.1.52"
USER = "chonsrv1test"
PASS = "Leila112//!!&"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    client.connect(HOST, username=USER, password=PASS, timeout=15,
                   allow_agent=False, look_for_keys=False)
    cmds = [
        "echo === WHOAMI === && whoami",
        "uname -a",
        "python3 --version",
        "cat /etc/os-release | grep PRETTY_NAME",
        "df -h / | tail -1",
        "free -m | head -2",
        "systemctl is-active nexora-control-plane 2>/dev/null || echo nexora-control-plane: not-found",
        "systemctl is-active nexora-node-agent 2>/dev/null || echo nexora-node-agent: not-found",
        "test -d /opt/nexora && echo /opt/nexora EXISTS || echo /opt/nexora ABSENT",
        "which pip3 || echo pip3-absent",
        "pip3 --version 2>/dev/null || echo pip3-unavailable",
    ]
    _, stdout, stderr = client.exec_command(" && ".join(cmds))
    print(stdout.read().decode())
    err = stderr.read().decode().strip()
    if err:
        print("STDERR:", err, file=sys.stderr)
    client.close()
    print("SSH OK")
except Exception as e:
    print(f"SSH ERROR: {e}", file=sys.stderr)
    sys.exit(1)
