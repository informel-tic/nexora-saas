"""Quick check of YunoHost state on remote server."""
import paramiko

SSH_HOST = "192.168.1.52"
SSH_USER = "chonsrv1test"
SSH_PASS = "Leila112//!!&"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(SSH_HOST, 22, SSH_USER, SSH_PASS)

def run(label, cmd):
    full = f"echo '{SSH_PASS}' | sudo -S -i sh -c {repr(cmd)}"
    _, stdout, stderr = client.exec_command(full)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    print(f"\n=== {label} ===")
    print(out[:2000])
    if err.strip():
        # filter sudo password prompt
        lines = [l for l in err.splitlines() if "Mot de passe" not in l and l.strip()]
        if lines:
            print("STDERR:", "\n".join(lines[:10]))

run("YunoHost domains", "yunohost domain list --output-as json")
run("YunoHost apps", "yunohost app list --output-as json")
run("Adoption report", "cat /opt/nexora/var/adoption-report.json 2>/dev/null || echo ABSENT")

client.close()
print("\nDONE")
