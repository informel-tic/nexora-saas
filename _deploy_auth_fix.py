"""Deploy console fix: X-Nexora-Token header + clear rate limit state."""
import paramiko, os, sys, time

HOST = "192.168.1.125"
KEY  = os.path.expanduser("~/.ssh/id_ed25519")
BASE = os.path.dirname(os.path.abspath(__file__))

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

# Retry connection
for attempt in range(3):
    try:
        ssh.connect(HOST, username="admin", key_filename=KEY, timeout=30)
        print(f"SSH connected (attempt {attempt+1})")
        break
    except Exception as e:
        print(f"SSH attempt {attempt+1} failed: {e}")
        if attempt == 2:
            sys.exit(1)
        time.sleep(5)

def run(cmd: str) -> str:
    _, out, err = ssh.exec_command(cmd, timeout=30)
    return (out.read() + err.read()).decode(errors="replace").strip()

sftp = ssh.open_sftp()

# 1 — Deploy updated api.js
local_api = os.path.join(BASE, "apps", "console", "api.js")
remote_repo = "/var/www/nexora/repo/apps/console/api.js"
print(f"Uploading {local_api} -> {remote_repo}")
sftp.put(local_api, remote_repo)
print("  OK")

# 2 — Clear auth-runtime.json (rate limit state)
print("\nClearing auth-runtime.json...")
print(run('echo "{}" | sudo tee /home/yunohost.app/nexora/auth-runtime.json'))

# 3 — Check current yunohost_panel.conf.inc (for diagnostic)
print("\n=== YUNOHOST PANEL CONF ===")
panel_conf = run("cat /etc/nginx/conf.d/yunohost_panel.conf.inc 2>/dev/null || echo MISSING")
print(panel_conf[:2000])

# 4 — Restart nexora to clear cached state
print("\nRestarting nexora.service...")
print(run("sudo systemctl restart nexora.service"))
time.sleep(2)

# 5 — Verify service is up
print("\nService status:")
print(run("systemctl is-active nexora.service"))

# 6 — Quick test: direct to backend
TOKEN = run("cat /home/yunohost.app/nexora/api-token").strip()
print(f"\nToken: {TOKEN[:20]}...")
r = run(f'curl -s -w "\\nHTTP:%{{http_code}}" -H "X-Nexora-Token: {TOKEN}" http://127.0.0.1:38120/api/console/access-context 2>&1')
print(f"Direct test (X-Nexora-Token): {r}")

# 7 — Test through nginx
r = run(f'curl -sk -w "\\nHTTP:%{{http_code}}" -H "X-Nexora-Token: {TOKEN}" https://srv2testrchon.nohost.me/nexora/api/console/access-context 2>&1')
print(f"Nginx test (X-Nexora-Token): {r}")

sftp.close()
ssh.close()
print("\nDONE")
