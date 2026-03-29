"""Gather Nexora token and nginx config details."""
import paramiko

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


def main():
    client = get_client()

    sections = [
        ("API TOKEN (operator)", "cat /opt/nexora/var/api-token 2>/dev/null || echo NOT_FOUND"),
        ("API TOKEN (/etc/nexora)", "cat /etc/nexora/api-token 2>/dev/null || echo NOT_FOUND"),
        ("API TOKEN ROLES", "cat /etc/nexora/api-token-roles.json 2>/dev/null || echo NOT_FOUND"),
        ("STATE JSON", "cat /opt/nexora/var/state.json 2>/dev/null | python3 -m json.tool 2>/dev/null || echo NOT_FOUND"),
        ("NGINX ALL LOCS WITH 38120", "grep -r '38120\\|38121\\|nexora' /etc/nginx/ 2>/dev/null | head -40 || echo NONE"),
        ("NGINX YUNOHOST APP CONF", "ls /etc/nginx/conf.d/ 2>/dev/null | head -30"),
        ("YUNOHOST APP LIST", "yunohost app list 2>/dev/null | grep -E 'id:|label:|url:' | head -30 || echo NONE"),
        ("NEXORA APP URL (ynh)", "yunohost app info nexora 2>/dev/null || yunohost app info nexora-saas 2>/dev/null || echo 'not installed as ynh app'"),
        ("NEXORA SERVICE STATUS", "systemctl status nexora 2>/dev/null | head -20"),
        ("NEXORA CP STATUS", "systemctl status nexora-control-plane 2>/dev/null | head -20 || echo NOT_FOUND"),
        ("NEXORA NODE AGENT STATUS", "systemctl status nexora-node-agent 2>/dev/null | head -20"),
        ("NEXORA OPT DIR", "ls /opt/nexora/var/ 2>/dev/null || echo NOT_FOUND"),
        ("JOURNAL NEXORA RECENT", "journalctl -u nexora -u nexora-control-plane --no-pager -n 20 2>/dev/null || echo NONE"),
        ("TENANT TOKENS IN STATE", "cat /opt/nexora/var/state.json 2>/dev/null | python3 -c \"import sys,json; d=json.load(sys.stdin); tenants=d.get('tenants',{}); [print(f'tenant={k}  token={v.get(\\\"token\\\",\\\"N/A\\\")}  tier={v.get(\\\"tier\\\",\\\"?\\\")}') for k,v in tenants.items()]\" 2>/dev/null || echo NO_TENANTS"),
    ]

    for title, cmd in sections:
        print(f"=== {title} ===")
        result = sudo_run(client, cmd)
        print(result if result else "(empty)")
        print()

    client.close()


if __name__ == "__main__":
    main()
