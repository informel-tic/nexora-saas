import _ssh_deploy as deploy

REMOTE_CMD = "grep -RniE 'ynh_.*(systemd|nginx|service)' /usr/share/yunohost 2>/dev/null | sed -n '1,160p'"

client = deploy.make_client()
deploy.run(client, REMOTE_CMD, sudo=True, timeout=30)
client.close()
