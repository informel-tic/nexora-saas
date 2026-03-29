"""Final validation of Nexora tenant access."""
import urllib.request
import ssl
import json

TOKEN = "9s2mGHS+YDuds1tG3b1o6TqS1uwMfRjMf642M0F0q/E="
BASE = "https://srv2testrchon.nohost.me/nexora"


def get(path, token=None):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(BASE + path)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
            body = r.read().decode()
            try:
                return r.status, json.loads(body)
            except Exception:
                return r.status, body[:200]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]
    except Exception as ex:
        return None, str(ex)


def main():
    tests = [
        ("GET", "/api/v1/health"),
        ("GET", "/api/v1/fleet"),
        ("GET", "/api/v1/tenants"),
        ("GET", "/api/console/access-context"),
    ]

    print("=" * 60)
    print("VALIDATION ACCÈS TENANT NEXORA")
    print(f"Instance : {BASE}/")
    print(f"Token    : {TOKEN[:20]}...")
    print("=" * 60)

    all_ok = True
    for method, path in tests:
        status, body = get(path)
        ok = status == 200
        if not ok:
            all_ok = False
        icon = "✓" if ok else "✗"
        print(f"[{status}] {icon} {method} {path}")
        if ok and isinstance(body, dict):
            # Show useful fields
            if "status" in body:
                print(f"       status={body['status']}")
            if "version" in body:
                print(f"       version={body['version']}")
            if "nodes" in body:
                print(f"       nodes={len(body['nodes'])}")
            if isinstance(body, list):
                print(f"       count={len(body)}")
            if "actor_role" in body:
                print(f"       role={body['actor_role']}, tenant={body.get('tenant_id')}, tier={body.get('tenant',{}).get('tier','?')}")
        elif isinstance(body, list):
            print(f"       count={len(body)}")
            if body:
                item = body[0]
                if isinstance(item, dict):
                    for k in ("tenant_id", "tier", "status"):
                        if k in item:
                            print(f"       [{k}={item[k]}]")

    print()
    if all_ok:
        print("✓ Tous les endpoints répondent 200 — Accès opérateur validé.")
    else:
        print("✗ Certains endpoints en erreur.")

    print()
    print("=== RÉSUMÉ INFOS DE CONNEXION ===")
    print(f"Console  : {BASE}/")
    print(f"API base : {BASE}/api/v1")
    print(f"Token    : {TOKEN}")
    print(f"Tenant   : nexora-operator")
    print(f"Tier     : enterprise")
    print(f"Rôle     : operator")


if __name__ == "__main__":
    main()
