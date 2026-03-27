"""MCP tools for storage management."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP


def register_storage_tools(mcp: FastMCP, settings=None):

    @mcp.tool()
    async def ynh_storage_usage() -> str:
        """Affiche l'utilisation disque détaillée par point de montage."""
        from nexora_core.storage import disk_usage_detailed

        return json.dumps(disk_usage_detailed(), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_storage_top_consumers() -> str:
        """Identifie les plus gros consommateurs d'espace disque."""
        from nexora_core.storage import top_disk_consumers

        return json.dumps(top_disk_consumers(), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_storage_ynh_map() -> str:
        """Carte de l'utilisation stockage YunoHost (apps, backups, mail, système)."""
        from nexora_core.storage import yunohost_storage_map

        return json.dumps(yunohost_storage_map(), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_storage_policy(profile: str = "standard") -> str:
        """Génère une politique de stockage et quotas.
        Args:
            profile: Profil (minimal, standard, professional)
        """
        from nexora_core.storage import generate_storage_policy

        return json.dumps(generate_storage_policy(profile), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_storage_s3_backup_config(bucket: str, endpoint: str = "", access_key: str = "") -> str:
        """Génère une configuration de backup S3 (rclone + script).
        Args:
            bucket: Nom du bucket S3
            endpoint: Endpoint S3 (défaut: AWS)
            access_key: Clé d'accès
        """
        from nexora_core.storage import generate_s3_backup_config

        return json.dumps(
            generate_s3_backup_config(bucket, endpoint, access_key),
            indent=2,
            ensure_ascii=False,
        )

    @mcp.tool()
    async def ynh_storage_nfs_config(server: str, share: str, mount_point: str = "/mnt/nexora-nfs") -> str:
        """Génère une configuration de montage NFS partagé.
        Args:
            server: Adresse du serveur NFS
            share: Chemin du partage
            mount_point: Point de montage local
        """
        from nexora_core.storage import generate_nfs_mount_config

        return json.dumps(
            generate_nfs_mount_config(server, share, mount_point),
            indent=2,
            ensure_ascii=False,
        )
