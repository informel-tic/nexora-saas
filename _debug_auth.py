"""Simulate exact browser console auth flow and check nginx config."""
import paramiko
import json

HOST = "192.168.1.125"
USER = "srv2rchon"
PASS = "Leila112//!!&"
TOKEN = "9s2mGHS+YDuds1tG3b1o6TqS1uwMfRjMf642M0F0q/E="


def get_client():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASS,
                   allow_agent=False, look_for_keys=False, timeout=20)
    return client


def sudo_run(client, cmd, timeout=30):
    full = f"sudo -S sh -c '{cmd}'"
    stdin, stdout, stderr = client.exec_command(full, timeout=timeout)
    stdin.write(PASS + "\n")
    stdin.flush()
    try:
        stdin.channel.shutdown_write()
    except Exception:
        pass
    out = stdout.read().decode()
    lines = [l for l in out.splitlines()
             if "password" not in l.lower()[:30] and not l.startswith("[sudo]")]
    return "\n".join(lines).strip()


def main():
    client = get_client()

    # 1. Get the actual nginx conf
    print("=== NGINX CONF FOR NEXORA ===")
    r = sudo_run(client, "cat /etc/nginx/conf.d/srv2testrchon.nohost.me.d/nexora.conf 2>/dev/null")
    print(r or "NOT FOUND")
    print()

    # 2. Check if the token file has changed
    print("=== CURRENT TOKEN ===")
    r = sudo_run(client, "cat /home/yunohost.app/nexora/api-token 2>/dev/null")
    print(f"Token: [{r}]")
    print(f"Match: {r.strip() == TOKEN}")
    print()

    # 3. Simulate browser request flow (via curl from localhost)
    print("=== SIMULATING BROWSER FLOW (curl from server) ===")

    # Step 1: tenant-claim (like the console does after login)
    print("\n--- Step 1: GET /api/auth/tenant-claim ---")
    r = sudo_run(client,
        f"curl -sk -w '\\nHTTP_CODE:%{{http_code}}' "
        f"-H 'Authorization: Bearer {TOKEN}' "
        f"-H 'X-Nexora-Tenant-Id: nexora-operator' "
        f"-H 'X-Nexora-Actor-Role: admin' "
        f"-H 'Accept: application/json' "
        f"'http://127.0.0.1:38120/api/auth/tenant-claim?tenant_id=nexora-operator'"
    )
    print(r)

    # Step 2: access-context (like the console does)
    print("\n--- Step 2: GET /api/console/access-context ---")
    r = sudo_run(client,
        f"curl -sk -w '\\nHTTP_CODE:%{{http_code}}' "
        f"-H 'Authorization: Bearer {TOKEN}' "
        f"-H 'X-Nexora-Tenant-Id: nexora-operator' "
        f"-H 'X-Nexora-Actor-Role: admin' "
        f"-H 'Accept: application/json' "
        f"'http://127.0.0.1:38120/api/console/access-context'"
    )
    print(r)

    # Step 3: Same via FQDN (through nginx)
    print("\n--- Step 3: GET via FQDN (nginx) /nexora/api/v1/health ---")
    r = sudo_run(client,
        f"curl -sk -w '\\nHTTP_CODE:%{{http_code}}' "
        f"-H 'Authorization: Bearer {TOKEN}' "
        f"'https://srv2testrchon.nohost.me/nexora/api/v1/health'"
    )
    print(r)

    # Step 4: Via FQDN with double slash (like the console sends)
    print("\n--- Step 4: GET via FQDN with DOUBLE SLASH /nexora//api/console/access-context ---")
    r = sudo_run(client,
        f"curl -sk -w '\\nHTTP_CODE:%{{http_code}}' "
        f"-H 'Authorization: Bearer {TOKEN}' "
        f"-H 'X-Nexora-Tenant-Id: nexora-operator' "
        f"-H 'X-Nexora-Actor-Role: admin' "
        f"'https://srv2testrchon.nohost.me/nexora//api/console/access-context'"
    )
    print(r)

    # Step 5: Via FQDN single slash
    print("\n--- Step 5: GET via FQDN SINGLE SLASH /nexora/api/console/access-context ---")
    r = sudo_run(client,
        f"curl -sk -w '\\nHTTP_CODE:%{{http_code}}' "
        f"-H 'Authorization: Bearer {TOKEN}' "
        f"-H 'X-Nexora-Tenant-Id: nexora-operator' "
        f"-H 'X-Nexora-Actor-Role: admin' "
        f"'https://srv2testrchon.nohost.me/nexora/api/console/access-context'"
    )
    print(r)

    # Step 6: Recent journal entries
    print("\n=== RECENT JOURNAL NEXORA (last 10) ===")
    r = sudo_run(client, "journalctl -u nexora --no-pager -n 10 2>/dev/null")
    print(r)

    # Step 7: Check auth-runtime.json for rate limit state
    print("\n=== AUTH RUNTIME STATE ===")
    r = sudo_run(client, "cat /home/yunohost.app/nexora/auth-runtime.json 2>/dev/null | python3 -m json.tool 2>/dev/null || echo NOT_FOUND")
    print(r)

    client.close()


if __name__ == "__main__":
    main()
