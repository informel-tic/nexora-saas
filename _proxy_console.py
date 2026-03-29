"""Local HTTP proxy to remote Nexora console via SSH+curl."""
import http.server
import paramiko
import sys
import json

HOST = "192.168.1.125"
USER = "srv2rchon"
PASS = "Leila112//!!&"
REMOTE_BASE = "http://127.0.0.1:38120"
LOCAL_PORT = 48120

# Persistent SSH connection
_client = None


def get_client():
    global _client
    if _client is None or _client.get_transport() is None or not _client.get_transport().is_active():
        _client = paramiko.SSHClient()
        _client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        _client.connect(
            HOST, port=22, username=USER, password=PASS,
            timeout=20, auth_timeout=20, banner_timeout=20,
            allow_agent=False, look_for_keys=False,
        )
    return _client


def sudo_fetch(path, token=None):
    """Fetch a URL from the remote server via SSH + curl."""
    client = get_client()
    headers = ""
    if token:
        headers = f"-H 'Authorization: Bearer {token}' -H 'X-Nexora-Actor-Role: admin'"
    cmd = f"curl -s -w '\\n---HTTP_STATUS:%{{http_code}}---' {headers} '{REMOTE_BASE}{path}'"
    escaped = cmd.replace('"', '\\"')
    full = f'sudo -S bash -c "{escaped}"'
    stdin, stdout, stderr = client.exec_command(full, timeout=30)
    stdin.write(PASS + "\n")
    stdin.flush()
    try:
        stdin.channel.shutdown_write()
    except Exception:
        pass
    raw = stdout.read().decode(errors="replace")
    # Filter sudo prompt lines
    lines = []
    for l in raw.split("\n"):
        if l.startswith("[sudo]") or "password" in l.lower()[:30]:
            continue
        lines.append(l)
    raw = "\n".join(lines)

    # Extract status code
    status = 200
    if "---HTTP_STATUS:" in raw:
        idx = raw.rfind("---HTTP_STATUS:")
        status_str = raw[idx:].replace("---HTTP_STATUS:", "").replace("---", "").strip()
        try:
            status = int(status_str)
        except ValueError:
            pass
        raw = raw[:idx]
    return status, raw


# Read token once at startup
def read_token():
    client = get_client()
    escaped = 'cat /home/yunohost.app/nexora/api-token'
    full = f'sudo -S bash -c "{escaped}"'
    stdin, stdout, stderr = client.exec_command(full, timeout=10)
    stdin.write(PASS + "\n")
    stdin.flush()
    try:
        stdin.channel.shutdown_write()
    except Exception:
        pass
    out = stdout.read().decode().strip()
    lines = [l for l in out.split("\n")
             if not l.startswith("[sudo]") and "password" not in l.lower()[:30]]
    return "\n".join(lines).strip()


TOKEN = None


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global TOKEN
        if TOKEN is None:
            TOKEN = read_token()

        path = self.path
        # Determine content type
        if path.endswith(".js"):
            ct = "application/javascript; charset=utf-8"
        elif path.endswith(".css"):
            ct = "text/css; charset=utf-8"
        elif path.endswith(".html") or path.endswith("/"):
            ct = "text/html; charset=utf-8"
        elif "/api/" in path:
            ct = "application/json; charset=utf-8"
        else:
            ct = "text/plain; charset=utf-8"

        # Some deployments protect console assets behind auth too, so proxy
        # authenticated requests for both API and console static paths.
        protected_prefixes = ("/api/", "/console/")
        use_token = TOKEN if path.startswith(protected_prefixes) else None
        status, body = sudo_fetch(path, token=use_token)

        self.send_response(status)
        self.send_header("Content-Type", ct)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, fmt, *args):
        print(f"  {args[0]}" if args else "")


def main():
    global TOKEN
    print(f"Starting proxy on http://127.0.0.1:{LOCAL_PORT}")
    print("Connecting to remote server...")
    get_client()
    TOKEN = read_token()
    print(f"Token: {TOKEN[:20]}...")
    print(f"\nOpen http://127.0.0.1:{LOCAL_PORT}/console/ in browser")
    print("Press Ctrl+C to stop.\n")
    sys.stdout.flush()

    server = http.server.HTTPServer(("127.0.0.1", LOCAL_PORT), ProxyHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
