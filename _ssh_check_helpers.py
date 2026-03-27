import paramiko

HOST = "192.168.1.52"
USER = "chonsrv1test"
PASS = "Leila112//!!&"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, 22, USER, PASS, timeout=20)
cmd = "echo 'Leila112//!!&' | sudo -S -i bash -lc \"source /usr/share/yunohost/helpers; declare -F | awk '{print \\\$3}' | grep '^ynh_.*systemd' || true\""
_, stdout, stderr = client.exec_command(cmd)
out = stdout.read().decode("utf-8", "replace")
err = stderr.read().decode("utf-8", "replace")
print(out)
print(err)
client.close()
