"""Diagnose and fix nexora service namespace issue."""
import paramiko
import os
import time
import sys

HOST = "192.168.1.125"
USER = "srv2rchon"
PASS = "Leila112//!!&"


def run_sudo(ssh, cmd: str) -> str:
    chan = ssh.get_transport().open_session()
    chan.get_pty()
    chan.exec_command(f"sudo -S bash -c {repr(cmd)}")
    time.sleep(0.5)
    chan.sendall((PASS + "\n").encode())
    output = b""
    deadline = time.time() + 20
    while time.time() < deadline:
        if chan.exit_status_ready():
            break
        if chan.recv_ready():
            output += chan.recv(4096)
        else:
            time.sleep(0.1)
    output += chan.recv(65536)
    chan.close()
    return output.decode(errors="replace").strip()


def run(ssh, cmd: str) -> str:
    _, out, err = ssh.exec_command(cmd, timeout=15)
    return (out.read() + err.read()).decode(errors="replace").strip()


def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASS,
                allow_agent=False, look_for_keys=False,
                timeout=15, banner_timeout=15, auth_timeout=15)
    print("Connected!")

    # 1 — Show systemd unit file
    print("\n=== SYSTEMD UNIT FILE ===")
    unit = run_sudo(ssh, "cat /etc/systemd/system/nexora.service")
    # strip password prompt
    lines = unit.split("\n")
    unit_clean = "\n".join(l for l in lines if not l.startswith("[sudo]") and "Mot de passe" not in l)
    print(unit_clean[:4000])

    # 2 — Show what nexora-export should be
    print("\n=== CHECK TMP/nexora-export ===")
    print(run_sudo(ssh, "ls -la /tmp/nexora-export 2>&1 || echo 'MISSING'"))

    # 3 — Show /run/systemd/unit-root 
    print("\n=== /run/systemd/unit-root/tmp ===")
    print(run_sudo(ssh, "ls -la /run/systemd/unit-root/tmp/ 2>&1"))

    # 4 — Check PrivateTmp and namespace in unit
    print("\n=== GREP PrivateTmp/BindPaths/Namespace in unit ===")
    print(run_sudo(ssh, "grep -iE 'privatetmp|bindpath|namespace|tmpfs|nexora-export' /etc/systemd/system/nexora.service || echo 'none found'"))

    # 5 — Check if there is an override
    print("\n=== OVERRIDE DIR ===")
    print(run_sudo(ssh, "ls -la /etc/systemd/system/nexora.service.d/ 2>&1 || echo 'No override dir'"))

    # 6 — Full journal for nexora (last 30 lines)
    print("\n=== FULL JOURNAL (last 30) ===")
    print(run_sudo(ssh, "journalctl -u nexora.service -n 30 --no-pager"))

    ssh.close()


if __name__ == "__main__":
    main()
