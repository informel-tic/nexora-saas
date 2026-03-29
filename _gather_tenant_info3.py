"""Get nginx config and test Nexora HTTP access."""
import paramiko
import urllib.request
import ssl
import json

HOST = "192.168.1.125"
USER = "srv2rchon"
PASS = "Leila112//!!&"

# Tokens collected
TOKEN_OPT = "FDZZn3rQQ9jAVMyOZk830v/YaVYbtGzbI68vjANxXf4="
TOKEN_ETC = "AtvZ6Y_XEMyA-jiqVQPuQLOHRNvT27OBxY54HrkqX0M"


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
    out = stdout.read().decode().strip()
    lines = [l for l in out.splitlines() if "password" not in l.lower()[:30] and not l.startswith("[sudo]")]
    return "\n".join(lines)


def http_test(url, token=None):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
            body = r.read().decode()[:500]
            return r.status, body
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]
    except Exception as ex:
        return None, str(ex)


def main():
    client = get_client()

    print("=== NGINX NEXORA LOCATION CONF ===")
    result = sudo_run(client, "find /etc/nginx -name '*.conf' | xargs grep -l 'nexora\\|38120' 2>/dev/null")
    print(result or "NONE")
    print()

    print("=== NGINX CONF FILES WITH NEXORA ===")
    for f in (result or "").splitlines():
        if f.strip():
            content = sudo_run(client, f"cat {f.strip()}")
            print(f"--- {f.strip()} ---")
            print(content[:2000])
            print()

    print("=== YUNOHOST APP NEXORA SETTINGS ===")
    r = sudo_run(client, "cat /etc/yunohost/apps/nexora/settings.yml 2>/dev/null || cat /etc/yunohost/apps/nexora-saas/settings.yml 2>/dev/null || echo NOT_FOUND")
    print(r)
    print()

    print("=== API-TOKEN-ROLES RAW HEX ===")
    r = sudo_run(client, "xxd /etc/nexora/api-token-roles.json 2>/dev/null | head -5")
    print(r)
    r2 = sudo_run(client, "cat /etc/nexora/api-token-roles.json | od -c | head -5")
    print(r2)
    print()

    # Read as UTF-16 / attempt fix
    print("=== API-TOKEN-ROLES (python decode) ===")
    r = sudo_run(client, "python3 -c \"data=open('/etc/nexora/api-token-roles.json','rb').read(); import json; d=json.loads(data.decode('utf-8-sig')); print(json.dumps(d,indent=2))\" 2>/dev/null || echo FAILED")
    print(r)
    print()

    client.close()

    # HTTP tests
    base = "https://srv2testrchon.nohost.me"
    paths = [
        "/nexora/",
        "/nexora/api/v1/health",
        "/nexora/api/v1/status",
        "/nexora/api/v1/nodes",
        "/nexora/api/v1/fleet",
    ]

    print("=== HTTP ACCESS TESTS ===")
    for path in paths:
        url = base + path
        status, body = http_test(url)
        print(f"[{status}] {path}")
        if body:
            print(f"  -> {body[:200]}")

    print()
    print("=== HTTP ACCESS TESTS WITH TOKEN (opt) ===")
    for path in paths:
        url = base + path
        status, body = http_test(url, TOKEN_OPT)
        print(f"[{status}] {path}")
        if body:
            print(f"  -> {body[:200]}")

    print()
    print("=== HTTP ACCESS TESTS WITH TOKEN (etc) ===")
    for path in ["/nexora/api/v1/health", "/nexora/api/v1/nodes"]:
        url = base + path
        status, body = http_test(url, TOKEN_ETC)
        print(f"[{status}] {path}")
        if body:
            print(f"  -> {body[:200]}")


if __name__ == "__main__":
    main()
