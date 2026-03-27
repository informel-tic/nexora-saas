"""Aide au scaffolding et à la validation de paquets YunoHost."""

from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from yunohost_mcp.utils.safety import validate_name, validate_output_path


def _write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def register_packaging_tools(mcp: FastMCP, settings=None):

    @mcp.tool()
    async def ynh_pkg_scaffold(package_name: str, output_dir: str) -> str:
        """Crée un squelette de package YunoHost.
        Args:
            package_name: Nom du package (alphanumérique)
            output_dir: Répertoire de sortie (redirigé si hors zone autorisée)
        """
        validate_name(package_name, "package name")
        safe_dir = validate_output_path(output_dir + f"/{package_name}_ynh/manifest.toml").parent
        base = safe_dir
        for rel in ["conf", "scripts", "doc"]:
            (base / rel).mkdir(parents=True, exist_ok=True)
        _write(
            base / "manifest.toml",
            f'packaging_format = 2\nid = "{package_name}"\nname = "{package_name}"\nversion = "0.1.0~ynh1"\n',
        )
        _write(base / "tests.toml", "test_format = 1\n")
        for script in ["install", "remove", "upgrade", "backup", "restore"]:
            _write(base / f"scripts/{script}", "#!/bin/bash\nset -eu\n")
        _write(
            base / "conf/nginx.conf",
            "location / { proxy_pass http://127.0.0.1:__PORT__/; }\n",
        )
        _write(
            base / "conf/systemd.service",
            "[Service]\nExecStart=__INSTALL_DIR__/venv/bin/python -m app\n",
        )
        return f"✅ Squelette créé dans {base}"

    @mcp.tool()
    async def ynh_pkg_manifest_generate(package_name: str, output_path: str) -> str:
        validate_name(package_name, "package name")
        safe_path = validate_output_path(output_path)
        content = f'''packaging_format = 2\nid = "{package_name}"\nname = "{package_name}"\nversion = "0.1.0~ynh1"\n\n[integration]\nyunohost = ">= 12.1"\nhelpers_version = "2.1"\narchitectures = "all"\nmulti_instance = false\nldap = "not_relevant"\nsso = "not_relevant"\n\n[install.domain]\ntype = "domain"\n\n[install.path]\ntype = "path"\ndefault = "/"\n'''
        _write(safe_path, content)
        return f"✅ Manifest généré: {safe_path}"

    @mcp.tool()
    async def ynh_pkg_tests_generate(output_path: str) -> str:
        safe_path = validate_output_path(output_path)
        _write(
            safe_path,
            "test_format = 1\n\n[default]\n\n[default.test_upgrade]\n\n[default.test_backup_restore]\n",
        )
        return f"✅ tests.toml généré: {safe_path}"

    @mcp.tool()
    async def ynh_pkg_validate_structure(package_dir: str) -> str:
        base = Path(package_dir)
        required = [
            base / "manifest.toml",
            base / "tests.toml",
            base / "conf",
            base / "scripts/install",
            base / "scripts/remove",
            base / "scripts/upgrade",
            base / "scripts/backup",
            base / "scripts/restore",
        ]
        missing = [str(p.relative_to(base)) for p in required if not p.exists()]
        return (
            "✅ Structure standard présente" if not missing else "❌ Structure incomplète:\n- " + "\n- ".join(missing)
        )

    @mcp.tool()
    async def ynh_pkg_validate_manifest(manifest_path: str) -> str:
        text = Path(manifest_path).read_text(encoding="utf-8")
        checks = {
            "packaging_format": "packaging_format" in text,
            "id": "\nid =" in text,
            "name": "\nname =" in text,
            "version": "\nversion =" in text,
            "integration": "[integration]" in text,
        }
        missing = [k for k, ok in checks.items() if not ok]
        return (
            "✅ Manifest cohérent (validation heuristique)"
            if not missing
            else "❌ Manifest incomplet: " + ", ".join(missing)
        )

    @mcp.tool()
    async def ynh_pkg_validate_scripts(package_dir: str) -> str:
        base = Path(package_dir) / "scripts"
        report = {}
        for name in ["install", "remove", "upgrade", "backup", "restore"]:
            path = base / name
            if not path.exists():
                report[name] = "missing"
                continue
            text = path.read_text(encoding="utf-8")
            report[name] = "ok" if "set -" in text else "warning:no-set-flags"
        return json.dumps(report, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_pkg_lint(package_dir: str) -> str:
        result = {
            "scripts": json.loads(await ynh_pkg_validate_scripts(package_dir)),
            "manifest": await ynh_pkg_validate_manifest(str(Path(package_dir) / "manifest.toml"))
            if (Path(package_dir) / "manifest.toml").exists()
            else "missing",
        }
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_pkg_detect_risky_patterns(package_dir: str) -> str:
        risky = []
        for path in Path(package_dir).rglob("*"):
            if path.is_file() and path.suffix in {"", ".sh", ".toml"}:
                text = path.read_text(encoding="utf-8", errors="replace")
                for pattern in [
                    "rm -rf /",
                    "chmod 777",
                    "curl | bash",
                    "systemctl disable firewall",
                ]:
                    if pattern in text:
                        risky.append({"file": str(path), "pattern": pattern})
        return "✅ Aucun pattern risqué détecté" if not risky else json.dumps(risky, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def ynh_pkg_release_checklist() -> str:
        return "\n".join(
            [
                "- manifest.toml v2 complet",
                "- scripts install/upgrade/remove/backup/restore présents",
                "- conf/nginx.conf et conf/systemd.service relus",
                "- permissions minimales",
                "- port interne non exposé",
                "- tests.toml prêt pour package_check",
                "- documentation admin et sécurité disponible",
                "- test install / upgrade / backup-restore / remove réalisé",
            ]
        )
