"""Gather Nexora tenant connection info from test server."""
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


def run(client, cmd, timeout=30):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    return stdout.read().decode().strip()


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
    # strip sudo noise
    lines = [l for l in out.splitlines() if "password" not in l.lower()[:30] and not l.startswith("[sudo]")]
    return "\n".join(lines)


def main():
    print(f"Connecting to {HOST}...")
    client = get_client()
    print("Connected.\n")

    sections = [
        ("SERVICES NEXORA", "systemctl list-units --type=service | grep -i nexora || echo NONE"),
        ("PORTS EN ECOUTE", "ss -tlnp 2>/dev/null | grep -E '3812[0-9]|8080|38[0-9]{3}' || netstat -tlnp 2>/dev/null | grep -E '3812[0-9]|8080|38[0-9]{3}' || echo NONE"),
        ("CONFIG /etc/nexora/", "ls /etc/nexora/ 2>/dev/null || echo NO_DIR"),
        ("NEXORA.CONF", "cat /etc/nexora/nexora.conf 2>/dev/null || echo NOT_FOUND"),
        ("OPERATOR TOKEN", "cat /etc/nexora/operator_token 2>/dev/null || cat /var/www/nexora/operator_token 2>/dev/null || find /var/www/nexora /etc/nexora -name 'operator_token' 2>/dev/null | head -3 || echo NOT_FOUND"),
        ("STATE FILE", "cat /var/www/nexora/repo/.nexora_state.json 2>/dev/null | python3 -c \"import sys,json; d=json.load(sys.stdin); print(json.dumps({k:v for k,v in d.items() if 'secret' not in k.lower() and 'pass' not in k.lower()}, indent=2))\" 2>/dev/null || echo NOT_FOUND"),
        ("CONTROL PLANE PROCESS", "ps aux | grep -E 'control_plane|nexora' | grep -v grep | head -10 || echo NONE"),
        ("YUNOHOST DOMAIN", "yunohost domain list 2>/dev/null || echo NO_YNH"),
        ("NGINX NEXORA CONF", "grep -r 'nexora\\|38120\\|38121' /etc/nginx/conf.d/ 2>/dev/null | head -20 || cat /etc/nginx/conf.d/nexora*.conf 2>/dev/null | head -30 || echo NONE"),
        ("ENV VARS NEXORA SERVICE", "systemctl show nexora-control-plane 2>/dev/null | grep -E 'Environment|ExecStart' | head -20 || echo NONE"),
        ("TOKEN FROM SYSTEMD ENV", "systemctl cat nexora-control-plane 2>/dev/null | head -40 || cat /etc/systemd/system/nexora*.service 2>/dev/null | head -40 || echo NONE"),
        ("HOSTNAME/IP", "hostname -f 2>/dev/null; ip -4 addr show | grep 'inet ' | grep -v '127.0' | head -5"),
    ]

    for title, cmd in sections:
        print(f"=== {title} ===")
        result = sudo_run(client, cmd)
        print(result if result else "(empty)")
        print()

    client.close()
    print("=== DONE ===")


if __name__ == "__main__":
    main()
