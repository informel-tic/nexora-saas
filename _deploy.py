"""Deploy Nexora to test server via SFTP + SSH."""
import paramiko
import os
import sys
import stat

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

# Only sync these top-level dirs/files
SYNC_ITEMS = [
    "src", "apps", "blueprints", "pyproject.toml", "README.md",
]


def get_client():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        HOST, port=22, username=USER, password=PASS,
        timeout=15, auth_timeout=15, banner_timeout=15,
        allow_agent=False, look_for_keys=False,
    )
    return client


def sudo_exec(client, cmd, timeout=60):
    """Execute command with sudo, piping password via stdin."""
    # Use double-quotes around cmd to avoid single-quote nesting issues
    escaped_cmd = cmd.replace('"', '\\"')
    full_cmd = f'sudo -S bash -c "{escaped_cmd}"'
    stdin, stdout, stderr = client.exec_command(full_cmd, timeout=timeout)
    stdin.write(PASS + "\n")
    stdin.flush()
    stdin.channel.shutdown_write()
    out = stdout.read().decode()
    err = stderr.read().decode()
    # Filter sudo prompt lines
    lines = [l for l in out.split("\n")
             if not l.startswith("[sudo]") and "password" not in l.lower()[:30]]
    return "\n".join(lines).strip(), err.strip()


def upload_recursive(sftp, local_dir, remote_dir, count=0):
    """Upload directory recursively, skipping excluded dirs."""
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
            if count % 50 == 0:
                print(f"  ... {count} files uploaded")
    return count


def main():
    client = get_client()

    # Step 1: Stop services
    print("=== Stopping services ===")
    for svc in ["nexora.service", "nexora-node-agent.service"]:
        out, _ = sudo_exec(client, f"systemctl stop {svc} 2>&1 || true")
        print(f"  Stopped {svc}")

    # Step 2: Upload code via SFTP to staging dir
    print("\n=== Uploading code via SFTP ===")
    # Clean and create staging dir
    sudo_exec(client, f"rm -rf {STAGING} && mkdir -p {STAGING}")
    sudo_exec(client, f"chown {USER}:{USER} {STAGING}")

    sftp = client.open_sftp()

    for item in SYNC_ITEMS:
        local_path = os.path.join(REPO_LOCAL, item)
        remote_path = STAGING + "/" + item

        if os.path.isdir(local_path):
            print(f"  Uploading {item}/ ...")
            count = upload_recursive(sftp, local_path, remote_path)
            print(f"  {item}/: {count} files")
        elif os.path.isfile(local_path):
            print(f"  Uploading {item}")
            sftp.put(local_path, remote_path)

    sftp.close()
    print("  Upload complete.")

    # Step 2b: Copy from staging to repo
    print("\n=== Copying to repo ===")
    for item in SYNC_ITEMS:
        sudo_exec(client, f"rm -rf {REPO_REMOTE}/{item}")
        sudo_exec(client, f"cp -r {STAGING}/{item} {REPO_REMOTE}/{item}")
    sudo_exec(client, f"rm -rf {STAGING}")

    # Step 3: Fix ownership
    print("\n=== Fixing ownership ===")
    out, _ = sudo_exec(client, f"chown -R nexora:nexora {REPO_REMOTE}")
    print("  Done.")

    # Step 4: Install package in both venvs
    print("\n=== Installing package ===")
    for venv in ["/var/www/nexora/venv", "/opt/nexora/venv"]:
        print(f"  Installing in {venv} ...")
        out, err = sudo_exec(
            client,
            f"cd {REPO_REMOTE} && {venv}/bin/pip install -e . 2>&1 | tail -5",
            timeout=120,
        )
        print(f"    {out}")

    # Step 5: Verify entry points exist
    print("\n=== Verifying entry points ===")
    for venv in ["/var/www/nexora/venv", "/opt/nexora/venv"]:
        for ep in ["nexora-control-plane", "nexora-node-agent"]:
            out, _ = sudo_exec(client, f"ls -la {venv}/bin/{ep} 2>&1")
            print(f"  {venv}/bin/{ep}: {'OK' if 'No such file' not in out else 'MISSING!'}")

    # Step 6: Update service files for SaaS mode
    print("\n=== Updating service files for SaaS mode ===")

    nexora_service = """[Unit]
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

    node_agent_service = """[Unit]
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

    # Write service files
    for fname, content in [
        ("/etc/systemd/system/nexora.service", nexora_service),
        ("/etc/systemd/system/nexora-node-agent.service", node_agent_service),
    ]:
        escaped = content.replace("'", "'\\''")
        out, _ = sudo_exec(client, f"cat > {fname} << 'SERVICEEOF'\n{content}SERVICEEOF")
        print(f"  Written {fname}")

    # Step 7: Reload systemd and start services
    print("\n=== Reloading systemd and starting services ===")
    sudo_exec(client, "systemctl daemon-reload")
    print("  daemon-reload done")

    for svc in ["nexora.service", "nexora-node-agent.service"]:
        sudo_exec(client, f"systemctl start {svc}")
        import time
        time.sleep(2)
        out, _ = sudo_exec(client, f"systemctl is-active {svc}")
        status = out.strip().split("\n")[-1]
        print(f"  {svc}: {status}")

    # Step 8: Check logs
    print("\n=== Recent logs ===")
    for svc in ["nexora.service", "nexora-node-agent.service"]:
        out, _ = sudo_exec(client, f"journalctl -u {svc} --no-pager -n 10 2>&1")
        print(f"\n--- {svc} ---")
        print(out)

    # Step 9: Test HTTP endpoints
    print("\n=== Testing HTTP endpoints ===")
    for url in [
        "http://127.0.0.1:38120/",
        "http://127.0.0.1:38120/console/",
        "http://127.0.0.1:38120/api/health",
        "http://127.0.0.1:38121/health",
    ]:
        out, _ = sudo_exec(client, f"curl -s -o /dev/null -w '%{{http_code}}' {url} 2>&1 || echo FAIL")
        code = out.strip().split("\n")[-1]
        print(f"  {url} -> {code}")

    client.close()
    print("\n=== Deployment complete ===")


if __name__ == "__main__":
    main()
