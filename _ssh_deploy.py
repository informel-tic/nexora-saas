"""
Script de déploiement Nexora via SSH/SFTP + paramiko.
Usage: python _ssh_deploy.py [check|upload|deploy|full]
"""
import paramiko
import os
import tarfile
import io
import sys
import time

# ─── Config ───────────────────────────────────────────────────────────────────
SSH_HOST   = "192.168.1.52"
SSH_PORT   = 22
SSH_USER   = "chonsrv1test"
SSH_PASS   = "Leila112//!!&"
SUDO_PASS  = "Leila112//!!&"    # même mdp pour sudo

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
REMOTE_DIR  = "/root/nexora"
DOMAIN      = "srv1testrchon.ynh.fr"
PATH_URL    = "/nexora"

# Fichiers/dossiers à exclure de l'archive
EXCLUDE = {
    ".git", "__pycache__", ".pytest_cache", "dist", "build",
    "*.egg-info", ".eggs", "node_modules", ".venv", "venv",
    "_ssh_deploy.py",       # ce script lui-même
}

# ─── Helpers ─────────────────────────────────────────────────────────────────
def make_client():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(SSH_HOST, port=SSH_PORT, username=SSH_USER,
                   password=SSH_PASS, timeout=20,
                   allow_agent=False, look_for_keys=False)
    return client


def _safe_print(text):
    """Print text safely on Windows consoles that use legacy encodings."""
    try:
        print(text, end="", flush=True)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "utf-8"
        safe = text.encode(enc, errors="replace").decode(enc, errors="replace")
        print(safe, end="", flush=True)


def run(client, cmd, sudo=False, timeout=120):
    """Exécute une commande SSH et affiche la sortie en temps réel."""
    if sudo:
        cmd = f"echo '{SUDO_PASS}' | sudo -S -i sh -c {repr(cmd)}"
    print(f"\n>>> {cmd[:120]}{'...' if len(cmd)>120 else ''}")
    transport = client.get_transport()
    chan = transport.open_session()
    chan.set_combine_stderr(True)
    chan.exec_command(cmd)
    out = []
    deadline = time.time() + timeout
    while True:
        if chan.recv_ready():
            chunk = chan.recv(4096).decode("utf-8", errors="replace")
            _safe_print(chunk)
            out.append(chunk)
        if chan.exit_status_ready():
            break
        if time.time() > deadline:
            print("\n[TIMEOUT]")
            break
        time.sleep(0.1)
    # flush restant
    while chan.recv_ready():
        chunk = chan.recv(4096).decode("utf-8", errors="replace")
        _safe_print(chunk)
        out.append(chunk)
    rc = chan.recv_exit_status()
    print(f"\n[exit {rc}]")
    return rc, "".join(out)


def should_exclude(path):
    parts = path.replace("\\", "/").split("/")
    for part in parts:
        if part in EXCLUDE:
            return True
        for pat in EXCLUDE:
            if pat.startswith("*") and part.endswith(pat[1:]):
                return True
    return False


def make_tarball():
    """Crée une archive .tar.gz du projet en mémoire."""
    print(f"[+] Archivage de {PROJECT_DIR} ...")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for root, dirs, files in os.walk(PROJECT_DIR):
            # Filtrer les dossiers exclus
            dirs[:] = [d for d in dirs
                       if not should_exclude(os.path.relpath(os.path.join(root, d), PROJECT_DIR))]
            for fname in files:
                fpath = os.path.join(root, fname)
                arcname = os.path.join("nexora",
                          os.path.relpath(fpath, PROJECT_DIR))
                if not should_exclude(os.path.relpath(fpath, PROJECT_DIR)):
                    tar.add(fpath, arcname=arcname)
    size_mb = buf.tell() / 1_048_576
    print(f"[+] Archive : {size_mb:.1f} Mo")
    buf.seek(0)
    return buf


# ─── Étapes de déploiement ───────────────────────────────────────────────────
def step_check():
    print("\n=== VÉRIFICATION SERVEUR ===")
    client = make_client()
    run(client, "id ; uname -a")
    run(client, "cat /etc/os-release | grep -E 'ID|VERSION'")
    rc, out = run(client, "which yunohost && yunohost --version 2>&1 || echo 'YunoHost: NON INSTALLE'", sudo=True)
    run(client, "df -h / | tail -1")
    run(client, "free -h")
    client.close()
    return rc


