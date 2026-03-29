"""Deploy 3-domain architecture to test server.

Connects via paramiko, syncs code, creates YunoHost subdomains,
installs nginx vhost configs, installs SSL certs, restarts services.
"""
import paramiko
import os
import sys
import time

HOST = "192.168.1.125"
USER = "srv2rchon"
PASS = os.environ.get("NEXORA_SSH_PASS", "Leila112//!!&")
DOMAIN = "srv2testrchon.nohost.me"
PORT = "38120"
REPO_LOCAL = os.path.dirname(os.path.abspath(__file__))
REPO_REMOTE = "/var/www/nexora/repo"
STAGING = "/tmp/nexora-deploy"

SKIP_DIRS = {
    "__pycache__", ".git", ".venv", ".venvaudit", "node_modules",
    "_ext", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".vscode",
}

SYNC_ITEMS = ["src", "apps", "deploy", "blueprints", "pyproject.toml", "README.md"]


def get_client():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        HOST, port=22, username=USER, password=PASS,
        timeout=30, auth_timeout=20, banner_timeout=20,
        allow_agent=False, look_for_keys=False,
    )
    return client


def sudo_exec(client, cmd, timeout=120):
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
    err = stderr.read().decode()
    lines = [l for l in out.split("\n")
             if not l.startswith("[sudo]") and "password" not in l.lower()[:30]]
    return "\n".join(lines).strip(), err.strip()


def run(client, cmd, timeout=30):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    return stdout.read().decode().strip(), stderr.read().decode().strip()


def upload_recursive(sftp, local_dir, remote_dir, count=0):
    try:
        sftp.stat(remote_dir)
    except FileNotFoundError:
        sftp.mkdir(remote_dir)
    for item in sorted(os.listdir(local_dir)):
        if item in SKIP_DIRS:
            continue
        local_path = os.path.join(local_dir, item)
        remote_path = remote_dir + "/" + item
        if os.path.isdir(local_path):
            count = upload_recursive(sftp, local_path, remote_path, count)
        elif os.path.isfile(local_path):
            sftp.put(local_path, remote_path)
            count += 1
            if count % 100 == 0:
                print(f"    ... {count} files uploaded")
    return count


