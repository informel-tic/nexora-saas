"""Fix the corrupted token-roles JSON on the server, then redeploy."""
import paramiko, json

HOST = "192.168.1.125"
USER = "srv2rchon"
PASS = "Leila112//!!&"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASS, allow_agent=False, look_for_keys=False, timeout=15)


def sudo_exec(client, cmd):
    full = f"sudo -S bash -c '{cmd}'"
    stdin, stdout, stderr = client.exec_command(full, timeout=30)
    stdin.write(PASS + "\n")
    stdin.flush()
    try:
        stdin.channel.shutdown_write()
    except Exception:
        pass
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    out_lines = [l for l in out.split("\n") if not l.startswith("[sudo]") and "password" not in l.lower()[:30]]
    return "\n".join(out_lines), err


# 1. Read the actual API token
print("=== Reading API token ===")
out, _ = sudo_exec(client, "cat /home/yunohost.app/nexora/api-token")
token = out.strip()
print(f"Token: {token}")

# 2. Build the correct JSON
roles_data = {
    "tokens": [
        {"token": token, "actor_role": "admin"}
    ]
}
correct_json = json.dumps(roles_data, indent=2)
print(f"\n=== Writing correct roles JSON ===")
print(correct_json)

# 3. Write to /tmp via SFTP, then sudo mv
sftp = client.open_sftp()
with sftp.file("/tmp/api-token-roles.json", "w") as f:
    f.write(correct_json + "\n")
sftp.close()

print("\n=== Installing corrected file ===")
out, _ = sudo_exec(client, "cp /tmp/api-token-roles.json /etc/nexora/api-token-roles.json && chown root:nexora /etc/nexora/api-token-roles.json && chmod 0640 /etc/nexora/api-token-roles.json && echo INSTALLED")
print(out)

# 4. Verify
print("\n=== Verifying ===")
out, _ = sudo_exec(client, "cat /etc/nexora/api-token-roles.json")
print(out)

print("\n=== ls -la ===")
out, _ = sudo_exec(client, "ls -la /etc/nexora/api-token-roles.json")
print(out)

client.close()
print("\nDone.")
