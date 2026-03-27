# API Surface Reference

> Auto-generated overview of all Nexora capabilities and their surface coverage.
> WS5 — REST / MCP / Console Convergence

## Coverage Summary

| Metric | Value |
|--------|-------|
| Total capabilities | 17 |
| Full parity (REST + MCP + Console) | 9 |
| Partial coverage | 8 |
| Coverage score | ~52.9% |

---

## Capabilities by Domain

### Inventory

| Capability | Status | REST | MCP | Console |
|------------|--------|------|-----|---------|
| `inventory.observe` | implemented | `GET /api/inventory/local`, `GET /api/inventory/{section}`, `GET /api/dashboard` | `ynh_doc_generate_overview`, `ynh_doc_services_inventory`, `ynh_doc_apps_inventory`, `ynh_doc_domains_inventory` | dashboard, inventory views |

### Fleet

| Capability | Status | REST | MCP | Console |
|------------|--------|------|-----|---------|
| `fleet.enrollment` | implemented | `POST /api/fleet/enroll/request`, `POST /api/fleet/enroll/attest`, `POST /api/fleet/enroll/register` | `ynh_fleet_enrollment_request`, `ynh_fleet_enrollment_attest`, `ynh_fleet_enrollment_register`, `ynh_fleet_register_node` | fleet enrollment workflows |
| `fleet.lifecycle` | implemented | `GET /api/fleet/lifecycle`, `POST /api/fleet/nodes/{node_id}/drain`, `POST .../cordon`, `POST .../uncordon`, `POST .../revoke`, `POST .../retire`, `POST .../rotate-credentials`, `POST .../re-enroll`, `POST .../delete` | `ynh_fleet_status`, `ynh_fleet_lifecycle`, `ynh_fleet_lifecycle_action`, `ynh_fleet_fetch_remote`, `ynh_fleet_drift_remote` | fleet lifecycle views |

### Compatibility

| Capability | Status | REST | MCP | Console |
|------------|--------|------|-----|---------|
| `compatibility.policy` | implemented | `GET /api/fleet/compatibility` | `ynh_fleet_compatibility` | compatibility indicators |

### Governance

| Capability | Status | REST | MCP | Console |
|------------|--------|------|-----|---------|
| `governance.scoring` | implemented | `GET /api/scores`, `GET /api/governance/report` | `ynh_gov_all_scores`, `ynh_gov_security_score`, `ynh_gov_pra_score`, `ynh_gov_health_score`, `ynh_gov_compliance_score`, `ynh_gov_executive_report` | scores section, governance views |
| `governance.risks` | implemented | `GET /api/governance/risks` | `ynh_gov_risk_register`, `ynh_gov_change_log`, `ynh_gov_snapshot_diff` | governance section (risk register table + score card) |

### Modes

| Capability | Status | REST | MCP | Console |
|------------|--------|------|-----|---------|
| `mode.management` | implemented | `GET /api/mode`, `GET /api/mode/list`, `POST /api/mode/switch`, `POST /api/mode/escalate`, `GET /api/mode/escalations`, `GET /api/mode/confirmations`, `GET /api/admin/log` | `ynh_mode_current`, `ynh_mode_list`, `ynh_mode_switch`, `ynh_mode_escalate`, `ynh_mode_list_escalations`, `ynh_mode_pending_confirmations`, `ynh_mode_history` | modes section, mode switching UI, escalation management |

### Docker

| Capability | Status | REST | MCP | Console |
|------------|--------|------|-----|---------|
| `docker.management` | implemented | `GET /api/docker/status`, `GET /api/docker/containers`, `GET /api/docker/templates` | `ynh_docker_status`, `ynh_docker_list_containers`, `ynh_docker_container_stats`, `ynh_docker_container_logs`, `ynh_docker_list_templates`, `ynh_docker_generate_compose`, `ynh_docker_deploy_compose`, `ynh_docker_run`, `ynh_docker_stop`, `ynh_docker_start`, `ynh_docker_remove`, `ynh_docker_pull` | docker section (status cards, containers table, templates) |

### PRA

| Capability | Status | REST | MCP | Console |
|------------|--------|------|-----|---------|
| `pra.management` | implemented | `GET /api/pra` | `ynh_pra_check_readiness`, `ynh_pra_export_config`, `ynh_pra_full_backup`, `ynh_pra_generate_rebuild_script`, `ynh_pra_snapshot` | pra section, pra score and runbooks display |

### Security

