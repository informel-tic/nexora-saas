"""Fix import error - deploy missing auth files + other deps."""
import paramiko
import os
import time

HOST = "192.168.1.125"
USER = "srv2rchon"
PASS = "Leila112//!!&"
REMOTE_REPO = "/var/www/nexora/repo"
LOCAL_ROOT = os.path.dirname(os.path.abspath(__file__))

# Deploy ALL src files to make sure everything is consistent
FILES_TO_DEPLOY = []

# Walk src/ and collect all .py files
for dirpath, dirnames, filenames in os.walk(os.path.join(LOCAL_ROOT, "src")):
    for fn in filenames:
        if fn.endswith(".py"):
            local_abs = os.path.join(dirpath, fn)
            rel = os.path.relpath(local_abs, LOCAL_ROOT).replace("\\", "/")
            remote = f"{REMOTE_REPO}/{rel}"
            FILES_TO_DEPLOY.append((rel, remote))

# Walk apps/ and collect all files
for dirpath, dirnames, filenames in os.walk(os.path.join(LOCAL_ROOT, "apps")):
    for fn in filenames:
        if fn.endswith((".py", ".js", ".html", ".css")):
            local_abs = os.path.join(dirpath, fn)
            rel = os.path.relpath(local_abs, LOCAL_ROOT).replace("\\", "/")
            remote = f"{REMOTE_REPO}/{rel}"
            FILES_TO_DEPLOY.append((rel, remote))

# Also deploy blueprints
for dirpath, dirnames, filenames in os.walk(os.path.join(LOCAL_ROOT, "blueprints")):
    for fn in filenames:
        if fn.endswith((".yaml", ".yml", ".json")):
            local_abs = os.path.join(dirpath, fn)
            rel = os.path.relpath(local_abs, LOCAL_ROOT).replace("\\", "/")
            remote = f"{REMOTE_REPO}/{rel}"
            FILES_TO_DEPLOY.append((rel, remote))

print(f"Total files to deploy: {len(FILES_TO_DEPLOY)}")


def sudo_exec(client, cmd, password):
    full_cmd = f"echo '{password}' | sudo -S bash -c '{cmd}' 2>&1"
    _, out, err = client.exec_command(full_cmd, timeout=30)
    return out.read().decode().strip(), err.read().decode().strip()


def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASS, allow_agent=False, look_for_keys=False, timeout=15)
    print("SSH connected")

    staging = "/tmp/nexora-deploy-full"
    sudo_exec(client, f"rm -rf {staging} && mkdir -p {staging} && chmod 777 {staging}", PASS)

    sftp = client.open_sftp()

    # Upload all files to flat staging
    uploaded = 0
    for local_rel, remote_path in FILES_TO_DEPLOY:
        local_path = os.path.join(LOCAL_ROOT, local_rel.replace("/", os.sep))
        if not os.path.exists(local_path):
            continue
        # Use a safe flat name for staging
        safe_name = local_rel.replace("/", "__")
        staging_file = f"{staging}/{safe_name}"
        try:
            sftp.put(local_path, staging_file)
            uploaded += 1
        except Exception as ex:
            print(f"  ERROR upload {local_rel}: {ex}")

    sftp.close()
    print(f"Uploaded {uploaded} files to staging")

    # Copy all files to repo with sudo
    ok_count = 0
    for local_rel, remote_path in FILES_TO_DEPLOY:
        local_path = os.path.join(LOCAL_ROOT, local_rel.replace("/", os.sep))
        if not os.path.exists(local_path):
            continue
        safe_name = local_rel.replace("/", "__")
        staging_file = f"{staging}/{safe_name}"
        remote_dir = os.path.dirname(remote_path)
        o, e = sudo_exec(client, f"mkdir -p {remote_dir} && cp {staging_file} {remote_path} && chown nexora:nexora {remote_path}", PASS)
        ok_count += 1

    print(f"Deployed {ok_count} files")

    # Restart service
    print("\nRestarting nexora.service...")
    sudo_exec(client, "systemctl restart nexora.service", PASS)
    time.sleep(5)

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
