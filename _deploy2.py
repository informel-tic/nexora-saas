"""Deploy Nexora to test server - single session, minimal connections."""
import paramiko
import os
import sys
import time

HOST = "192.168.1.125"
USER = "srv2rchon"
PASS = "Leila112//!!&"
REPO_LOCAL = os.path.dirname(os.path.abspath(__file__))
REPO_REMOTE = "/var/www/nexora/repo"
STAGING = "/tmp/nexora-deploy"

SKIP_DIRS = {
    "__pycache__", ".git", ".venv", ".venvaudit", "node_modules",
    "_ext", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".vscode",
}

SYNC_ITEMS = ["src", "apps", "blueprints", "pyproject.toml", "README.md"]


def get_client():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        HOST, port=22, username=USER, password=PASS,
        timeout=20, auth_timeout=20, banner_timeout=20,
        allow_agent=False, look_for_keys=False,
    )
    return client


def sudo_exec(client, cmd, timeout=120):
    """Execute command with sudo via stdin password."""
    escaped_cmd = cmd.replace('"', '\\"')
    full_cmd = f'sudo -S bash -c "{escaped_cmd}"'
    stdin, stdout, stderr = client.exec_command(full_cmd, timeout=timeout)
    stdin.write(PASS + "\n")
    stdin.flush()
    try:
        stdin.channel.shutdown_write()
    except Exception:
        pass
    out = stdout.read().decode()
    err = stderr.read().decode()
    lines = [l for l in out.split("\n")
             if not l.startswith("[sudo]") and "password" not in l.lower()[:30]]
    return "\n".join(lines).strip(), err.strip()


def run(client, cmd, timeout=30):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    return stdout.read().decode().strip(), stderr.read().decode().strip()


def upload_recursive(sftp, local_dir, remote_dir, count=0):
    try:
        sftp.stat(remote_dir)
    except FileNotFoundError:
        sftp.mkdir(remote_dir)
    for item in sorted(os.listdir(local_dir)):
        if item in SKIP_DIRS:
            continue
        local_path = os.path.join(local_dir, item)
        remote_path = remote_dir + "/" + item
        if os.path.isdir(local_path):
            count = upload_recursive(sftp, local_path, remote_path, count)
        elif os.path.isfile(local_path):
            sftp.put(local_path, remote_path)
            count += 1
            if count % 100 == 0:
                print(f"    ... {count} files uploaded")
    return count