| Capability | Status | REST | MCP | Console |
|------------|--------|------|-----|---------|
| `security.posture` | implemented | `GET /api/security/posture` | `ynh_security_audit`, `ynh_security_check_updates`, `ynh_security_fail2ban_status`, `ynh_security_fail2ban_ban`, `ynh_security_fail2ban_unban`, `ynh_security_open_ports`, `ynh_security_permissions_audit`, `ynh_security_recent_logins` | security section, security posture display |

### Branding

| Capability | Status | REST | MCP | Console | Node |
|------------|--------|------|-----|---------|------|
| `branding.apply` | implemented | `GET /api/branding`, `GET /api/portal/palettes`, `GET /api/portal/sectors` | `ynh_op_apply_branding`, `ynh_op_sync_branding_to_node`, `ynh_fleet_sync_branding`, `ynh_portal_apply_theme`, `ynh_portal_generate_theme`, `ynh_portal_generate_sector_theme`, `ynh_portal_list_palettes`, `ynh_portal_list_sectors` | blueprints section (branding preview) | `POST /branding/apply` |

### SLA

| Capability | Status | REST | MCP | Console |
|------------|--------|------|-----|---------|
| `sla.tracking` | implemented | `GET /api/sla/tiers` | `ynh_sla_list_tiers`, `ynh_sla_compute_uptime`, `ynh_sla_generate_policy`, `ynh_sla_history`, `ynh_sla_record_downtime`, `ynh_sla_report`, `ynh_sla_report_from_history` | sla-tracking section (tier cards with uptime %, RTO/RPO) |

### Notifications

| Capability | Status | REST | MCP | Console |
|------------|--------|------|-----|---------|
| `notifications.routing` | implemented | `GET /api/notifications/templates` | `ynh_notify_list_templates`, `ynh_notify_preview_alert`, `ynh_notify_generate_webhook`, `ynh_notify_generate_config`, `ynh_notify_send_webhook`, `ynh_notify_send_ntfy` | notifications section (template cards with level badges) |

### Storage

| Capability | Status | REST | MCP | Console |
|------------|--------|------|-----|---------|
| `storage.analysis` | implemented | `GET /api/storage/usage`, `GET /api/storage/ynh-map` | `ynh_storage_usage`, `ynh_storage_ynh_map`, `ynh_storage_top_consumers`, `ynh_storage_policy`, `ynh_storage_nfs_config`, `ynh_storage_s3_backup_config` | storage section (disk usage table, YunoHost storage map) |

### Hooks

| Capability | Status | REST | MCP | Console |
|------------|--------|------|-----|---------|
| `hooks.management` | implemented | `GET /api/hooks/events`, `GET /api/hooks/presets` | `ynh_hooks_list_events`, `ynh_hooks_list_presets`, `ynh_hooks_generate_config`, `ynh_hooks_generate_script`, `ynh_hooks_install_preset`, `ynh_hooks_install_script` | hooks section (events table, presets with badge list) |

### Adoption

| Capability | Status | REST | MCP | Console |
|------------|--------|------|-----|---------|
| `adoption.workflow` | implemented | `GET /api/adoption/report`, `POST /api/adoption/import` | -- (gap) | adoption section, adoption report and import UI |

### Automation

| Capability | Status | REST | MCP | Console |
|------------|--------|------|-----|---------|
| `automation.catalog` | implemented | `GET /api/automation/templates`, `GET /api/automation/checklists` | `ynh_auto_list_templates`, `ynh_auto_list_checklists`, `ynh_auto_generate_plan`, `ynh_auto_generate_crontab`, `ynh_auto_install_crontab`, `ynh_auto_get_checklist` | automation section |

### Node Runtime

| Capability | Status | REST | MCP | Console | Node |
|------------|--------|------|-----|---------|------|
| `node.actions` | partial | -- (gap) | `ynh_op_apply_branding`, `ynh_op_create_backup`, `ynh_op_backup_rotate`, `ynh_op_renew_cert`, `ynh_op_restart_service` | node actions panel | `POST /branding/apply`, `POST /permissions/sync`, `POST /inventory/refresh`, `POST /pra/snapshot`, `POST /maintenance/enable`, `POST /maintenance/disable`, `POST /docker/compose/apply`, `POST /healthcheck/run` |

### Console

| Capability | Status | REST | MCP | Console |
|------------|--------|------|-----|---------|
| `console.operator-ui` | partial | `GET /api/v1/docs`, `GET /api/dashboard`, `GET /api/fleet`, `GET /api/metrics` | -- (gap) | 16-view SPA: dashboard, fleet, security, PRA, governance, SLA, docker, storage, notifications, hooks, blueprints, automation, adoption, modes, services, domains |

---

## Coverage Matrix

