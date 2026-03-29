"""Functional verification of Owner vs Subscriber separation."""
import os, json, tempfile
from pathlib import Path

from nexora_node_sdk.auth import get_api_token, build_tenant_scope_claim
import control_plane.api as api_module
from control_plane.api import build_application
from nexora_saas.orchestrator import NexoraService
from starlette.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent

tmp_dir = tempfile.mkdtemp()
state_path = Path(tmp_dir) / "state.json"
api_module.service = NexoraService(REPO_ROOT, state_path=state_path)
client = TestClient(api_module.app, raise_server_exceptions=False)
TOKEN = get_api_token()
headers = {
    "Authorization": f"Bearer {TOKEN}",
    "X-Nexora-Action": "test-mutation",
    "Origin": "http://testserver",
    "Referer": "http://testserver/console",
}

# --- OPERATOR (admin) ---
print("=== OPERATOR (admin) access-context ===")
role_file = Path(tmp_dir) / "roles-admin.json"
role_file.write_text(json.dumps({TOKEN: "admin"}), encoding="utf-8")
os.environ["NEXORA_API_TOKEN_ROLE_FILE"] = str(role_file)

r = client.get("/api/console/access-context", headers={**headers, "X-Nexora-Actor-Role": "admin"})
d = r.json()
print(f"  role={d.get('actor_role')}  is_operator={d.get('is_operator')}  is_owner={d.get('is_owner')}")
print(f"  allowed_sections={d.get('allowed_sections')}")
print(f"  subscriber_mode={d.get('subscriber_mode')}")
print()

# --- SUBSCRIBER ---
print("=== SUBSCRIBER access-context ===")
role_file_sub = Path(tmp_dir) / "roles-subscriber.json"
role_file_sub.write_text(json.dumps({TOKEN: "subscriber"}), encoding="utf-8")
os.environ["NEXORA_API_TOKEN_ROLE_FILE"] = str(role_file_sub)

r2 = client.get("/api/console/access-context", headers={**headers, "X-Nexora-Actor-Role": "subscriber", "X-Nexora-Tenant-Id": "ten-abc"})
d2 = r2.json()
print(f"  role={d2.get('actor_role')}  is_operator={d2.get('is_operator')}  is_owner={d2.get('is_owner')}")
print(f"  allowed_sections={d2.get('allowed_sections')}")
print(f"  subscriber_mode={d2.get('subscriber_mode')}")
print()

# --- OBSERVER ---
print("=== OBSERVER access-context ===")
role_file_obs = Path(tmp_dir) / "roles-observer.json"
role_file_obs.write_text(json.dumps({TOKEN: "observer"}), encoding="utf-8")
os.environ["NEXORA_API_TOKEN_ROLE_FILE"] = str(role_file_obs)

r3 = client.get("/api/console/access-context", headers={**headers, "X-Nexora-Actor-Role": "observer"})
d3 = r3.json()
print(f"  role={d3.get('actor_role')}  is_operator={d3.get('is_operator')}  is_owner={d3.get('is_owner')}")
print(f"  allowed_sections={d3.get('allowed_sections')}")
print()

# --- OWNER LOGIN (no passphrase configured) ---
print("=== OWNER check (no passphrase configured) ===")
os.environ.pop("NEXORA_API_TOKEN_ROLE_FILE", None)
r4 = client.post("/api/auth/owner-login", json={"passphrase": "test"}, headers={"X-Nexora-Action": "owner-login", "Origin": "http://testserver", "Referer": "http://testserver/owner-console"})
print(f"  status={r4.status_code} detail={r4.json().get('detail', '')}")
print()

# --- SUBSCRIBER blocked from operator-only routes ---
print("=== SUBSCRIBER blocked from operator-only routes ===")
role_file_sub2 = Path(tmp_dir) / "roles-subscriber2.json"
role_file_sub2.write_text(json.dumps({TOKEN: "subscriber"}), encoding="utf-8")
os.environ["NEXORA_API_TOKEN_ROLE_FILE"] = str(role_file_sub2)

r5 = client.post("/api/adoption/import?domain=example.org&path=/nexora", headers={**headers, "X-Nexora-Actor-Role": "subscriber"})
print(f"  status={r5.status_code}")
if r5.status_code == 403:
    print(f"  BLOCKED correctly: {r5.json().get('detail', r5.text[:80])}")

r5b = client.get("/api/settings", headers={**headers, "X-Nexora-Actor-Role": "subscriber"})
print(f"  /api/settings status={r5b.status_code}")
if r5b.status_code == 403:
    print(f"  BLOCKED correctly: {r5b.json().get('detail', r5b.text[:80])}")
print()

# --- SECTION DIFF ---
print("=== SECTION DIFF: operator vs subscriber ===")
op_sections = set(d.get("allowed_sections", []))
sub_sections = set(d2.get("allowed_sections", []))
obs_sections = set(d3.get("allowed_sections", []))
print(f"  Operator-only sections: {sorted(op_sections - sub_sections)}")
print(f"  Observer extra vs sub:  {sorted(obs_sections - sub_sections)}")
print(f"  Subscriber sections:    {sorted(sub_sections)}")
print()

# Assertions
errors = []
if not d.get("is_operator"):
    errors.append("Admin should be is_operator=True")
if d2.get("is_operator"):
    errors.append("Subscriber should be is_operator=False")
if not d2.get("subscriber_mode"):
    errors.append("Subscriber should have subscriber_mode=True")
if "settings" in sub_sections:
    errors.append("Subscriber should NOT have 'settings' section")
if "tenants" in sub_sections:
    errors.append("Subscriber should NOT have 'tenants' section")
if "settings" not in op_sections:
    errors.append("Operator should have 'settings' section")
if r4.status_code not in (401, 503):
    errors.append(f"Owner login without passphrase should return 401 or 503, got {r4.status_code}")
if r5.status_code != 403:
    errors.append(f"Subscriber adoption import should return 403, got {r5.status_code}")
if r5b.status_code != 403:
    errors.append(f"Subscriber /api/settings should return 403, got {r5b.status_code}")

# Cleanup
os.environ.pop("NEXORA_API_TOKEN_ROLE_FILE", None)
import shutil
shutil.rmtree(tmp_dir, ignore_errors=True)

if errors:
    print("ERRORS:")
    for e in errors:
        print(f"  - {e}")
    exit(1)
else:
    print("ALL VERIFICATION CHECKS PASSED")
