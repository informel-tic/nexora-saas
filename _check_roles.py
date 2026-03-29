"""Check token-roles config in detail."""
import paramiko, json

HOST = "192.168.1.125"
USER = "srv2rchon"
PASS = "Leila112//!!&"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASS, allow_agent=False, look_for_keys=False, timeout=15)


def sudo_exec(client, cmd):
    full = f'sudo -S bash -c "{cmd}"'
    stdin, stdout, stderr = client.exec_command(full, timeout=30)
    stdin.write(PASS + "\n")
    stdin.flush()
    try:
        stdin.channel.shutdown_write()
    except Exception:
        pass
    return stdout.read().decode().strip(), stderr.read().decode().strip()


# 1. Check roles file raw content
print("=== /etc/nexora/api-token-roles.json (raw hex) ===")
out, _ = sudo_exec(client, "xxd /etc/nexora/api-token-roles.json 2>/dev/null | head -20")
lines = [l for l in out.split("\n") if not l.startswith("[sudo]")]
print("\n".join(lines))

print("\n=== /etc/nexora/api-token-roles.json (cat -A) ===")
out, _ = sudo_exec(client, "cat -A /etc/nexora/api-token-roles.json 2>/dev/null")
lines = [l for l in out.split("\n") if not l.startswith("[sudo]")]
print("\n".join(lines))

# 2. Check the primary API token 
print("\n=== API token (hexdump first 80 chars) ===")
out, _ = sudo_exec(client, "cat /home/yunohost.app/nexora/api-token | head -c 80 | xxd")
lines = [l for l in out.split("\n") if not l.startswith("[sudo]")]
print("\n".join(lines))

# 3. Python-level check: can we load the roles file?
print("\n=== Python check: load roles file ===")
out, _ = sudo_exec(client, """python3 -c '
import json, pathlib
path = pathlib.Path("/etc/nexora/api-token-roles.json")
if not path.exists():
    print("FILE MISSING")
else:
    raw = path.read_text()
    print("raw len:", len(raw))
    print("raw repr:", repr(raw[:300]))
    try:
        data = json.loads(raw)
        print("parsed:", json.dumps(data, indent=2)[:500])
    except Exception as e:
        print("JSON ERROR:", e)
'""")
lines = [l for l in out.split("\n") if not l.startswith("[sudo]")]
print("\n".join(lines))

# 4. Test: does the middleware resolve the role?
print("\n=== Python check: resolve_actor_role_for_token ===")
out, _ = sudo_exec(client, r"""python3 -c '
import sys; sys.path.insert(0, "/var/www/nexora/repo/src")
from nexora_node_sdk.auth._scopes import _load_token_actor_roles, resolve_actor_role_for_token
from nexora_node_sdk.auth._token import get_api_token

token = get_api_token()
print("API token (first 20):", repr(token[:20]))

roles = _load_token_actor_roles()
print("Role mapping count:", len(roles))
for k, v in roles.items():
    print(f"  key (first 20): {repr(k[:20])} -> role: {v}")

resolved = resolve_actor_role_for_token(token)
print("Resolved role for primary token:", resolved)
'""")
lines = [l for l in out.split("\n") if not l.startswith("[sudo]")]
print("\n".join(lines))

client.close()
print("\nDone.")
