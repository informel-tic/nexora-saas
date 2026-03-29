"""Get the actual active token and test it."""
import paramiko
import urllib.request
import ssl

HOST = "192.168.1.125"
USER = "srv2rchon"
PASS = "Leila112//!!&"


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
    lines = [l for l in out.splitlines() if "password" not in l.lower()[:30] and not l.startswith("[sudo]")]
    return "\n".join(lines).strip()


def http_test(url, token=None, header_name="Authorization", header_prefix="Bearer "):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url)
    if token:
        req.add_header(header_name, f"{header_prefix}{token}")
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
            body = r.read().decode()[:800]
            return r.status, body
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]
    except Exception as ex:
        return None, str(ex)


def main():
    client = get_client()

    print("=== TOKEN ACTIF (home/yunohost.app/nexora/api-token) ===")
    token = sudo_run(client, "cat /home/yunohost.app/nexora/api-token 2>/dev/null")
    print(f"Token: {token!r}")
    print()

    print("=== HOME/YUNOHOST.APP/NEXORA/ CONTENTS ===")
    r = sudo_run(client, "ls -la /home/yunohost.app/nexora/ 2>/dev/null")
    print(r)
    print()

    print("=== STATE JSON (home) ===")
    r = sudo_run(client, "python3 -c \"import json; d=json.load(open('/home/yunohost.app/nexora/state.json')); print('tenants:', len(d.get('tenants',[])), '| nodes:', len(d.get('nodes',[])), '| schema:', d.get('_persistence',{}).get('schema_version','?'))\" 2>/dev/null || echo NOT_FOUND")
    print(r)
    print()

    # Try curl with correct token
    token_clean = token.strip()
    print(f"=== CURL TEST WITH HOME TOKEN ({token_clean[:20]}...) ===")
    r = sudo_run(client, f"curl -sk -H 'Authorization: Bearer {token_clean}' https://localhost:38120/api/v1/health 2>&1 | head -3")
    print(f"localhost:38120: {r}")

    r2 = sudo_run(client, f"curl -sk -H 'Authorization: Bearer {token_clean}' https://srv2testrchon.nohost.me/nexora/api/v1/health 2>&1 | head -3")
    print(f"public FQDN: {r2}")
    print()

    client.close()

    # Python HTTP tests
    base = "https://srv2testrchon.nohost.me"
    endpoints = [
        "/nexora/api/v1/health",
        "/nexora/api/v1/status",
        "/nexora/api/v1/nodes",
        "/nexora/api/v1/fleet",
        "/nexora/api/v1/tenants",
        "/nexora/console/access-context",
        "/nexora/api/console/access-context",
    ]

    print("=== HTTP TESTS WITH ACTIVE TOKEN ===")
    for ep in endpoints:
        url = base + ep
        status, body = http_test(url, token_clean)
        print(f"[{status}] {ep}")
        if status == 200:
            print(f"  -> {body[:300]}")
        elif status != 200:
            print(f"  -> {body[:150]}")

    print()
    print(f"\n=== RÉSUMÉ ACCÈS OPÉRATEUR ===")
    print(f"Console URL : https://srv2testrchon.nohost.me/nexora/")
    print(f"API base    : https://srv2testrchon.nohost.me/nexora/api/v1")
    print(f"Token actif : {token_clean}")
    print(f"X-Nexora-Token: {token_clean}")


if __name__ == "__main__":
    main()
