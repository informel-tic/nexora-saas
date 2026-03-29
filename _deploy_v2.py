"""Deploy updated Nexora code to server via paramiko SFTP + restart service."""
import paramiko
import os
import time

HOST = "192.168.1.125"
USER = "srv2rchon"
PASS = "Leila112//!!&"
REMOTE_REPO = "/var/www/nexora/repo"
LOCAL_ROOT = os.path.dirname(os.path.abspath(__file__))

FILES_TO_DEPLOY = [
    ("src/nexora_node_sdk/yh_adapter.py",       f"{REMOTE_REPO}/src/nexora_node_sdk/yh_adapter.py"),
    ("src/nexora_node_sdk/auth/_scopes.py",      f"{REMOTE_REPO}/src/nexora_node_sdk/auth/_scopes.py"),
    ("src/nexora_saas/failover.py",              f"{REMOTE_REPO}/src/nexora_saas/failover.py"),
    ("src/nexora_saas/app_migration.py",         f"{REMOTE_REPO}/src/nexora_saas/app_migration.py"),
    ("src/nexora_node_sdk/docker.py",            f"{REMOTE_REPO}/src/nexora_node_sdk/docker.py"),
    ("apps/control_plane/api.py",                f"{REMOTE_REPO}/apps/control_plane/api.py"),
    ("apps/console/app.js",                      f"{REMOTE_REPO}/apps/console/app.js"),
    ("apps/console/views.js",                    f"{REMOTE_REPO}/apps/console/views.js"),
    ("apps/console/index.html",                  f"{REMOTE_REPO}/apps/console/index.html"),
]


def sudo_exec(client, cmd, password):
    full_cmd = f"echo '{password}' | sudo -S bash -c '{cmd}' 2>&1"
    _, out, err = client.exec_command(full_cmd, timeout=30)
    return out.read().decode().strip(), err.read().decode().strip()


def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASS, allow_agent=False, look_for_keys=False, timeout=15)
    print("SSH connected")

    o, _ = sudo_exec(client, f"wc -l {REMOTE_REPO}/apps/control_plane/api.py", PASS)
    print(f"Remote api.py lines: {o}")

    staging = "/tmp/nexora-deploy-staging"
    sudo_exec(client, f"rm -rf {staging} && mkdir -p {staging} && chmod 777 {staging}", PASS)

    sftp = client.open_sftp()

    for local_rel, remote_path in FILES_TO_DEPLOY:
        local_path = os.path.join(LOCAL_ROOT, local_rel.replace("/", os.sep))
        if not os.path.exists(local_path):
            print(f"  SKIP (not found): {local_rel}")
            continue

        staging_file = f"{staging}/{os.path.basename(local_rel)}"
        try:
            sftp.put(local_path, staging_file)
            size = os.path.getsize(local_path)
            print(f"  UPLOAD: {local_rel} ({size} bytes)")
        except Exception as ex:
            print(f"  ERROR: {local_rel}: {ex}")
            continue

    sftp.close()
    print("\nAll files staged. Deploying to repo with sudo...")

    for local_rel, remote_path in FILES_TO_DEPLOY:
        local_path = os.path.join(LOCAL_ROOT, local_rel.replace("/", os.sep))
        if not os.path.exists(local_path):
            continue
        staging_file = f"{staging}/{os.path.basename(local_rel)}"
        remote_dir = os.path.dirname(remote_path)
        o, e = sudo_exec(client, f"mkdir -p {remote_dir} && cp {staging_file} {remote_path} && chown nexora:nexora {remote_path} && chmod 644 {remote_path}", PASS)
        err_text = (o + " " + e).strip()
        if err_text and "password" not in err_text.lower():
            print(f"  DEPLOY {local_rel}: {err_text}")
        else:
            print(f"  OK: {remote_path}")

    print("\n=== Verification ===")
    for local_rel, remote_path in FILES_TO_DEPLOY:
        local_path = os.path.join(LOCAL_ROOT, local_rel.replace("/", os.sep))
        if not os.path.exists(local_path):
            continue
        o, _ = sudo_exec(client, f"wc -l {remote_path}", PASS)
        with open(local_path, "r", encoding="utf-8") as f:
            local_lines = len(f.readlines())
        remote_lines = o.split()[0] if o and o.split() else "?"
        match = "OK" if str(local_lines) == remote_lines else "MISMATCH"
        print(f"  {match}: {local_rel} local={local_lines} remote={remote_lines}")

    print("\n=== Restarting nexora.service ===")
    o, _ = sudo_exec(client, "systemctl restart nexora.service", PASS)
    time.sleep(4)
    o, _ = sudo_exec(client, "systemctl is-active nexora.service", PASS)
    print(f"Status: {o}")
    o, _ = sudo_exec(client, "journalctl -u nexora.service --no-pager -n 20", PASS)
    print(f"=== Journal ===\n{o}")
    o, _ = sudo_exec(client, "ss -tlnp | grep 38120", PASS)
    print(f"\nPort 38120: {o or 'NOT LISTENING'}")

    sudo_exec(client, f"rm -rf {staging}", PASS)
    client.close()
    print("\nDeploy complete!")


if __name__ == "__main__":
    main()