| Capability | REST | MCP | Console |
|------------|:----:|:---:|:-------:|
| `inventory.observe` | Y | Y | Y |
| `fleet.enrollment` | Y | Y | Y |
| `fleet.lifecycle` | Y | Y | Y |
| `compatibility.policy` | Y | Y | Y |
| `governance.scoring` | Y | Y | Y |
| `governance.risks` | Y | Y | Y |
| `mode.management` | Y | Y | Y |
| `docker.management` | Y | Y | Y |
| `pra.management` | Y | Y | Y |
| `security.posture` | Y | Y | Y |
| `branding.apply` | Y | Y | Y |
| `sla.tracking` | Y | Y | Y |
| `notifications.routing` | Y | Y | Y |
| `storage.analysis` | Y | Y | Y |
| `hooks.management` | Y | Y | Y |
| `adoption.workflow` | Y | -- | Y |
| `automation.catalog` | Y | Y | Y |
| `node.actions` | -- | Y | Y |
| `console.operator-ui` | Y | -- | Y |

---

## Remaining Gaps (v2.1+ backlog)

1. **adoption.workflow** — Missing MCP tools for adoption report and import (tracked NEXT-30)
2. **node.actions** — Missing REST proxy routes on control-plane for node actions (tracked NEXT-31)
3. **console.operator-ui** — Missing MCP tools for console-specific queries (tracked NEXT-32)
4. **security.posture** — MCP has granular tools (fail2ban, ports, logins) without dedicated REST endpoints; currently only aggregated via `/api/security/posture`

**Closed in v2.1 sprint (2026-03-27):** governance.risks, docker.management, sla.tracking, notifications.routing, storage.analysis, hooks.management — all now have full console views.  `/api/metrics` Prometheus endpoint added.

---

## Interface Parity Surfaces

Detailed REST vs MCP parity definitions are maintained in `src/nexora_core/interface_parity.py` covering:

| Surface | Capabilities | REST entries | MCP entries | Gaps |
|---------|:------------:|:------------:|:-----------:|:----:|
| fleet-lifecycle | 8 | 13 | 8 | 0 |
| governance | 9 | 4 | 9 | 2 |
| mode-management | 7 | 7 | 7 | 0 |
| node-actions | 8 | 0 | 5 | 8 |
| security-audit | 8 | 1 | 8 | 7 |

---

## Operator-only Surface Matrix (Phase 10)

The following REST routes are explicitly reserved to operator actors (`X-Nexora-Actor-Role` in `operator/admin/architect`) and are denied to subscriber-facing actors when `NEXORA_OPERATOR_ONLY_ENFORCE=1`:

- `GET /api/persistence`
- `GET /api/interface-parity/fleet-lifecycle`
- `GET /api/docker/status`
- `GET /api/docker/containers`
- `GET /api/docker/templates`
- `GET /api/failover/strategies`
- `GET /api/storage/usage`
- `GET /api/storage/ynh-map`
- `GET /api/notifications/templates`
- `GET /api/sla/tiers`
- `GET /api/hooks/events`
- `GET /api/hooks/presets`
- `GET /api/automation/templates`
- `GET /api/automation/checklists`

Behavioral enforcement is covered in `tests/test_p8_behavioral.py` (`test_operator_only_surface_matrix_denies_subscriber_access`).

---

## Quick Endpoints Reference

### Control Plane Endpoints
- `GET /api/v1/health`, `dashboard`, `fleet`
- `GET /api/capabilities`
- `GET /api/persistence`
- `GET /api/interface-parity/fleet-lifecycle`
*Secondary Security*: `/api/security/updates`, `fail2ban/*`, `open-ports`, `permissions-audit`, `recent-logins`
- `POST /api/fleet/enroll/request`, `attest`, `register`
- `POST /api/fleet/nodes/{node_id}/drain|cordon|revoke|retire`

### Node Agent Endpoints
- `GET /health`, `identity`, `inventory`, `metrics`, `summary`
- `POST /enroll`, `attest`, `rotate-credentials`, `revoke`
- `POST /branding/apply`, `/permissions/sync`, `/inventory/refresh`, `/pra/snapshot`, `/maintenance/enable`, `/maintenance/disable`, `/docker/compose/apply`, `/healthcheck/run`

---

## MCP Tool Catalog (Summary)

- **Capacités** : 194 outils exposés via MCP après filtrage de politique.
- **Domaines couverts** : fleet, inventory, security, pra, docker, storage, sla, notifications, automation, governance, blueprints, portal, etc.
- **Usage IA** : Les outils MCP sont des adaptateurs directs des services métier canoniques (REST parity).

---

