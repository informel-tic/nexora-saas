"""Deep-dive: check yunohost SSO panel config and test header forwarding."""
import paramiko, os, json

HOST = "srv2testrchon.nohost.me"
KEY  = os.path.expanduser("~/.ssh/id_ed25519")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username="admin", key_filename=KEY, timeout=15)

def run(cmd: str) -> str:
    _, out, err = ssh.exec_command(cmd, timeout=30)
    return (out.read() + err.read()).decode(errors="replace").strip()

# 1 — Check yunohost_panel.conf.inc
print("=== YUNOHOST PANEL CONF ===")
print(run("cat /etc/nginx/conf.d/yunohost_panel.conf.inc"))
print()

# 2 — Check SSOwat config (is nexora protected?)
print("=== SSOWAT CONF (nexora entries) ===")
ssowat_raw = run("cat /etc/ssowat/conf.json")
try:
    ssowat = json.loads(ssowat_raw)
    # Check unprotected_urls or skipped_urls
    for key in ["unprotected_urls", "skipped_urls", "permissions"]:
        if key in ssowat:
            val = ssowat[key]
            if isinstance(val, dict):
                for k, v in val.items():
                    if "nexora" in k.lower() or (isinstance(v, dict) and any("nexora" in str(x).lower() for x in v.values())):
                        print(f"  {key}.{k}: {json.dumps(v, indent=2)}")
            elif isinstance(val, list):
                for item in val:
                    if "nexora" in str(item).lower():
                        print(f"  {key}: {item}")
except json.JSONDecodeError:
    print("  [Cannot parse ssowat conf]")
print()

# 3 — Check YunoHost permissions for nexora
print("=== YUNOHOST PERMISSION LIST ===")
print(run("yunohost user permission list --short 2>/dev/null | grep -i nexora || echo 'No nexora permissions found'"))
print()

# 4 — Full nginx nexora config
print("=== FULL NGINX NEXORA CONF ===")
print(run("cat /etc/nginx/conf.d/srv2testrchon.nohost.me.d/nexora.conf"))
print()

# 5 — Test: curl WITH a fake cookie (simulating browser SSO session)
TOKEN = run("cat /home/yunohost.app/nexora/api-token").strip()
print("=== TEST: curl WITH SSO Cookie through nginx ===")
cmd5 = (
    f'curl -sk -o /dev/null -w "%{{http_code}}" '
    f'-H "Authorization: Bearer {TOKEN}" '
    f'-H "Cookie: yunohost.portal=fakecookie123" '
    f'https://127.0.0.1/nexora/api/console/access-context '
    f'--resolve srv2testrchon.nohost.me:443:127.0.0.1 '
    f'-H "Host: srv2testrchon.nohost.me"'
)
print(f"  Status: {run(cmd5)}")
print()

# 6 — Test: curl WITHOUT cookie through nginx
print("=== TEST: curl WITHOUT Cookie through nginx ===")
cmd6 = (
    f'curl -sk -o /dev/null -w "%{{http_code}}" '
    f'-H "Authorization: Bearer {TOKEN}" '
    f'https://127.0.0.1/nexora/api/console/access-context '
    f'--resolve srv2testrchon.nohost.me:443:127.0.0.1 '
    f'-H "Host: srv2testrchon.nohost.me"'
)
print(f"  Status: {run(cmd6)}")
print()

# 7 — Test: curl directly to backend (bypassing nginx)
print("=== TEST: curl DIRECT to backend ===")
cmd7 = (
    f'curl -s -o /dev/null -w "%{{http_code}}" '
    f'-H "Authorization: Bearer {TOKEN}" '
    f'http://127.0.0.1:38120/api/console/access-context'
)
print(f"  Status: {run(cmd7)}")
print()

# 8 — Check if the Authorization header makes it through nginx
print("=== TEST: Add backend debug header logging ===")
# Instead, let's just grep the access log for recent 401s
print(run("journalctl -u nexora.service --since '5 minutes ago' --no-pager | tail -20"))
print()

# 9 — Check auth-runtime.json rate limit state
print("=== AUTH RUNTIME STATE ===")
print(run("cat /home/yunohost.app/nexora/auth-runtime.json 2>/dev/null || echo 'No auth-runtime.json'"))
print()

# 10 — Check if X-Nexora-Token header works (alternative to Authorization)
print("=== TEST: X-Nexora-Token through nginx ===")
cmd10 = (
    f'curl -sk -o /dev/null -w "%{{http_code}}" '
    f'-H "X-Nexora-Token: {TOKEN}" '
    f'https://127.0.0.1/nexora/api/console/access-context '
    f'--resolve srv2testrchon.nohost.me:443:127.0.0.1 '
    f'-H "Host: srv2testrchon.nohost.me"'
)
print(f"  Status: {run(cmd10)}")
print()

# 11 — Check if maybe the auth middleware checks a DIFFERENT header when behind proxy
print("=== MIDDLEWARE: How does it extract the token? ===")
print(run("grep -n 'authorization\\|x-nexora-token\\|bearer' /opt/nexora/src/nexora_node_sdk/auth/_middleware.py -i"))

ssh.close()
