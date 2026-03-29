"""Focused: check SSO header stripping and test browser-like request."""
import paramiko, os

HOST = "srv2testrchon.nohost.me"
KEY  = os.path.expanduser("~/.ssh/id_ed25519")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username="admin", key_filename=KEY, timeout=15)

def run(cmd: str) -> str:
    _, out, err = ssh.exec_command(cmd, timeout=20)
    return (out.read() + err.read()).decode(errors="replace").strip()

TOKEN = run("cat /home/yunohost.app/nexora/api-token").strip()
print(f"TOKEN={TOKEN!r}")
print()

# 1 — SSO panel config
print("=== YUNOHOST PANEL CONF ===")
print(run("cat /etc/nginx/conf.d/yunohost_panel.conf.inc 2>/dev/null || echo MISSING"))
print()

# 2 — SSOwat permissions for nexora
print("=== SSOWAT PERMISSIONS ===")
print(run("python3 -c \"import json; d=json.load(open('/etc/ssowat/conf.json')); [print(k,v.get('uris',[])) for k,v in d.get('permissions',{}).items() if 'nexora' in k.lower()]\" 2>&1"))
print()

# 3 — Test through nginx WITH Authorization header
print("=== CURL THROUGH NGINX: Authorization Bearer ===")
r = run(f'curl -sk -w "\\n%{{http_code}}" -H "Authorization: Bearer {TOKEN}" https://srv2testrchon.nohost.me/nexora/api/console/access-context 2>&1')
print(r)
print()

# 4 — Test through nginx with X-Nexora-Token
print("=== CURL THROUGH NGINX: X-Nexora-Token ===")
r = run(f'curl -sk -w "\\n%{{http_code}}" -H "X-Nexora-Token: {TOKEN}" https://srv2testrchon.nohost.me/nexora/api/console/access-context 2>&1')
print(r)
print()

# 5 — Direct to backend
print("=== CURL DIRECT BACKEND: Authorization Bearer ===")
r = run(f'curl -s -w "\\n%{{http_code}}" -H "Authorization: Bearer {TOKEN}" http://127.0.0.1:38120/api/console/access-context 2>&1')
print(r)
print()

# 6 — Dump the ACTUAL headers that arrive at the backend
# Add a tiny temp middleware to log headers
print("=== CHECKING NGINX HEADER FORWARDING ===")
# Use nc to see what nginx sends
r = run("""timeout 3 bash -c '
  # Start a listener, send the request, capture headers
  { echo -e "HTTP/1.1 200 OK\\r\\nContent-Length: 2\\r\\n\\r\\nOK" | nc -l 38199 > /tmp/nexora_header_test.txt 2>&1; } &
  NCPID=$!
  sleep 0.5
  # Temporarily nothing - just test curl verbose through nginx
  curl -sk -D /tmp/nexora_resp_headers.txt -H "Authorization: Bearer TESTTOKEN123" https://srv2testrchon.nohost.me/nexora/api/v1/health -o /dev/null 2>&1
  kill $NCPID 2>/dev/null
  echo "--- Response headers ---"
  cat /tmp/nexora_resp_headers.txt 2>/dev/null
' 2>&1""")
print(r)
print()

# 7 — Check if nexora app is registered as "unprotected" in YunoHost
print("=== YUNOHOST APP SETTINGS ===")
print(run("cat /etc/yunohost/apps/nexora/settings.yml 2>/dev/null | head -30 || echo 'No app settings'"))
print()

# 8 — Clear the auth runtime to reset rate limits
print("=== AUTH RUNTIME BEFORE CLEAR ===")
print(run("cat /home/yunohost.app/nexora/auth-runtime.json 2>/dev/null"))
print()

# 9 — Check if there's something in yunohost SSO intercepting
print("=== NGINX FULL NEXORA CONF ===")
print(run("cat /etc/nginx/conf.d/srv2testrchon.nohost.me.d/nexora.conf 2>/dev/null || echo MISSING"))

ssh.close()
