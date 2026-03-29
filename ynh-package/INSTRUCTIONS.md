# ynh-package — YunoHost Package

## Purpose

Standard YunoHost packaging format v2 package for deploying Nexora on YunoHost instances. Contains install/remove/upgrade/backup/restore hooks, nginx/systemd configuration templates, and the app manifest.

## Entry Point

- `manifest.toml` — YunoHost app manifest (packaging format v2, helpers v2.1).

## Structure

| Path | Purpose |
|------|---------|
| `manifest.toml` | App metadata, resource requirements (amd64/arm64, port 38120, YNH ≥ 12.1) |
| `conf/nginx.conf` | Nginx configuration template |
| `conf/systemd.service` | Systemd service template |
| `scripts/install` | YNH install hook |
| `scripts/remove` | YNH remove hook |
| `scripts/upgrade` | YNH upgrade hook |
| `scripts/backup` | YNH backup hook |
| `scripts/restore` | YNH restore hook |
| `scripts/_common.sh` | Shared helpers sourced by all hooks |

## Conventions

- **Packaging format**: v2 (`packaging_format = 2`).
- **Helpers version**: 2.1.
- **License**: AGPL-3.0-or-later.
- **Default port**: 38120.
- **Architectures**: amd64, arm64.
- **Min YunoHost**: 12.1.
- Install/upgrade hooks enforce operator-role lock file at `/etc/nexora/api-token-roles.json`.
- Service templates set `NEXORA_OPERATOR_ONLY_ENFORCE=1` and `NEXORA_API_TOKEN_ROLE_FILE`.

## Testing

Package structure is validated by `tests/test_packaging.py`.
