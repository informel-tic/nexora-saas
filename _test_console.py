"""Test Nexora console on the running server."""
import paramiko
import sys
import json

HOST = "192.168.1.125"
USER = "srv2rchon"
PASS = "Leila112//!!&"


def get_client():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        HOST, port=22, username=USER, password=PASS,
        timeout=20, auth_timeout=20, banner_timeout=20,
        allow_agent=False, look_for_keys=False,
    )
    return client


def sudo_exec(client, cmd, timeout=30):
    escaped_cmd = cmd.replace('"', '\\"')
    full_cmd = f'sudo -S bash -c "{escaped_cmd}"'
    stdin, stdout, stderr = client.exec_command(full_cmd, timeout=timeout)
    stdin.write(PASS + "\n")
    stdin.flush()
    try:
        stdin.channel.shutdown_write()
    except Exception:
        pass
    out = stdout.read().decode()
    lines = [l for l in out.split("\n")
             if not l.startswith("[sudo]") and "password" not in l.lower()[:30]]
    return "\n".join(lines).strip()


def main():
    client = get_client()

    # Get API token
    print("=== Getting API token ===")
    token = sudo_exec(client, "cat /home/yunohost.app/nexora/api-token").strip()
    print(f"Token: {token[:20]}...")
    auth_headers = f"-H 'Authorization: Bearer {token}' -H 'X-Nexora-Actor-Role: admin'"

    if "--sync-admin-role" in sys.argv:
        print("\n=== Sync token role to admin ===")
        role_payload = json.dumps(
            {"tokens": [{"token": token, "actor_role": "admin"}]},
            ensure_ascii=True,
        )
        sync_cmd = (
            "printf '%s\\n' '"
            + role_payload
            + "' > /etc/nexora/api-token-roles.json && "
            "chmod 644 /etc/nexora/api-token-roles.json && "
            "systemctl restart nexora.service && "
            "sleep 2 && systemctl is-active nexora.service"
        )
        status = sudo_exec(client, sync_cmd, timeout=90).strip()
        print(f"  nexora.service: {status}")
        mapped = sudo_exec(client, "cat /etc/nexora/api-token-roles.json")
        print(f"  role map: {mapped}")

    # Test health
    print("\n=== Health check ===")
    out = sudo_exec(client, "curl -s http://127.0.0.1:38120/api/health")
    print(f"  /api/health: {out[:200]}")

    # Test access-context with token
    print("\n=== Access context (SaaS mode) ===")
    out = sudo_exec(client, f"curl -s {auth_headers} http://127.0.0.1:38120/api/console/access-context")
    print(f"  {out[:500]}")
    try:
        ctx = json.loads(out)
        sections = ctx.get("allowed_sections", [])
        print(f"  Allowed sections: {len(sections)} -> {sections}")
    except Exception:
        pass

    # Test console HTML
    print("\n=== Console HTML ===")
    out = sudo_exec(client, "curl -s http://127.0.0.1:38120/console/ | head -30")
    print(out[:500])

    # Test API endpoints actually used by the console sections
    print("\n=== API Endpoints (console surface) ===")
    endpoints = [
        "/api/console/access-context",
        "/api/health",
        "/api/dashboard",
        "/api/identity",
        "/api/scores",
        "/api/governance/report",
        "/api/inventory/apps",
        "/api/inventory/services",
        "/api/inventory/domains",
        "/api/inventory/certs",
        "/api/security/posture",
        "/api/governance/risks",
        "/api/security/updates",
        "/api/security/fail2ban/status",
        "/api/security/open-ports",
        "/api/security/permissions-audit",
        "/api/security/recent-logins",
        "/api/pra",
        "/api/fleet",
        "/api/fleet/topology",
        "/api/blueprints",
        "/api/automation/templates",
        "/api/automation/checklists",
        "/api/mode",
        "/api/mode/escalations",
        "/api/mode/confirmations",
        "/api/admin/log",
        "/api/docker/status",
        "/api/docker/containers",
        "/api/docker/templates",
        "/api/storage/usage",
        "/api/storage/ynh-map",
        "/api/notifications/templates",
        "/api/hooks/events",
        "/api/hooks/presets",
        "/api/sla/tiers",
        "/api/plans",
        "/api/organizations",
        "/api/subscriptions",
        "/api/tenants",
    ]
    bad = []
    for ep in endpoints:
        out = sudo_exec(
            client,
            f"curl -s -o /dev/null -w '%{{http_code}}' {auth_headers} http://127.0.0.1:38120{ep} 2>/dev/null",
        )
        code = out.strip().split("\\n")[-1]
        print(f"  {ep}: {code}")
        if code not in {"200", "204"}:
            bad.append((ep, code))

    if bad:
        print("\n  Endpoints en échec:")
        for ep, code in bad:
            print(f"    - {ep}: {code}")
    else:
        print("\n  Tous les endpoints console sont OK (200/204).")

    # Test console JS files load
    print("\n=== Console static files ===")
    for f in ["app.js", "views.js", "components.js", "styles.css"]:
        out = sudo_exec(client, f"curl -s -o /dev/null -w '%{{http_code}}' http://127.0.0.1:38120/console/{f}")
        code = out.strip().split("\\n")[-1]
        print(f"  /console/{f}: {code}")

    # Test node agent
    print("\n=== Node Agent ===")
    out = sudo_exec(client, "curl -s http://127.0.0.1:38121/health")
    print(f"  /health: {out[:200]}")
    out = sudo_exec(client, "curl -s http://127.0.0.1:38121/overlay")
    print(f"  /overlay: {out[:200]}")

    # Test via nginx (external access)
    print("\n=== External access via nginx ===")
    out = sudo_exec(client, "curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1/nexora/console/")
    print(f"  https://localhost/nexora/console/: {out.strip()}")
    out = sudo_exec(client, "curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1/nexora/api/health")
    print(f"  https://localhost/nexora/api/health: {out.strip()}")

    client.close()
    print("\n=== Console test complete ===")


if __name__ == "__main__":
    main()