def main():
    step = sys.argv[1] if len(sys.argv) > 1 else "full"

    print(f"=== Nexora 3-Domain Deployment to {HOST} ===")
    print(f"Domain: {DOMAIN}  Port: {PORT}")
    print()

    client = get_client()
    print("SSH connected.\n")

    # ---- Step 1: Sync code ----
    if step in ("full", "sync"):
        print("[1/7] Uploading code via SFTP...")
        sudo_exec(client, f"rm -rf {STAGING} && mkdir -p {STAGING} && chown {USER}:{USER} {STAGING}")
        sftp = client.open_sftp()
        total = 0
        for item in SYNC_ITEMS:
            local_path = os.path.join(REPO_LOCAL, item)
            remote_path = STAGING + "/" + item
            if os.path.isdir(local_path):
                print(f"  {item}/ ...")
                total = upload_recursive(sftp, local_path, remote_path, total)
            elif os.path.isfile(local_path):
                sftp.put(local_path, remote_path)
                total += 1
        sftp.close()
        print(f"  Uploaded {total} files.")

        print("  Copying to deployment directory...")
        for item in SYNC_ITEMS:
            sudo_exec(client, f"rm -rf {REPO_REMOTE}/{item} && cp -r {STAGING}/{item} {REPO_REMOTE}/{item}")
        sudo_exec(client, f"chown -R nexora:nexora {REPO_REMOTE} && rm -rf {STAGING}")
        print("  Done.\n")

        # Re-install package
        print("  Re-installing package in venv...")
        for venv in ["/var/www/nexora/venv", "/opt/nexora/venv"]:
            out, err = sudo_exec(client,
                f"cd {REPO_REMOTE} && {venv}/bin/pip install -e . 2>&1 | tail -3",
                timeout=180)
            print(f"    {venv}: {out}")
        print()

    # ---- Step 2: Stop services ----
    if step in ("full", "domains"):
        print("[2/7] Stopping control-plane to apply changes...")
        sudo_exec(client, "systemctl stop nexora.service 2>/dev/null || true")
        sudo_exec(client, "systemctl stop nexora-control-plane.service 2>/dev/null || true")
        print("  Stopped.\n")

    # ---- Step 3: Create subdomains in YunoHost ----
    if step in ("full", "domains"):
        print("[3/7] Creating subdomains in YunoHost...")
        for sub in ["saas", "www", "console"]:
            fqdn = f"{sub}.{DOMAIN}"
            print(f"  Adding {fqdn}...")
            out, err = sudo_exec(client,
                f"yunohost domain list --output-as json 2>/dev/null | grep -q '{fqdn}' && echo EXISTS || yunohost domain add {fqdn} 2>&1",
                timeout=60)
            result = out.strip().split("\n")[-1] if out.strip() else err.strip().split("\n")[-1]
            print(f"    -> {result}")
        print()

    # ---- Step 4: Install SSL certificates ----
    if step in ("full", "domains", "certs"):
        print("[4/7] Installing Let's Encrypt certificates...")
        for sub in ["saas", "www", "console"]:
            fqdn = f"{sub}.{DOMAIN}"
            print(f"  Requesting cert for {fqdn}...")
            out, err = sudo_exec(client,
                f"yunohost domain cert install {fqdn} --no-checks 2>&1",
                timeout=120)
            # Show last meaningful line
            lines = [l for l in (out + "\n" + err).split("\n") if l.strip()]
            result = lines[-1] if lines else "no output"
            print(f"    -> {result}")
            time.sleep(2)  # Rate limit between cert requests
        print()

    # ---- Step 5: Install nginx vhost configs ----
    if step in ("full", "domains", "nginx"):
        print("[5/7] Installing nginx vhost configurations...")
        # YunoHost-compatible location-only templates (no server{} blocks)
        templates = {
            "ynh-saas.conf": "saas",
            "ynh-console.conf": "console",
            "ynh-www.conf": "www",
        }
        for tpl_name, sub in templates.items():
            tpl_local = os.path.join(REPO_LOCAL, "deploy", "templates", tpl_name)
            if not os.path.exists(tpl_local):
                print(f"  ERROR: Template not found: {tpl_local}")
                continue

            # Read template and substitute __PORT__
            with open(tpl_local, "r", encoding="utf-8") as f:
                content = f.read()
            content = content.replace("__PORT__", PORT)

            fqdn = f"{sub}.{DOMAIN}"
            nginx_dir = f"/etc/nginx/conf.d/{fqdn}.d"
            output_name = "nexora.conf"

            # Remove any old broken configs first
            sudo_exec(client, f"rm -f {nginx_dir}/nexora-*.conf 2>/dev/null || true")

            # Upload via SFTP
            sftp = client.open_sftp()
            tmp_path = f"/tmp/nexora-{sub}.conf"
            with sftp.open(tmp_path, "w") as f:
                f.write(content)
            sftp.close()

            sudo_exec(client, f"mkdir -p {nginx_dir}")
            sudo_exec(client, f"mv {tmp_path} {nginx_dir}/{output_name}")
            print(f"  -> {nginx_dir}/{output_name}")

        # Configure SSOwat to skip Nexora paths (avoid YunoHost SSO interception)
        print("  Configuring SSOwat permissions...")
        for sub in ["saas", "www", "console"]:
            fqdn = f"{sub}.{DOMAIN}"
            # Add unprotected regex for all paths on Nexora subdomains
            out, err = sudo_exec(client,
                f"yunohost app setting nexora unprotected_regex -v '/' 2>/dev/null; "
                f"python3 -c \""
                f"import json, os; "
                f"p='/etc/ssowat/conf.json'; "
                f"d=json.load(open(p)) if os.path.exists(p) else {{}}; "
                f"u=d.setdefault('permissions', {{}}).setdefault('nexora.main', {{}}).setdefault('uris', []); "
                f"uri='re:{fqdn}/.*'; "
                f"(u.append(uri) if uri not in u else None); "
                f"json.dump(d,open(p,'w'),indent=2)"
                f"\" 2>&1",
                timeout=30)
            print(f"    SSOwat {fqdn}: configured")

        # Also remove old nexora.conf from base domain .d/ that had path-based proxy
        sudo_exec(client, f"rm -f /etc/nginx/conf.d/{DOMAIN}.d/nexora.conf 2>/dev/null || true")

        print("  Testing nginx config...")
        out, err = sudo_exec(client, "nginx -t 2>&1")
        combined = out + " " + err
        if "successful" in combined.lower():
            print("  nginx -t: OK")
            sudo_exec(client, "systemctl reload nginx")
            print("  nginx reloaded.")
        else:
            print(f"  nginx -t FAILED: {combined}")
            print("  NOT reloading nginx. Fix manually.")
        print()

    # ---- Step 6: Start services ----
    if step in ("full", "start"):
        print("[6/7] Starting services...")
        sudo_exec(client, "systemctl daemon-reload")
        # Start control plane
        sudo_exec(client, "systemctl enable nexora.service 2>/dev/null || true")
        sudo_exec(client, "systemctl restart nexora.service")
        time.sleep(5)
        out, _ = sudo_exec(client, "systemctl is-active nexora.service")
        cp_status = out.strip().split("\n")[-1]
        print(f"  nexora.service: {cp_status}")

        # Start node agent
        sudo_exec(client, "systemctl restart nexora-node-agent.service")
        time.sleep(2)
        out, _ = sudo_exec(client, "systemctl is-active nexora-node-agent.service")
        na_status = out.strip().split("\n")[-1]
        print(f"  nexora-node-agent.service: {na_status}")

        # Wait for API to be ready
        print("  Waiting for API startup...")
        for i in range(30):
            out, _ = sudo_exec(client, "curl -sf http://127.0.0.1:38120/api/health -o /dev/null -w '%{http_code}' 2>/dev/null || echo 000")
            code = out.strip().split("\n")[-1]
            if code == "200":
                print(f"  API ready after {i+1}s")
                break
            time.sleep(1)
        else:
            print("  WARNING: API not ready after 30s")
            out, _ = sudo_exec(client, "journalctl -u nexora.service --no-pager -n 15 2>&1")
            print(f"  Logs:\n{out}")
        print()

    # ---- Step 7: Verify all surfaces ----
    if step in ("full", "verify"):
        print("[7/7] Verifying all surfaces from server...")
        checks = [
            ("http://127.0.0.1:38120/api/health", "API Health (direct)"),
            (f"https://saas.{DOMAIN}/api/health", f"saas.{DOMAIN} health"),
            (f"https://www.{DOMAIN}/", f"www.{DOMAIN} public"),
            (f"https://console.{DOMAIN}/console/", f"console.{DOMAIN} console"),
            (f"https://saas.{DOMAIN}/owner-console/", f"saas.{DOMAIN} owner-console"),
        ]
        for url, label in checks:
            out, _ = sudo_exec(client,
                f"curl -sk -o /dev/null -w '%{{http_code}}' '{url}' 2>/dev/null || echo 000")
            code = out.strip().split("\n")[-1]
            status = "OK" if code in ("200", "302", "307") else f"FAIL({code})"
            print(f"  {label}: HTTP {code} {status}")

        # Check SSL cert validity
        print("\n  SSL certificate check:")
        for sub in ["saas", "www", "console"]:
            fqdn = f"{sub}.{DOMAIN}"
            out, _ = sudo_exec(client,
                f"echo | openssl s_client -servername {fqdn} -connect 127.0.0.1:443 2>/dev/null | openssl x509 -noout -subject -dates 2>/dev/null || echo 'NO CERT'")
            lines = [l for l in out.split("\n") if l.strip()]
            print(f"  {fqdn}:")
            for l in lines:
                print(f"    {l}")

        # Show service status summary
        print("\n  Service summary:")
        out, _ = sudo_exec(client, "journalctl -u nexora.service --no-pager -n 5 2>&1")
        print(f"  Last control-plane logs:\n{out}")

    print("\n=== Deployment complete ===")
    print(f"  Owner console:  https://saas.{DOMAIN}/")
    print(f"  Public site:    https://www.{DOMAIN}/")
    print(f"  Subscriber:     https://console.{DOMAIN}/console/")
    print()

    client.close()


if __name__ == "__main__":
    main()
