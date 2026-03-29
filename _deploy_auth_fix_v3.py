"""Deploy auth fix: connects as srv2rchon, uses sudo with password."""
import paramiko
import json
import os
import sys
import time

HOST = "192.168.1.125"
USER = "srv2rchon"
PASS = "Leila112//!!&"
BASE = os.path.dirname(os.path.abspath(__file__))


def run_sudo(ssh, cmd: str, password: str = PASS) -> str:
    """Run a command with sudo, feeding the password via stdin."""
    chan = ssh.get_transport().open_session()
    chan.get_pty()
    chan.exec_command(f"sudo -S sh -c '{cmd}'")
    time.sleep(0.5)
    # Feed password
    chan.sendall((password + "\n").encode())
    output = b""
    while True:
        if chan.exit_status_ready():
            break
        if chan.recv_ready():
            output += chan.recv(4096)
    output += chan.recv(65536)
    chan.close()
    return output.decode(errors="replace").strip()


def run(ssh, cmd: str) -> str:
    _, out, err = ssh.exec_command(cmd, timeout=20)
    return (out.read() + err.read()).decode(errors="replace").strip()


def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    print(f"Connecting to {HOST} as {USER}...")
    for attempt in range(3):
        try:
            ssh.connect(
                HOST, username=USER, password=PASS,
                allow_agent=False, look_for_keys=False,
                timeout=15, banner_timeout=15, auth_timeout=15
            )
            print("  Connected!")
            break
        except Exception as e:
            print(f"  Attempt {attempt + 1} failed: {e}")
            if attempt == 2:
                sys.exit(1)
            time.sleep(3)

    sftp = ssh.open_sftp()

    # 1 — Upload fixed api.js
    local_api = os.path.join(BASE, "apps", "console", "api.js")
    remote_tmp = f"/home/{USER}/api.js.tmp"
    remote_dest = "/var/www/nexora/repo/apps/console/api.js"
    print(f"\n1. Uploading api.js...")
    sftp.put(local_api, remote_tmp)
    result = run_sudo(ssh, f"cp {remote_tmp} {remote_dest} && chown nexora:nexora {remote_dest}")
    print(f"   {result or 'OK'}")

    # 2 — Clear auth-runtime.json (rate limits)
    print("\n2. Clearing auth-runtime rate limit state...")
    result = run_sudo(ssh, "echo '{}' > /home/yunohost.app/nexora/auth-runtime.json && chown nexora:nexora /home/yunohost.app/nexora/auth-runtime.json")
    print(f"   {result or 'OK'}")

    # 3 — Get current token and fix api-token-roles.json
    print("\n3. Reading active token...")
    token = run_sudo(ssh, "cat /home/yunohost.app/nexora/api-token 2>/dev/null || cat /opt/nexora/var/api-token 2>/dev/null").strip()
    # strip sudo password prompt from output
    token = token.split("\n")[-1].strip()
    print(f"   Token: {token[:20]}..." if token else "   WARNING: could not read token")

    if token:
        roles_json = json.dumps({token: "operator"})
        print("4. Fixing api-token-roles.json...")
        # Write via python3 on remote to avoid shell escaping issues with the token
        py_cmd = (
            f"python3 -c \""
            f"import json; "
            f"d = json.loads(open('/home/{USER}/roles.json.tmp').read()); "
            f"open('/etc/nexora/api-token-roles.json', 'w').write(json.dumps(d)); "
            f"import os; os.chmod('/etc/nexora/api-token-roles.json', 0o600)"
            f"\""
        )
        # First write JSON to a temp file as the user, then sudo-process it
        sftp.open(f"/home/{USER}/roles.json.tmp", "w").write(roles_json)
        result = run_sudo(ssh, py_cmd)
        run(ssh, f"rm -f /home/{USER}/roles.json.tmp")
        print(f"   {result or 'OK'}")
    else:
        print("4. Skipping api-token-roles fix (no token found)")

    # 5 — Restart nexora
    print("\n5. Restarting nexora.service...")
    result = run_sudo(ssh, "systemctl restart nexora.service")
    print(f"   {result or 'OK'}")
    time.sleep(5)

    status = run(ssh, "systemctl is-active nexora.service")
    print(f"   Status: {status}")
    if status != "active":
        print("   WARNING: Service not active! Waiting 10s more...")
        time.sleep(10)
        status = run(ssh, "systemctl is-active nexora.service")
        print(f"   Status after wait: {status}")
    if status != "active":
        logs = run_sudo(ssh, "journalctl -u nexora.service -n 15 --no-pager")
        print(logs)

    # 6 — Validate
    print("\n6. Validation...")
    # Check what port nexora is actually listening on
    ports = run(ssh, "ss -tlnp 2>/dev/null | grep nexora || ss -tlnp 2>/dev/null | grep '3812'")
    print(f"   Listening ports: {ports or '(none - service may still be starting)'}")
    time.sleep(3)

    if token:
        r = run(ssh, f'curl -s -o /dev/null -w "%{{http_code}}" -H "X-Nexora-Token: {token}" http://127.0.0.1:38120/api/console/access-context')
        print(f"   Direct X-Nexora-Token:    HTTP {r}")
        r = run(ssh, f'curl -s -o /dev/null -w "%{{http_code}}" -H "Authorization: Bearer {token}" http://127.0.0.1:38120/api/console/access-context')
        print(f"   Direct Authorization:     HTTP {r}")
        r = run(ssh, f'curl -sk -o /dev/null -w "%{{http_code}}" -H "X-Nexora-Token: {token}" https://srv2testrchon.nohost.me/nexora/api/console/access-context')
        print(f"   Nginx X-Nexora-Token:     HTTP {r}")
        r = run(ssh, f'curl -sk -o /dev/null -w "%{{http_code}}" -H "Authorization: Bearer {token}" https://srv2testrchon.nohost.me/nexora/api/console/access-context')
        print(f"   Nginx Authorization:      HTTP {r}")

    # Cleanup temp file
    run(ssh, f"rm -f {remote_tmp}")
    sftp.close()
    ssh.close()

    print("\n" + "=" * 60)
    print("DONE")
    if token:
        print(f"\nBrowser test:")
        print(f"  URL:    https://srv2testrchon.nohost.me/nexora/console/")
        print(f"  Token:  {token}")
        print(f"  Tenant: nexora-operator")
        print(f"  Role:   operator")
    print("=" * 60)


if __name__ == "__main__":
    main()