def step_upload():
    print("\n=== TRANSFERT DU PROJET ===")
    client = make_client()

    # Créer le répertoire cible (en root)
    run(client, f"mkdir -p {REMOTE_DIR}", sudo=True)
    run(client, f"chown {SSH_USER}:{SSH_USER} {REMOTE_DIR}", sudo=True)

    # Uploader l'archive
    buf = make_tarball()
    sftp = client.open_sftp()
    remote_tar = f"/tmp/nexora-deploy.tar.gz"
    print(f"[+] Upload vers {remote_tar} ...")
    sftp.putfo(buf, remote_tar, file_size=buf.getbuffer().nbytes,
               callback=lambda done, total: print(
                   f"\r    {done/1_048_576:.1f}/{total/1_048_576:.1f} Mo", end=""))
    sftp.close()
    print(f"\n[+] Upload terminé")

    # Extraire dans /root
    run(client, f"tar -xzf {remote_tar} -C /root/", sudo=True)
    # Restaurer les permissions exécutables perdues lors du tar Windows
    run(client, f"find {REMOTE_DIR}/deploy -name '*.sh' -exec chmod +x {{}} \\;", sudo=True)
    run(client, f"find {REMOTE_DIR}/scripts -name '*.sh' -exec chmod +x {{}} \\;", sudo=True)
    run(client, f"chmod +x {REMOTE_DIR}/install.sh 2>/dev/null || true", sudo=True)
    run(client, f"ls -la {REMOTE_DIR}/", sudo=True)
    run(client, f"rm -f {remote_tar}")

    client.close()


def step_deploy():
    print("\n=== DÉPLOIEMENT NEXORA ===")
    client = make_client()

    # S'assurer que le domaine est enregistré dans YunoHost avant le bootstrap
    print(f"\n[+] Vérification / ajout du domaine {DOMAIN} dans YunoHost...")
    rc_dom, _ = run(client, f"yunohost domain info {DOMAIN} >/dev/null 2>&1", sudo=True, timeout=30)
    if rc_dom != 0:
        print(f"[+] Domaine {DOMAIN} absent - yunohost domain add en cours...")
        run(client, f"yunohost domain add {DOMAIN}", sudo=True, timeout=60)
    else:
        print(f"[+] Domaine {DOMAIN} deja present dans YunoHost.")

    bootstrap_cmd = (
        f"cd {REMOTE_DIR} && "
        f"MODE=fresh "
        f"PROFILE=control-plane+node-agent "
        f"ENROLLMENT_MODE=pull "
        f"DOMAIN={DOMAIN} "
        f"PATH_URL={PATH_URL} "
        f"bash ./deploy/bootstrap-full-platform.sh"
    )
    rc, out = run(client, bootstrap_cmd, sudo=True, timeout=600)

    if rc == 0:
        print("\n[OK] Bootstrap termine avec succes")
        step_validate(client)
    else:
        print(f"\n[FAIL] Bootstrap echoue (exit {rc})")
        # Afficher les dernières lignes du log
        run(client, "tail -50 /var/log/nexora/bootstrap-node.log 2>/dev/null || echo 'Log non disponible'", sudo=True)

    client.close()
    return rc


def step_validate(client=None):
    print("\n=== VALIDATION POST-INSTALL ===")
    close_after = client is None
    if client is None:
        client = make_client()

    run(client, "systemctl status nexora-control-plane --no-pager 2>&1 | head -20", sudo=True)
    run(client, "systemctl status nexora-node-agent --no-pager 2>&1 | head -20", sudo=True)
    run(client, "curl -s http://127.0.0.1:38120/api/health 2>&1", sudo=True)
    run(client, f"curl -sk https://{DOMAIN}{PATH_URL}/api/health 2>&1")

    if close_after:
        client.close()


# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "full"

    if action == "check":
        step_check()
    elif action == "upload":
        step_upload()
    elif action == "deploy":
        step_deploy()
    elif action == "validate":
        step_validate()
    elif action == "full":
        print("=== DÉPLOIEMENT COMPLET NEXORA ===")
        print(f"Cible : {SSH_USER}@{SSH_HOST}  →  {DOMAIN}{PATH_URL}")
        step_check()
        step_upload()
        step_deploy()
    else:
        print(f"Usage: python _ssh_deploy.py [check|upload|deploy|validate|full]")
        sys.exit(1)
