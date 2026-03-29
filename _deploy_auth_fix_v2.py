"""
Deploy auth fix to server.
Run: python _deploy_auth_fix_v2.py

This script:
1. Uploads the fixed api.js (X-Nexora-Token header added)
2. Clears auth rate limit state
3. Fixes corrupted api-token-roles.json
4. Restarts nexora service
5. Validates the fix works
"""
import paramiko
import json
import os
import sys
import time

HOST = "192.168.1.125"
KEY = os.path.expanduser("~/.ssh/id_ed25519")
BASE = os.path.dirname(os.path.abspath(__file__))


def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    print(f"Connecting to {HOST}...")
    for attempt in range(3):
        try:
            ssh.connect(HOST, username="admin", key_filename=KEY,
                        timeout=15, banner_timeout=15, auth_timeout=15)
            print("  Connected!")
            break
        except Exception as e:
            print(f"  Attempt {attempt + 1} failed: {e}")
            if attempt == 2:
                print("\nServer unreachable. Try rebooting it first:")
                print("  - Physical access or YunoHost webadmin")
                print("  - Then re-run this script")
                sys.exit(1)
            time.sleep(3)

    def run(cmd: str) -> str:
        _, out, err = ssh.exec_command(cmd, timeout=30)
        return (out.read() + err.read()).decode(errors="replace").strip()

    sftp = ssh.open_sftp()

    # 1 — Upload fixed api.js
    local_api = os.path.join(BASE, "apps", "console", "api.js")
    remote_api = "/var/www/nexora/repo/apps/console/api.js"
    print(f"\n1. Uploading api.js -> {remote_api}")
    sftp.put(local_api, remote_api)
    print("   OK")

    # 2 — Clear auth-runtime.json (rate limits)
    print("\n2. Clearing auth-runtime state...")
    print(f"   {run('echo {} | sudo tee /home/yunohost.app/nexora/auth-runtime.json')}")

    # 3 — Fix api-token-roles.json
    print("\n3. Fixing api-token-roles.json...")
    token = run("cat /home/yunohost.app/nexora/api-token").strip()
    roles_data = {token: "operator"}
    roles_json = json.dumps(roles_data, indent=2)
    run(f"echo '{roles_json}' | sudo tee /etc/nexora/api-token-roles.json")
    run("sudo chmod 600 /etc/nexora/api-token-roles.json")
    print("   OK")

    # 4 — Restart nexora
    print("\n4. Restarting nexora.service...")
    run("sudo systemctl restart nexora.service")
    time.sleep(3)
    status = run("systemctl is-active nexora.service")
    print(f"   Status: {status}")
    if status != "active":
        print("   WARNING: Service is not active!")
        print(run("journalctl -u nexora.service --since '30 seconds ago' --no-pager"))

    # 5 — Validate
    print("\n5. Validation tests...")
    # Test via X-Nexora-Token (the fix)
    r = run(
        f'curl -s -w "\\nHTTP:%{{http_code}}" '
        f'-H "X-Nexora-Token: {token}" '
        f'http://127.0.0.1:38120/api/console/access-context'
    )
    print(f"   Direct X-Nexora-Token: {r.split(chr(10))[-1]}")

    # Test via Authorization Bearer
    r = run(
        f'curl -s -w "\\nHTTP:%{{http_code}}" '
        f'-H "Authorization: Bearer {token}" '
        f'http://127.0.0.1:38120/api/console/access-context'
    )
    print(f"   Direct Authorization: {r.split(chr(10))[-1]}")

    # Test through nginx with X-Nexora-Token
    r = run(
        f'curl -sk -w "\\nHTTP:%{{http_code}}" '
        f'-H "X-Nexora-Token: {token}" '
        f'https://srv2testrchon.nohost.me/nexora/api/console/access-context'
    )
    print(f"   Nginx X-Nexora-Token: {r.split(chr(10))[-1]}")

    sftp.close()
    ssh.close()

    print("\n" + "=" * 60)
    print("DONE. Test in browser:")
    print("  URL:    https://srv2testrchon.nohost.me/nexora/console/")
    print(f"  Token:  {token}")
    print("  Tenant: nexora-operator")
    print("  Role:   operator")
    print("=" * 60)


if __name__ == "__main__":
    main()
