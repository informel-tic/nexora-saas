"""Detailed smoke test - check all key endpoints with full HTTP info."""
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


TOKEN = "9s2mGHS+YDuds1tG3b1o6TqS1uwMfRjMf642M0F0q/E="
TENANT = "nexora-operator"
BASE = "http://127.0.0.1:38120"

tests = [
    ("GET /api/health (no auth)", f"curl -s -w '\\nHTTP:%{{http_code}}' {BASE}/api/health"),
    ("GET /api/console/access-context (with token)", f"curl -s -w '\\nHTTP:%{{http_code}}' -H 'Authorization: Bearer {TOKEN}' {BASE}/api/console/access-context"),
    ("GET /api/console/access-context (with token + tenant header)", f"curl -s -w '\\nHTTP:%{{http_code}}' -H 'Authorization: Bearer {TOKEN}' -H 'X-Nexora-Tenant-Id: {TENANT}' {BASE}/api/console/access-context"),
    ("POST /api/auth/tenant-claim (get claim)", f"curl -s -w '\\nHTTP:%{{http_code}}' -X POST -H 'Authorization: Bearer {TOKEN}' -H 'Content-Type: application/json' -d '{{\"tenant_id\": \"{TENANT}\"}}' {BASE}/api/auth/tenant-claim"),
    ("GET /api/v1/fleet/status (with token)", f"curl -s -w '\\nHTTP:%{{http_code}}' -H 'Authorization: Bearer {TOKEN}' {BASE}/api/v1/fleet/status"),
    ("GET console page", f"curl -s -w '\\nHTTP:%{{http_code}}' {BASE}/console/ | tail -3"),
    ("Service logs (last 5 lines)", "journalctl -u nexora.service --no-pager -n 5 --output=cat"),
]

for label, cmd in tests:
    print(f"\n=== {label} ===")
    out, err = sudo_exec(client, cmd)
    # Filter sudo prompt
    lines = [l for l in out.split("\n") if not l.startswith("[sudo]") and "password" not in l.lower()[:30]]
    print("\n".join(lines[-10:]))  # last 10 lines
    if err:
        err_lines = [l for l in err.split("\n") if not l.startswith("[sudo]") and "password" not in l.lower()[:30]]
        if err_lines:
            print("STDERR:", "\n".join(err_lines[:3]))

client.close()
print("\n\nDone.")
