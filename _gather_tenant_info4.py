"""Find the actual active token for the running nexora service."""
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
    out = stdout.read().decode().strip()
    lines = [l for l in out.splitlines() if "password" not in l.lower()[:30] and not l.startswith("[sudo]")]
    return "\n".join(lines)


def http_test(url, token=None, header_name="Authorization", header_prefix="Bearer "):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url)
    if token:
        req.add_header(header_name, f"{header_prefix}{token}")
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

    print("=== nexora.service UNIT FILE ===")
    r = sudo_run(client, "systemctl cat nexora 2>/dev/null | head -50")
    print(r)
    print()

    print("=== nexora.service ENVIRONMENT ===")
    r = sudo_run(client, "systemctl show nexora --property=Environment 2>/dev/null")
    print(r)
    print()

    print("=== nexora-node-agent.service UNIT FILE ===")
    r = sudo_run(client, "systemctl cat nexora-node-agent 2>/dev/null | head -40")
    print(r)
    print()

    print("=== ALL TOKEN FILES ===")
    r = sudo_run(client, "find /opt/nexora /etc/nexora /var/www/nexora /home/yunohost.app/nexora -name '*token*' 2>/dev/null")
    print(r or "NONE")
    print()

    print("=== OPT NEXORA VAR CONTENTS ===")
    r = sudo_run(client, "ls -la /opt/nexora/var/ 2>/dev/null")
    print(r)
    print()

    print("=== VAR WWW NEXORA CONTENTS ===")
    r = sudo_run(client, "ls -la /var/www/nexora/ 2>/dev/null")
    print(r)
    print()

    print("=== ACTUAL TOKEN IN OPT/NEXORA/VAR ===")
    r = sudo_run(client, "cat /opt/nexora/var/api-token 2>/dev/null | xxd | head -3")
    print(r)
    r2 = sudo_run(client, "wc -c /opt/nexora/var/api-token 2>/dev/null")
    print(f"bytes: {r2}")
    print()

    print("=== JOURNAL NEXORA LAST 20 ===")
    r = sudo_run(client, "journalctl -u nexora --no-pager -n 20 2>/dev/null")
    print(r)
    print()

    print("=== JOURNAL NEXORA-NODE-AGENT LAST 20 ===")
    r = sudo_run(client, "journalctl -u nexora-node-agent --no-pager -n 20 2>/dev/null")
    print(r)
    print()

    print("=== NEXORA API HEALTH (curl style) ===")
    r = sudo_run(client, "curl -sk -o - -w '\\nHTTP_STATUS:%{http_code}' https://srv2testrchon.nohost.me/nexora/api/v1/health 2>&1 | head -5")
    print(r)
    print()

    print("=== NEXORA API HEALTH WITH TOKEN (OPT) ===")
    token = sudo_run(client, "cat /opt/nexora/var/api-token 2>/dev/null")
    print(f"Token from file: {token!r}")
    r = sudo_run(client, f"curl -sk -H 'Authorization: Bearer {token}' https://srv2testrchon.nohost.me/nexora/api/v1/health 2>&1 | head -3")
    print(r)
    print()

    print("=== NEXORA TOKEN VIA ENV (proc) ===")
    r = sudo_run(client, "ps aux | grep -v grep | grep -E 'nexora|python|uvicorn' | head -10")
    print(r)
    pids = sudo_run(client, "ps aux | grep -v grep | grep -E 'nexora|uvicorn' | awk '{print $2}' | head -3")
    for pid in (pids or "").splitlines():
        pid = pid.strip()
        if pid:
            env = sudo_run(client, f"cat /proc/{pid}/environ 2>/dev/null | tr '\\0' '\\n' | grep -i token | head -5")
            print(f"PID {pid} env tokens: {env}")
    print()

    client.close()

    # Try the token with actual URL
    token_clean = token.strip()
    url = "https://srv2testrchon.nohost.me/nexora/api/v1/health"

    print(f"=== PYTHON HTTP TEST WITH CLEAN TOKEN ===")
    status, body = http_test(url, token_clean)
    print(f"[{status}] {body[:300]}")

    # Also try X-Nexora-Token header
    status2, body2 = http_test(url, token_clean, header_name="X-Nexora-Token", header_prefix="")
    print(f"[{status2}] X-Nexora-Token: {body2[:300]}")


if __name__ == "__main__":
    main()
