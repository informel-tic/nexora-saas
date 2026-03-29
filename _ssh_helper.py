"""SSH helper for Nexora deployment to test server."""
import paramiko
import sys
import os

HOST = "192.168.1.125"
USER = "srv2rchon"
PASS = "Leila112//!!&"


def get_client():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        HOST, port=22, username=USER, password=PASS,
        timeout=15, auth_timeout=15, banner_timeout=15,
        allow_agent=False, look_for_keys=False,
    )
    return client


def sudo_exec(client, cmd):
    """Execute a command with sudo, piping password via stdin."""
    full_cmd = f"sudo -S bash -c '{cmd}'"
    stdin, stdout, stderr = client.exec_command(full_cmd, get_pty=True)
    stdin.write(PASS + "\n")
    stdin.flush()
    out = stdout.read().decode()
    err = stderr.read().decode()
    # Filter sudo prompt lines
    lines = [l for l in out.split("\n") if not l.startswith("[sudo]") and "password" not in l.lower()]
    return "\n".join(lines).strip(), err.strip()


def run(client, cmd):
    """Execute a command without sudo."""
    stdin, stdout, stderr = client.exec_command(cmd)
    return stdout.read().decode().strip(), stderr.read().decode().strip()


def upload_file(client, local_path, remote_path):
    """Upload a file via SFTP."""
    sftp = client.open_sftp()
    sftp.put(local_path, remote_path)
    sftp.close()


def upload_dir(client, local_dir, remote_dir):
    """Upload a directory recursively via SFTP."""
    sftp = client.open_sftp()
    _upload_dir_recursive(sftp, local_dir, remote_dir)
    sftp.close()


def _upload_dir_recursive(sftp, local_dir, remote_dir):
    try:
        sftp.stat(remote_dir)
    except FileNotFoundError:
        sftp.mkdir(remote_dir)
    for item in os.listdir(local_dir):
        local_path = os.path.join(local_dir, item)
        remote_path = remote_dir + "/" + item
        if os.path.isdir(local_path):
            # Skip __pycache__, .git, .venv, node_modules
            if item in ("__pycache__", ".git", ".venv", "node_modules", ".venvaudit", "_ext"):
                continue
            _upload_dir_recursive(sftp, local_path, remote_path)
        else:
            sftp.put(local_path, remote_path)


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "recon"
    client = get_client()

    if action == "recon":
        print("=== Server Reconnaissance ===")
        cmds = [
            ("whoami", False),
            ("hostname", False),
            ("ls -la /opt/nexora/", True),
            ("ls -la /opt/nexora/var/ 2>/dev/null || echo empty", True),
            ("cat /opt/nexora/var/config.env 2>/dev/null || echo no_config", True),
            ("systemctl list-units --type=service | grep -i nexora || echo no_svc", True),
            ("ls /etc/systemd/system/ | grep -i nexora || echo no_svc_file", True),
            ("cat /etc/nginx/conf.d/srv2testrchon.nohost.me.d/*.conf 2>/dev/null || echo no_nginx", True),
            ("ls -la /opt/nexora/venv/bin/ 2>/dev/null | head -10 || echo no_venv", True),
            ("cat /opt/nexora/venv/pyvenv.cfg 2>/dev/null || echo no_cfg", True),
            ("/opt/nexora/venv/bin/python --version 2>/dev/null || echo no_py", True),
            ("ls -la /opt/nexora/src/ 2>/dev/null || echo no_src", True),
            ("ls -la /opt/nexora/apps/ 2>/dev/null || echo no_apps", True),
        ]
        for cmd, use_sudo in cmds:
            out, err = (sudo_exec(client, cmd) if use_sudo else run(client, cmd))
            print(f"\n--- {cmd} ---")
            if out:
                print(out)
        print("\nDone.")

    elif action == "test-sudo":
        out, err = sudo_exec(client, "whoami")
        print(f"sudo whoami: {out}")
        print(f"err: {err}")

    elif action == "exec":
        # Run arbitrary command: python _ssh_helper.py exec "ls -la"
        cmd = sys.argv[2]
        use_sudo = "--sudo" in sys.argv
        if use_sudo:
            out, err = sudo_exec(client, cmd)
        else:
            out, err = run(client, cmd)
        print(out)
        if err:
            print(f"STDERR: {err}", file=sys.stderr)

    client.close()
