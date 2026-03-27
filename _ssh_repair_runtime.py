import _ssh_deploy as deploy

commands = [
    "chown -R nexora-platform:nexora-platform /home/yunohost.app/nexora-platform",
    "chown -R nexora-platform:nexora-platform /var/www/nexora-platform",
    "systemctl restart nexora-platform",
    "systemctl status nexora-platform --no-pager 2>&1 | head -20",
    "curl -s http://127.0.0.1:38120/api/health 2>&1",
    "curl -sk https://srv1testrchon.ynh.fr/nexora/api/health 2>&1",
]
for cmd in commands:
    client = deploy.make_client()
    try:
        deploy.run(client, cmd, sudo=True, timeout=45)
    finally:
        client.close()
