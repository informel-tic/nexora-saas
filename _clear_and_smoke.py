"""Clear rate-limit state + smoke test with real token."""
import paramiko

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


print("--- Clearing auth-runtime state ---")
out, _ = sudo_exec(client, "rm -f /home/yunohost.app/nexora/auth-runtime.json /opt/nexora/var/auth-runtime.json; echo CLEARED")
print(out)

print("--- API token ---")
out, _ = sudo_exec(client, "cat /home/yunohost.app/nexora/api-token")
lines = [l for l in out.split("\n") if not l.startswith("[sudo]") and "password" not in l.lower()[:30]]
token = lines[-1].strip() if lines else "EMPTY"
print(f"Token: {token}")

print("--- Token roles config ---")
out, _ = sudo_exec(client, "cat /etc/nexora/api-token-roles.json 2>/dev/null || echo MISSING")
lines2 = [l for l in out.split("\n") if not l.startswith("[sudo]") and "password" not in l.lower()[:30]]
print("\n".join(lines2))

print("--- Smoke test: access-context with token ---")
out, _ = sudo_exec(client, f'curl -s -H "Authorization: Bearer {token}" http://127.0.0.1:38120/api/console/access-context 2>/dev/null | head -c 500')
lines3 = [l for l in out.split("\n") if not l.startswith("[sudo]") and "password" not in l.lower()[:30]]
print("\n".join(lines3))

print("--- Smoke test: access-context WITHOUT token (should 401, NOT 429) ---")
out, _ = sudo_exec(client, "curl -s -w '\\nHTTP_CODE=%{http_code}' http://127.0.0.1:38120/api/console/access-context 2>/dev/null | tail -5")
lines4 = [l for l in out.split("\n") if not l.startswith("[sudo]") and "password" not in l.lower()[:30]]
print("\n".join(lines4))

client.close()
print("\nDone.")
