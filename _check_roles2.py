"""Check token-roles on server using simple commands."""
import paramiko, base64

HOST = "192.168.1.125"
USER = "srv2rchon"
PASS = "Leila112//!!&"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASS, allow_agent=False, look_for_keys=False, timeout=15)


def sudo_exec(client, cmd):
    full = f"sudo -S bash -c '{cmd}'"
    stdin, stdout, stderr = client.exec_command(full, timeout=30)
    stdin.write(PASS + "\n")
    stdin.flush()
    try:
        stdin.channel.shutdown_write()
    except Exception:
        pass
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    # Filter out sudo prompt lines
    out_lines = [l for l in out.split("\n") if not l.startswith("[sudo]") and "password" not in l.lower()[:30]]
    return "\n".join(out_lines), err


# 1. Read roles file as base64 to avoid escaping issues
print("=== Roles file (base64) ===")
out, _ = sudo_exec(client, "base64 /etc/nexora/api-token-roles.json 2>/dev/null || echo MISSING")
print("raw output:", repr(out))
if out and out != "MISSING":
    try:
        decoded = base64.b64decode(out).decode("utf-8", errors="replace")
        print("Decoded content:", repr(decoded))
    except Exception as e:
        print("Decode error:", e)

# 2. Read API token as base64
print("\n=== API token (base64) ===")
out, _ = sudo_exec(client, "base64 /home/yunohost.app/nexora/api-token 2>/dev/null || echo MISSING")
if out and out != "MISSING":
    try:
        decoded = base64.b64decode(out).decode("utf-8", errors="replace")
        print("Token:", repr(decoded.strip()))
    except Exception as e:
        print("Decode error:", e)

# 3. File sizes/perms
print("\n=== File details ===")
out, _ = sudo_exec(client, "ls -la /etc/nexora/api-token-roles.json /home/yunohost.app/nexora/api-token 2>&1")
print(out)

# 4. Quick python role resolve test (script uploaded to /tmp)
script = '''
import sys, json, pathlib
sys.path.insert(0, "/var/www/nexora/repo/src")
try:
    from nexora_node_sdk.auth._scopes import _load_token_actor_roles, resolve_actor_role_for_token
    from nexora_node_sdk.auth._token import get_api_token
    token = get_api_token()
    print("TOKEN_START:" + repr(token[:30]) + ":TOKEN_END")
    roles = _load_token_actor_roles()
    print("ROLES_COUNT:" + str(len(roles)))
    for k, v in roles.items():
        print("ROLE_ENTRY:" + repr(k[:30]) + " -> " + v)
    resolved = resolve_actor_role_for_token(token)
    print("RESOLVED:" + str(resolved))
except Exception as e:
    print("ERROR:" + str(e))
'''

# Write script to /tmp
sftp = client.open_sftp()
with sftp.file("/tmp/_check_roles.py", "w") as f:
    f.write(script)
sftp.close()

print("\n=== Python resolve test ===")
out, _ = sudo_exec(client, "python3 /tmp/_check_roles.py")
print(out)

client.close()
print("\nDone.")
