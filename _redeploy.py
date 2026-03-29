"""Quick redeploy of single file + restart."""
import paramiko
import os
import time
import base64

HOST = "192.168.1.125"
USER = "srv2rchon"
PASS = "Leila112//!!&"
REMOTE_REPO = "/var/www/nexora/repo"
LOCAL_ROOT = os.path.dirname(os.path.abspath(__file__))

FILES = [
    ("apps/control_plane/api.py", f"{REMOTE_REPO}/apps/control_plane/api.py"),
]


def new_client():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PASS,
              allow_agent=False, look_for_keys=False, timeout=20,
              banner_timeout=30, auth_timeout=30)
    t = c.get_transport()
    if t:
        t.set_keepalive(10)
    return c


def sudo_exec(client, cmd, password):
    # Use base64 to avoid shell escaping issues with password
    pw_b64 = base64.b64encode(password.encode()).decode()
    full_cmd = f"echo {pw_b64} | base64 -d | sudo -S bash -c {repr(cmd)} 2>&1"
    _, out, err = client.exec_command(full_cmd, timeout=30)
    result = out.read().decode().strip()
    return result


def main():
    print("Connecting...")
    client = new_client()
    print("SSH connected")

    staging = "/tmp/nexora-quick"
    sudo_exec(client, f"rm -rf {staging} && mkdir -p {staging} && chmod 777 {staging}", PASS)
    print("Staging dir ready")

    sftp = client.open_sftp()
    for local_rel, remote_path in FILES:
        local_path = os.path.join(LOCAL_ROOT, local_rel.replace("/", os.sep))
        safe_name = os.path.basename(local_rel)
        sftp.put(local_path, f"{staging}/{safe_name}")
        print(f"  Uploaded: {local_rel}")
    sftp.close()

    for local_rel, remote_path in FILES:
        safe_name = os.path.basename(local_rel)
        sudo_exec(client, f"cp {staging}/{safe_name} {remote_path} && chown nexora:nexora {remote_path}", PASS)
        print(f"  Deployed: {remote_path}")

    print("Restarting service...")
    sudo_exec(client, "systemctl restart nexora.service", PASS)
    time.sleep(4)

    o = sudo_exec(client, "systemctl is-active nexora.service", PASS)
    print(f"Status: {o}")

    client.close()
    time.sleep(1)

    # Reconnect for curl tests (avoid stale transport)
    print("Reconnecting for tests...")
    client = new_client()

    TOKEN = "9s2mGHS+YDuds1tG3b1o6TqS1uwMfRjMf642M0F0q/E="
    AUTH = f"-H 'Authorization: Bearer {TOKEN}' -H 'X-Nexora-Actor-Role: operator'"
    _, out, _ = client.exec_command(f"curl -sS {AUTH} http://127.0.0.1:38120/api/inventory/services 2>&1 | head -c 500", timeout=15)
    print(f"Services: {out.read().decode().strip()}")

    _, out, _ = client.exec_command(f"curl -sS {AUTH} http://127.0.0.1:38120/api/health 2>&1", timeout=10)
    print(f"Health: {out.read().decode().strip()}")

    o = sudo_exec(client, "journalctl -u nexora.service --no-pager -n 5", PASS)
    print(f"Journal:\n{o}")

    sudo_exec(client, f"rm -rf {staging}", PASS)
    client.close()
    print("Done!")


if __name__ == "__main__":
    main()
