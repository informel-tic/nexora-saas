"""MCP tools for Docker container management."""

from __future__ import annotations

import json
from mcp.server.fastmcp import FastMCP
from yunohost_mcp.utils.safety import validate_name, validate_positive_int


def register_docker_tools(mcp: FastMCP, settings=None):

    @mcp.tool()
    async def ynh_docker_status() -> str:
        """Vérifie si Docker est installé et affiche les infos système Docker."""
        from nexora_core.docker import docker_info

        return json.dumps(docker_info(), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_docker_list_containers(show_all: bool = False) -> str:
        """Liste les conteneurs Docker en cours d'exécution.
        Args:
            show_all: Afficher aussi les conteneurs arrêtés
        """
        from nexora_core.docker import list_containers

        return json.dumps(list_containers(show_all), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_docker_container_stats() -> str:
        """Affiche les statistiques CPU/mémoire de chaque conteneur."""
        from nexora_core.docker import container_stats

        return json.dumps(container_stats(), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_docker_container_logs(name: str, lines: int = 50) -> str:
        """Affiche les logs d'un conteneur Docker.
        Args:
            name: Nom du conteneur
            lines: Nombre de lignes (défaut: 50)
        """
        validate_name(name, "container name")
        lines = validate_positive_int(int(lines), "lines", 500)
        from nexora_core.docker import container_logs

        return container_logs(name, lines)

    @mcp.tool()
    async def ynh_docker_list_templates() -> str:
        """Liste les templates Docker prêts à l'emploi (Redis, PostgreSQL, Minio, etc.)."""
        from nexora_core.docker import list_docker_templates

        return json.dumps(list_docker_templates(), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_docker_generate_compose(services: str) -> str:
        """Génère un fichier docker-compose.yml à partir d'une liste de services.
        Args:
            services: JSON array de services [{name, image, ports, volumes, environment}]
        """
        from nexora_core.docker import generate_compose_file

        try:
            svc_list = json.loads(services)
        except json.JSONDecodeError:
            return "❌ Format JSON invalide."
        return generate_compose_file(svc_list)

    @mcp.tool()
    async def ynh_docker_generate_compose_from_templates(template_names: str) -> str:
        """Génère un docker-compose.yml à partir de noms de templates.
        Args:
            template_names: Noms de templates séparés par des virgules (ex: redis,postgres,grafana)
        """
        from nexora_core.docker import get_docker_template, generate_compose_file

        names = [n.strip() for n in template_names.split(",")]
        services = []
        for name in names:
            tpl = get_docker_template(name)
            if tpl:
                services.append({"name": name, **tpl})
            else:
                return f"❌ Template '{name}' non trouvé."
        return generate_compose_file(services)

    @mcp.tool()
    async def ynh_docker_generate_nginx_proxy(
        container_name: str, domain: str, internal_port: int, path: str = "/"
    ) -> str:
        """Génère une config nginx reverse proxy pour un conteneur Docker.
        Args:
            container_name: Nom du conteneur
            domain: Domaine frontal
            internal_port: Port interne du conteneur
            path: Chemin URL (défaut: /)
        """
        from nexora_core.docker import generate_nginx_proxy_for_container

        return generate_nginx_proxy_for_container(
            container_name, domain, internal_port, path=path
        )

    @mcp.tool()
    async def ynh_docker_estimate_resources(services: str) -> str:
        """Estime les ressources nécessaires pour un ensemble de services Docker.
        Args:
            services: Noms de templates séparés par des virgules
        """
        from nexora_core.docker import estimate_docker_resources

        names = [n.strip() for n in services.split(",")]
        return json.dumps(
            estimate_docker_resources(names), indent=2, ensure_ascii=False
        )

    @mcp.tool()
    async def ynh_docker_pull(image: str) -> str:
        """[OPERATOR] Télécharge une image Docker.
        Args:
            image: Image à télécharger (ex: redis:7-alpine)
        """
        from nexora_core.docker import docker_pull

        return json.dumps(docker_pull(image), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_docker_run(
        image: str, name: str, ports: str = "", environment: str = ""
    ) -> str:
        """[OPERATOR] Lance un conteneur Docker.
        Args:
            image: Image Docker
            name: Nom du conteneur
            ports: Ports (ex: 127.0.0.1:6379:6379,127.0.0.1:8080:80)
            environment: Variables (ex: KEY=val,KEY2=val2)
        """
        validate_name(name, "container name")
        from nexora_core.docker import docker_run

        port_list = [p.strip() for p in ports.split(",") if p.strip()] if ports else []
        env_dict = (
            dict(kv.split("=", 1) for kv in environment.split(",") if "=" in kv)
            if environment
            else {}
        )
        return json.dumps(
            docker_run(image, name, ports=port_list, environment=env_dict),
            indent=2,
            ensure_ascii=False,
        )

    @mcp.tool()
    async def ynh_docker_start(name: str) -> str:
        """[OPERATOR] Démarre un conteneur arrêté.
        Args:
            name: Nom du conteneur
        """
        validate_name(name, "container name")
        from nexora_core.docker import docker_start

        return json.dumps(docker_start(name), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_docker_stop(name: str) -> str:
        """[OPERATOR] Arrête un conteneur.
        Args:
            name: Nom du conteneur
        """
        validate_name(name, "container name")
        from nexora_core.docker import docker_stop

        return json.dumps(docker_stop(name), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_docker_remove(name: str, force: bool = False) -> str:
        """[ADMIN] Supprime un conteneur.
        Args:
            name: Nom du conteneur
            force: Forcer la suppression (si en cours)
        """
        validate_name(name, "container name")
        from nexora_core.docker import docker_remove

        return json.dumps(docker_remove(name, force), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_docker_deploy_compose(services: str) -> str:
        """[OPERATOR] Génère un docker-compose.yml et lance docker compose up.
        Args:
            services: Noms de templates séparés par virgules (ex: redis,postgres)
        """
        from nexora_core.docker import (
            get_docker_template,
            generate_compose_file,
            write_compose_file,
            docker_compose_up,
        )

        names = [n.strip() for n in services.split(",")]
        svc_list = []
        for n in names:
            tpl = get_docker_template(n)
            if not tpl:
                return f"❌ Template '{n}' non trouvé."
            svc_list.append({"name": n, **tpl})
        content = generate_compose_file(svc_list)
        written = write_compose_file(content)
        result = docker_compose_up(written["written"])
        return json.dumps(
            {"compose": written, "deploy": result}, indent=2, ensure_ascii=False
        )

    @mcp.tool()
    async def ynh_docker_compose_down() -> str:
        """[ADMIN] Arrête et supprime les conteneurs du docker-compose Nexora."""
        from nexora_core.docker import docker_compose_down

        return json.dumps(
            docker_compose_down("/opt/nexora/docker/docker-compose.yml"),
            indent=2,
            ensure_ascii=False,
        )
