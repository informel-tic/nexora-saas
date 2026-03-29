"""Fix nexora namespace issue: create /tmp/nexora-export and add ExecStartPre."""
import paramiko
import os
import time
import sys

HOST = "192.168.1.125"
USER = "srv2rchon"
PASS = "Leila112//!!&"
BASE = os.path.dirname(os.path.abspath(__file__))


def run_sudo(ssh, cmd: str) -> str:
    chan = ssh.get_transport().open_session()
    chan.get_pty()
    chan.exec_command(f"sudo -S bash -c {repr(cmd)}")
    time.sleep(0.5)
    chan.sendall((PASS + "\n").encode())
    output = b""
    deadline = time.time() + 25
    while time.time() < deadline:
        if chan.exit_status_ready():
            break
        if chan.recv_ready():
            output += chan.recv(4096)
        else:
            time.sleep(0.1)
    output += chan.recv(65536)
    chan.close()
    # strip sudo password prompt lines
    lines = output.decode(errors="replace").split("\n")
    return "\n".join(l for l in lines if "Mot de passe" not in l and "[sudo]" not in l).strip()


def run(ssh, cmd: str) -> str:
    _, out, err = ssh.exec_command(cmd, timeout=15)
    return (out.read() + err.read()).decode(errors="replace").strip()


def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASS,
                allow_agent=False, look_for_keys=False,
                timeout=15, banner_timeout=15, auth_timeout=15)
    print("Connected!")

    # 1 — Create missing directories
    print("\n1. Creating missing directories...")
    print(run_sudo(ssh, "mkdir -p /tmp/nexora-export && chown nexora:nexora /tmp/nexora-export && chmod 755 /tmp/nexora-export") or "   OK /tmp/nexora-export")
    print(run_sudo(ssh, "mkdir -p /var/log/nexora && chown nexora:nexora /var/log/nexora && chmod 755 /var/log/nexora") or "   OK /var/log/nexora")

    # 2 — Add tmpfiles.d so /tmp/nexora-export persists across reboots
    print("\n2. Adding tmpfiles.d entry for /tmp/nexora-export...")
    tmpfiles_content = "d /tmp/nexora-export 0755 nexora nexora -"
    print(run_sudo(ssh, f"echo '{tmpfiles_content}' > /etc/tmpfiles.d/nexora.conf") or "   OK")

    # 3 — Add ExecStartPre to unit file (so it also works without tmpfiles-setup run)
    print("\n3. Adding ExecStartPre to nexora.service unit...")
    # Check if ExecStartPre already exists
    existing = run_sudo(ssh, "grep 'ExecStartPre' /etc/systemd/system/nexora.service || echo MISSING")
    if "MISSING" in existing:
        # Insert ExecStartPre before ExecStart
        print(run_sudo(ssh,
            "sed -i 's|ExecStart=/var/www/nexora/venv/bin/nexora-control-plane|"
            "ExecStartPre=+/bin/mkdir -p /tmp/nexora-export\\n"
            "ExecStartPre=+/bin/chown nexora:nexora /tmp/nexora-export\\n"
            "ExecStart=/var/www/nexora/venv/bin/nexora-control-plane|' "
            "/etc/systemd/system/nexora.service"
        ) or "   OK")
    else:
        print(f"   ExecStartPre already present: {existing}")

    # 4 — Reload daemon and start service
    print("\n4. Reloading systemd daemon...")
    print(run_sudo(ssh, "systemctl daemon-reload") or "   OK")

    print("\n5. Starting nexora.service...")
    print(run_sudo(ssh, "systemctl start nexora.service") or "   OK")
    time.sleep(5)

    status = run(ssh, "systemctl is-active nexora.service")
    print(f"   Status: {status}")
    if status != "active":
        print("   Waiting 10s more...")
        time.sleep(10)
        status = run(ssh, "systemctl is-active nexora.service")
        print(f"   Status after wait: {status}")

    if status != "active":
        print("   Journal:")
        print(run_sudo(ssh, "journalctl -u nexora.service -n 20 --no-pager"))
        ssh.close()
        return

    # 5 — Upload fixed api.js
    print("\n6. Uploading fixed api.js...")
    local_api = os.path.join(BASE, "apps", "console", "api.js")
    remote_tmp = f"/home/{USER}/api.js.tmp"
    remote_dest = "/var/www/nexora/repo/apps/console/api.js"
    sftp = ssh.open_sftp()
    sftp.put(local_api, remote_tmp)
    print(run_sudo(ssh, f"cp {remote_tmp} {remote_dest} && chown nexora:nexora {remote_dest}") or "   OK")
    run(ssh, f"rm -f {remote_tmp}")

    # 6 — Clear rate limit state
    print("\n7. Clearing auth-runtime rate limits...")
    print(run_sudo(ssh, "echo '{}' > /home/yunohost.app/nexora/auth-runtime.json && chown nexora:nexora /home/yunohost.app/nexora/auth-runtime.json") or "   OK")

    # 7 — Fix api-token-roles.json (write via temp file to avoid shell escaping)
    print("\n8. Fixing api-token-roles.json...")
    token = run_sudo(ssh, "cat /home/yunohost.app/nexora/api-token").strip()
    if token:
        import json
        roles_json = json.dumps({token: "operator"}, ensure_ascii=True)
        sftp.open(f"/home/{USER}/roles.json.tmp", "w").write(roles_json)
        print(run_sudo(ssh,
            f"cp /home/{USER}/roles.json.tmp /etc/nexora/api-token-roles.json && "
            f"chmod 600 /etc/nexora/api-token-roles.json && "
            f"chown root:root /etc/nexora/api-token-roles.json && "
            f"rm -f /home/{USER}/roles.json.tmp"
        ) or "   OK")
        print(f"   Token: {token[:20]}...")
    else:
        print("   WARNING: could not read token")

    # 8 — Validate
    print("\n9. Validation tests...")
    time.sleep(2)
    if token:
        r = run(ssh, f'curl -s -o /dev/null -w "%{{http_code}}" -H "X-Nexora-Token: {token}" http://127.0.0.1:38120/api/console/access-context')
        print(f"   Direct X-Nexora-Token:   HTTP {r}")
        r = run(ssh, f'curl -s -o /dev/null -w "%{{http_code}}" -H "Authorization: Bearer {token}" http://127.0.0.1:38120/api/console/access-context')
        print(f"   Direct Authorization:    HTTP {r}")
        r = run(ssh, f'curl -sk -o /dev/null -w "%{{http_code}}" -H "X-Nexora-Token: {token}" https://srv2testrchon.nohost.me/nexora/api/console/access-context')
        print(f"   Nginx X-Nexora-Token:    HTTP {r}")
        r = run(ssh, f'curl -sk -o /dev/null -w "%{{http_code}}" -H "Authorization: Bearer {token}" https://srv2testrchon.nohost.me/nexora/api/console/access-context')
        print(f"   Nginx Authorization:     HTTP {r}")

    sftp.close()
    ssh.close()

    print("\n" + "=" * 60)
    print("DONE")
    if token:
        print(f"\nBrowser console:")
        print(f"  URL:    https://srv2testrchon.nohost.me/nexora/console/")
        print(f"  Token:  {token}")
        print(f"  Tenant: nexora-operator")
        print(f"  Role:   operator")
    print("=" * 60)


if __name__ == "__main__":
    main()