def main():
    step = sys.argv[1] if len(sys.argv) > 1 else "full"

    print(f"Connecting to {HOST}...")
    client = get_client()
    print("Connected!")

    # Always do everything in one session to avoid fail2ban
    # Step 1: Stop services
    print("\n[1/8] Stopping services...")
    sudo_exec(client, "systemctl stop nexora.service nexora-node-agent.service 2>/dev/null || true")
    print("  Done.")

    # Step 2: Upload code
    print("\n[2/8] Uploading code via SFTP...")
    sudo_exec(client, f"rm -rf {STAGING} && mkdir -p {STAGING} && chown {USER}:{USER} {STAGING}")
    sftp = client.open_sftp()
    total = 0
    for item in SYNC_ITEMS:
        local_path = os.path.join(REPO_LOCAL, item)
        remote_path = STAGING + "/" + item
        if os.path.isdir(local_path):
            print(f"  {item}/ ...")
            total = upload_recursive(sftp, local_path, remote_path, total)
        elif os.path.isfile(local_path):
            sftp.put(local_path, remote_path)
            total += 1
    sftp.close()
    print(f"  Uploaded {total} files.")

    # Step 3: Copy to repo
    print("\n[3/8] Copying to deployment directory...")
    for item in SYNC_ITEMS:
        sudo_exec(client, f"rm -rf {REPO_REMOTE}/{item} && cp -r {STAGING}/{item} {REPO_REMOTE}/{item}")
    sudo_exec(client, f"chown -R nexora:nexora {REPO_REMOTE} && rm -rf {STAGING}")
    print("  Done.")

    # Step 4: Install package
    print("\n[4/8] Installing package in venvs...")
    for venv in ["/var/www/nexora/venv", "/opt/nexora/venv"]:
        print(f"  {venv}...")
        out, err = sudo_exec(client,
            f"cd {REPO_REMOTE} && {venv}/bin/pip install -e . 2>&1 | tail -8",
            timeout=180)
        print(f"    {out}")

    # Step 5: Verify entry points
    print("\n[5/8] Verifying entry points...")
    for venv in ["/var/www/nexora/venv", "/opt/nexora/venv"]:
        for ep in ["nexora-control-plane", "nexora-node-agent"]:
            out, _ = sudo_exec(client, f"test -f {venv}/bin/{ep} && echo OK || echo MISSING")
            status = "OK" if "OK" in out else "MISSING"
            print(f"  {venv}/bin/{ep}: {status}")

    # Step 6: Write service files for SaaS mode
    print("\n[6/8] Writing systemd service files (SaaS mode)...")

    nexora_svc = """[Unit]
Description=Nexora Control Plane (YunoHost)
After=network.target

[Service]
Type=simple
User=nexora
Group=nexora
WorkingDirectory=/var/www/nexora/repo
Environment=PYTHONPATH=/var/www/nexora/repo/src:/var/www/nexora/repo/apps
Environment=NEXORA_CONTROL_PLANE_HOST=127.0.0.1
Environment=NEXORA_CONTROL_PLANE_PORT=38120
Environment=NEXORA_STATE_PATH=/home/yunohost.app/nexora/state.json
Environment=NEXORA_API_TOKEN_FILE=/home/yunohost.app/nexora/api-token
Environment=NEXORA_API_TOKEN_ROLE_FILE=/etc/nexora/api-token-roles.json
Environment=NEXORA_REPO_ROOT=/var/www/nexora/repo
ExecStart=/var/www/nexora/venv/bin/nexora-control-plane
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/home/yunohost.app/nexora /var/log/nexora /tmp/nexora-export
ProtectHome=no

[Install]
WantedBy=multi-user.target
"""

    node_svc = """[Unit]
Description=Nexora Node Agent
After=network.target

[Service]
Type=simple
User=nexora
Group=nexora
WorkingDirectory=/var/www/nexora/repo
Environment=PYTHONPATH=/var/www/nexora/repo/src:/var/www/nexora/repo/apps
Environment=NEXORA_NODE_AGENT_HOST=127.0.0.1
Environment=NEXORA_NODE_AGENT_PORT=38121
Environment=NEXORA_STATE_PATH=/opt/nexora/var/state.json
Environment=NEXORA_API_TOKEN_FILE=/opt/nexora/var/api-token
ExecStart=/opt/nexora/venv/bin/nexora-node-agent
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/opt/nexora/var /var/lib/nexora /tmp/nexora-export
ProtectHome=true

[Install]
WantedBy=multi-user.target
"""

    sftp = client.open_sftp()
    for fname, content in [
        ("nexora.service", nexora_svc),
        ("nexora-node-agent.service", node_svc),
    ]:
        tmp_path = f"/tmp/{fname}"
        with sftp.open(tmp_path, "w") as f:
            f.write(content)
        sudo_exec(client, f"mv {tmp_path} /etc/systemd/system/{fname} && chmod 644 /etc/systemd/system/{fname}")
        print(f"  Written /etc/systemd/system/{fname}")
    sftp.close()

    sudo_exec(client, "mkdir -p /var/lib/nexora && chown nexora:nexora /var/lib/nexora")
    sudo_exec(client, "mkdir -p /var/log/nexora && chown nexora:nexora /var/log/nexora")
    sudo_exec(client, "mkdir -p /tmp/nexora-export && chown nexora:nexora /tmp/nexora-export")
    sudo_exec(client, "test -f /home/yunohost.app/nexora/api-token || (head -c 32 /dev/urandom | base64 > /home/yunohost.app/nexora/api-token && chmod 600 /home/yunohost.app/nexora/api-token && chown nexora:nexora /home/yunohost.app/nexora/api-token)")
    sudo_exec(client, "test -f /opt/nexora/var/api-token || (head -c 32 /dev/urandom | base64 > /opt/nexora/var/api-token && chmod 600 /opt/nexora/var/api-token && chown nexora:nexora /opt/nexora/var/api-token)")
    sudo_exec(client, "mkdir -p /etc/nexora")
    sudo_exec(
        client,
        "token=$(cat /home/yunohost.app/nexora/api-token); "
        "printf '{\\\"tokens\\\":[{\\\"token\\\":\\\"%s\\\",\\\"actor_role\\\":\\\"admin\\\"}]}\\n' \"$token\" > /etc/nexora/api-token-roles.json && "
        "chmod 644 /etc/nexora/api-token-roles.json",
    )

    # Step 7: Restart services
    print("\n[7/8] Restarting services...")
    sudo_exec(client, "systemctl daemon-reload")
    for svc in ["nexora.service", "nexora-node-agent.service"]:
        sudo_exec(client, f"systemctl restart {svc}")
        time.sleep(3)
        out, _ = sudo_exec(client, f"systemctl is-active {svc}")
        status = out.strip().split("\\n")[-1]
        print(f"  {svc}: {status}")

    # Step 8: Wait and test
    print("\n[8/8] Waiting for startup, then testing endpoints...")
    time.sleep(45)  # Control plane takes ~40s to start
    endpoints = [
        ("http://127.0.0.1:38120/", "Control Plane root"),
        ("http://127.0.0.1:38120/console/", "Console"),
        ("http://127.0.0.1:38120/api/health", "API Health"),
        ("http://127.0.0.1:38121/health", "Node Agent Health"),
    ]
    for url, label in endpoints:
        out, _ = sudo_exec(client, f"curl -s -o /dev/null -w '%{{http_code}}' {url} 2>/dev/null || echo FAIL")
        code = out.strip().split("\\n")[-1]
        print(f"  {label}: {code}")

    # Check console access-context (SaaS mode should return all sections)
    print("\n  Testing SaaS mode (access-context)...")
    out, _ = sudo_exec(client, "curl -s http://127.0.0.1:38120/api/console/access-context 2>/dev/null | head -5")
    print(f"  access-context: {out[:200]}")

    # Logs
    print("\n--- Control Plane logs (last 15) ---")
    out, _ = sudo_exec(client, "journalctl -u nexora.service --no-pager -n 15 2>&1")
    print(out)

    print("\n--- Node Agent logs (last 10) ---")
    out, _ = sudo_exec(client, "journalctl -u nexora-node-agent.service --no-pager -n 10 2>&1")
    print(out)

    client.close()
    print("\n=== Deployment complete ===")


if __name__ == "__main__":
    main()
