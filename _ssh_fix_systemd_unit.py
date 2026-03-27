import _ssh_deploy as deploy

commands = [
    "sed -i 's/^ProtectHome=true$/ProtectHome=false/' /etc/systemd/system/nexora-platform.service",
    "systemctl daemon-reload",
    "systemctl restart nexora-platform",
    "curl -s http://127.0.0.1:38120/api/health",
    "systemctl status nexora-platform --no-pager | head -20",
]

client = deploy.make_client()
for cmd in commands:
    deploy.run(client, cmd, sudo=True, timeout=45)
client.close()
