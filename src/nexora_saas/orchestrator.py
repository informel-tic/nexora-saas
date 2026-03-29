"""Application service orchestrating inventory, enrollment and fleet state.

NexoraService extends the lightweight NodeService from nexora_node_sdk
with fleet orchestration, enrollment issuance, governance, multi-tenant
isolation, and quota enforcement.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

# Shared modules from nexora_node_sdk
from nexora_node_sdk.compatibility import resolve_compatibility_matrix_path
from nexora_node_sdk.models import (
    DashboardSummary,
    FleetSummary,
    NodeRecord,
    TenantTier,
)
from nexora_node_sdk.node_service import NodeService
from nexora_node_sdk.security_audit import emit_security_event
from nexora_node_sdk.state import normalize_node_record, transition_node_status

# SaaS-only modules
from .adoption import build_adoption_report
from .enrollment import attest_node, consume_enrollment_token, issue_enrollment_token
from .feature_provisioning import (
    build_heartbeat_for_node,
    deprovision_node,
    get_node_provisioning_status,
    provision_node_features,
    resolve_features_for_tier,
)
from .node_lifecycle import apply_lifecycle_action, summarize_fleet_lifecycle
from .quotas import get_quota_limit, get_tenant_entitlements, is_quota_exceeded
from .subscription import (
    cancel_subscription,
    create_organization,
    create_subscription,
    get_organization,
    get_subscription,
    get_subscription_by_tenant,
    list_organizations,
    list_plans,
    list_subscriptions,
    reactivate_subscription,
    suspend_subscription,
    upgrade_subscription,
)

logger = logging.getLogger(__name__)


class NexoraService(NodeService):
    """Full SaaS control-plane service.

    Inherits local inventory, identity, compatibility, and caching from
    NodeService. Adds fleet orchestration, enrollment issuance, governance,
    multi-tenant isolation, and quota enforcement.
    """

    def persistence_status(self) -> dict[str, Any]:
        """Expose the active persistence backend used by the control plane."""

        description = self.state.describe()
        status = {
            "backend": description.get("backend"),
            "path": description.get("path"),
            "exists": description.get("exists"),
            "parent": description.get("parent"),
        }
        for key in (
            "backup_dir",
            "backup_count",
            "backup_retention",
            "journal_path",
            "journal_exists",
            "schema_version",
        ):
            if key in description:
                status[key] = description[key]
        if "dual_write" in description:
            status["dual_write"] = description["dual_write"]
        if hasattr(self.state, "backup_policy"):
            status["policy"] = self.state.backup_policy()
        if hasattr(self.state, "coherence_report"):
            status["coherence"] = self.state.coherence_report()
        return status

    def dashboard(self, tenant_id: str | None = None) -> DashboardSummary:
        node = self.local_node_summary()

        def _extract_tenant_domain_set() -> set[str]:
            state = self.state.load()
            domains: set[str] = set()
            for rec in state.get("nodes", []):
                if not isinstance(rec, dict):
                    continue
                if rec.get("tenant_id") != tenant_id:
                    continue
                for domain in rec.get("domains", []):
                    if isinstance(domain, str) and domain:
                        domains.add(domain)
            return domains

        def _tenant_filter_items(items: list[Any]) -> list[Any]:
            if not tenant_id:
                return list(items)
            tenant_domains = _extract_tenant_domain_set()
            if not tenant_domains:
                logger.warning(
                    "dashboard tenant filter requested but no tenant domains found",
                    extra={"tenant_id": tenant_id, "node_id": node.node_id},
                )
                return []
            filtered: list[Any] = []
            for item in items:
                if isinstance(item, dict):
                    text = " ".join(str(v).lower() for v in item.values() if isinstance(v, (str, int, float)))
                else:
                    text = str(item).lower()
                if any(domain.lower() in text for domain in tenant_domains):
                    filtered.append(item)
            return filtered

        tenant_scope_warning: str | None = None
        if tenant_id and node.tenant_id and node.tenant_id != tenant_id:
            tenant_scope_warning = (
                f"Local node tenant '{node.tenant_id}' differs from requested tenant '{tenant_id}'. "
                "Returning tenant-scoped dashboard subsets only."
            )

        apps_payload = self._fetch_section("apps")
        services_payload = self._fetch_section("services")
        certs_payload = self._fetch_section("certs")
        backups_payload = self._fetch_section("backups")

        apps = apps_payload.get("apps", []) if isinstance(apps_payload, dict) else []
        services_data = services_payload.get("services", {}) if isinstance(services_payload, dict) else {}
        certs_data = certs_payload.get("certificates", {}) if isinstance(certs_payload, dict) else {}
        backups_data = backups_payload.get("archives", []) if isinstance(backups_payload, dict) else []

        top_apps = _tenant_filter_items(list(apps))[:10]
        scoped_services = _tenant_filter_items(
            [{"name": k, **(v if isinstance(v, dict) else {"status": str(v)})} for k, v in services_data.items()]
        )[:15]
        scoped_certs = _tenant_filter_items(
            [{"domain": k, **(v if isinstance(v, dict) else {"value": str(v)})} for k, v in certs_data.items()]
        )[:15]
        normalized_backups = [
            entry if isinstance(entry, dict) else {"name": str(entry)} for entry in list(backups_data)
        ]
        scoped_backups = _tenant_filter_items(normalized_backups)[:10]

        alerts: list[str] = []
        if not scoped_backups:
            alerts.append("No backups found")
        if not scoped_certs:
            alerts.append("No certificate data found")
        if tenant_scope_warning:
            alerts.append(tenant_scope_warning)

        return DashboardSummary(
            node=node,
            top_apps=top_apps,
            alerts=alerts,
            services=scoped_services,
            certs=scoped_certs,
            backups=scoped_backups,
            raw={"tenant_id": tenant_id, "tenant_filter_applied": bool(tenant_id)},
        )

    def import_existing_state(self, domain: str | None = None, path: str | None = None) -> dict[str, Any]:
        self.invalidate_cache()
        inv = self.local_inventory()
        report = build_adoption_report(inv, domain, path)
        node_summary = self.local_node_summary().model_dump()
        state = self._ensure_identity_state(self.state.load(), enrolled_by="local-bootstrap")
        compatibility = self.compatibility_report()["assessment"]
        node_record = normalize_node_record(
            {
                **node_summary,
                "registered_at": datetime.now(timezone.utc).isoformat(),
                "credential_expires_at": state["identity"].get("expires_at"),
                "compatibility": compatibility,
            }
        )
        runtime_quota = self._validate_runtime_quota_for_node(
            state,
            tenant_id=node_record.get("tenant_id"),
            apps_count=node_record.get("apps_count", 0),
            storage_gb=node_record.get("storage_gb", 0),
        )
        if not runtime_quota.get("allowed", True):
            return {
                "imported": False,
                "idempotent": False,
                "error": runtime_quota.get("error", "runtime_quota_blocked"),
                "quota": runtime_quota,
                "report": report,
                "state_path": str(self.state.path),
            }
        node_record = transition_node_status(
            node_record, "healthy" if compatibility["bootstrap_allowed"] else "degraded"
        )
        state.setdefault("nodes", [])
        state["nodes"] = [n for n in state["nodes"] if n.get("node_id") != node_record["node_id"]] + [node_record]
        imports = state.setdefault("imports", [])
        import_payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "domain": domain,
            "path": path,
            "report": report,
            "mode": report.get("recommended_mode"),
            "node_id": node_record["node_id"],
        }
        duplicate_import = any(
            isinstance(entry, dict)
            and entry.get("node_id") == import_payload["node_id"]
            and entry.get("domain") == import_payload["domain"]
            and entry.get("path") == import_payload["path"]
            and entry.get("report") == import_payload["report"]
            for entry in imports
        )
        if not duplicate_import:
            imports.append(import_payload)

        snapshots = state.setdefault("inventory_snapshots", [])
        snapshot_payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "kind": "adoption-import",
            "inventory": inv,
            "tenant_id": node_record.get("tenant_id"),
        }
        duplicate_snapshot = any(
            isinstance(entry, dict) and entry.get("kind") == "adoption-import" and entry.get("inventory") == inv
            for entry in snapshots
        )
        if not duplicate_snapshot:
            snapshots.append(snapshot_payload)
        if node_record["node_id"] not in state["fleet"]["managed_nodes"]:
            state["fleet"]["managed_nodes"].append(node_record["node_id"])
        self.state.save(state)
        return {
            "imported": not duplicate_import,
            "idempotent": duplicate_import,
            "node": node_record,
            "report": report,
            "state_path": str(self.state.path),
        }

    def fleet_summary(self, tenant_id: str | None = None) -> FleetSummary:
        state = self._ensure_identity_state(self.state.load())
        local = self.local_node_summary()

        nodes_raw = state.get("nodes", [])
        if tenant_id:
            nodes_raw = [n for n in nodes_raw if n.get("tenant_id") == tenant_id]

        nodes = []
        if not tenant_id or local.tenant_id == tenant_id:
            nodes.append(local)

        for node in nodes_raw:
            if node.get("node_id") != local.node_id:
                try:
                    nodes.append(NodeRecord(**node))
                except Exception as exc:
                    logger.warning(
                        "invalid node record ignored in fleet_summary",
                        extra={"node_id": node.get("node_id"), "error": str(exc)},
                    )
        total_apps = sum(n.apps_count for n in nodes)
        total_domains = sum(n.domains_count for n in nodes)
        overall = int(sum(n.health_score for n in nodes) / len(nodes)) if nodes else 0
        return FleetSummary(
            nodes=nodes,
            total_nodes=len(nodes),
            total_apps=total_apps,
            total_domains=total_domains,
            overall_health_score=overall,
        )

    def request_enrollment_token(
        self,
        *,
        requested_by: str,
        mode: str,
        ttl_minutes: int = 30,
        node_id: str | None = None,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        """Create and persist a one-time enrollment token for a node."""

        state = self._ensure_identity_state(self.state.load())

        if tenant_id:
            subscription = get_subscription_by_tenant(state, tenant_id)
            tier = TenantTier.FREE.value

            if subscription:
                sub_status = str(subscription.get("status") or "active").strip().lower()
                tier = str(subscription.get("tier") or TenantTier.FREE.value)
                if sub_status in {"suspended", "cancelled", "expired"}:
                    return {
                        "success": False,
                        "error": f"Subscription for tenant '{tenant_id}' is '{sub_status}'. Enrollment blocked.",
                        "reason": f"subscription_{sub_status}",
                    }
            else:
                tenant_record = next(
                    (
                        tenant
                        for tenant in state.get("tenants", [])
                        if isinstance(tenant, dict) and tenant.get("tenant_id") == tenant_id
                    ),
                    {},
                )
                tier = str(tenant_record.get("tier") or TenantTier.FREE.value)

            tenant_nodes = [
                node
                for node in state.get("nodes", [])
                if isinstance(node, dict) and node.get("tenant_id") == tenant_id
            ]
            if is_quota_exceeded(tier, "max_nodes", len(tenant_nodes)):
                return {
                    "success": False,
                    "error": (
                        f"Quota exceeded for tenant '{tenant_id}': "
                        f"max_nodes limit reached ({len(tenant_nodes)}/{get_quota_limit(tier, 'max_nodes')})."
                    ),
                    "reason": "quota_max_nodes",
                }

        issued = issue_enrollment_token(
            state,
            requested_by=requested_by,
            mode=mode,
            ttl_minutes=ttl_minutes,
            node_id=node_id,
            tenant_id=tenant_id,
        )
        self.state.save(state)
        return {"success": True, **issued}

    def attest_enrollment(self, **payload: Any) -> dict[str, Any]:
        """Validate an enrollment attestation against compatibility policy."""

        state = self._ensure_identity_state(self.state.load())
        result = attest_node(
            state,
            compatibility_matrix_path=str(resolve_compatibility_matrix_path(self.repo_root)),
            **payload,
        )
        self.state.save(state)
        return result

    def register_enrolled_node(
        self,
        *,
        token: str,
        hostname: str,
        node_id: str,
        enrollment_mode: str,
        profile: str | None = None,
        roles: list[str] | None = None,
        apps_count: int = 0,
        storage_gb: int = 0,
    ) -> dict[str, Any]:
        """Finalize registration of a node whose token has been attested."""

        state = self._ensure_identity_state(self.state.load())
        token_record = consume_enrollment_token(state, token, node_id=node_id)

        existing = next(
            (node for node in state.get("nodes", []) if node.get("node_id") == node_id),
            {},
        )
        effective_apps_count = int(apps_count or existing.get("apps_count", 0) or 0)
        effective_storage_gb = int(storage_gb or existing.get("storage_gb", 0) or 0)

        tenant_id = token_record.get("tenant_id")
        if tenant_id:
            tenant_info = next(
                (t for t in state.get("tenants", []) if t.get("tenant_id") == tenant_id),
                {},
            )
            tier = tenant_info.get("tier", TenantTier.FREE)

            tenant_nodes = [n for n in state.get("nodes", []) if n.get("tenant_id") == tenant_id]
            if is_quota_exceeded(tier, "max_nodes", len(tenant_nodes)):
                return {
                    "registered": False,
                    "error": f"Quota exceeded for tier '{tier}'. Maximum nodes allowed: {get_quota_limit(tier, 'max_nodes')}",
                }
            runtime_quota = self._validate_runtime_quota_for_node(
                state,
                tenant_id=tenant_id,
                apps_count=effective_apps_count,
                storage_gb=effective_storage_gb,
            )
            if not runtime_quota.get("allowed", True):
                return {
                    "registered": False,
                    "error": runtime_quota.get("error", "runtime_quota_blocked"),
                    "quota": runtime_quota,
                }
        compatibility = self.compatibility_report()["assessment"]
        record = normalize_node_record(
            {
                **existing,
                "node_id": node_id,
                "hostname": hostname,
                "status": "attested",
                "enrollment_mode": enrollment_mode,
                "registered_at": datetime.now(timezone.utc).isoformat(),
                "status_updated_at": datetime.now(timezone.utc).isoformat(),
                "token_id": token_record.get("token_id"),
                "tenant_id": token_record.get("tenant_id"),
                "organization_id": next(
                    (
                        t.get("org_id")
                        for t in state.get("tenants", [])
                        if t.get("tenant_id") == token_record.get("tenant_id")
                    ),
                    None,
                ),
                "credential_expires_at": state.get("identity", {}).get("expires_at"),
                "compatibility": compatibility,
                "profile": profile,
                "roles": roles or existing.get("roles", []),
                "enrolled_by": token_record.get("requested_by"),
                "apps_count": effective_apps_count,
                "storage_gb": effective_storage_gb,
            }
        )
        record = transition_node_status(record, "registered")
        state["nodes"] = [node for node in state.get("nodes", []) if node.get("node_id") != node_id] + [record]
        state.setdefault("fleet", {}).setdefault("managed_nodes", [])
        if node_id not in state["fleet"]["managed_nodes"]:
            state["fleet"]["managed_nodes"].append(node_id)
        self.state.save(state)
        return {"registered": True, "node": record}

    def run_lifecycle_action(
        self, *, node_id: str, action: str, operator: str, confirmation: bool = False
    ) -> dict[str, Any]:
        """Apply a lifecycle action to a managed node."""

        state = self._ensure_identity_state(self.state.load())
        result = apply_lifecycle_action(
            state,
            node_id=node_id,
            action=action,
            operator=operator,
            confirmation=confirmation,
            certs_dir=str(self.state.path.parent / "certs"),
        )
        self.state.save(state)
        return result

    def fleet_lifecycle(self, tenant_id: str | None = None) -> dict[str, Any]:
        """Return the current fleet state, optionally filtered by tenant."""

        state = self.state.load()
        nodes = state.get("nodes", [])
        if tenant_id:
            nodes = [n for n in nodes if n.get("tenant_id") == tenant_id]

        return summarize_fleet_lifecycle(nodes)

    def _validate_runtime_quota_for_node(
        self,
        state: dict[str, Any],
        *,
        tenant_id: str | None,
        apps_count: int,
        storage_gb: int,
    ) -> dict[str, Any]:
        """Runtime quota guard for node-level app/storage metrics."""

        if not tenant_id:
            return {"allowed": True, "reason": "no-tenant-scope"}
        tenant_info = next(
            (
                tenant
                for tenant in state.get("tenants", [])
                if isinstance(tenant, dict) and tenant.get("tenant_id") == tenant_id
            ),
            {},
        )
        tier = tenant_info.get("tier", TenantTier.FREE)
        apps_limit = get_quota_limit(tier, "max_apps_per_node")
        storage_limit = get_quota_limit(tier, "max_storage_gb")
        apps_count = max(0, int(apps_count or 0))
        storage_gb = max(0, int(storage_gb or 0))

        if is_quota_exceeded(tier, "max_apps_per_node", apps_count):
            return {
                "allowed": False,
                "resource": "max_apps_per_node",
                "current": apps_count,
                "limit": apps_limit,
                "error": f"Quota exceeded for tenant '{tenant_id}': apps per node {apps_count}/{apps_limit}",
            }
        if is_quota_exceeded(tier, "max_storage_gb", storage_gb):
            return {
                "allowed": False,
                "resource": "max_storage_gb",
                "current": storage_gb,
                "limit": storage_limit,
                "error": f"Quota exceeded for tenant '{tenant_id}': storage {storage_gb}GB/{storage_limit}GB",
            }
        return {
            "allowed": True,
            "tier": str(tier),
            "max_apps_per_node": apps_limit,
            "max_storage_gb": storage_limit,
            "apps_count": apps_count,
            "storage_gb": storage_gb,
        }

    def tenant_usage_vs_quota(self, tenant_id: str | None = None) -> dict[str, Any]:
        """Expose canonical tenant usage versus quota limits."""

        state = self.state.load()
        tenants = [
            tenant for tenant in state.get("tenants", []) if isinstance(tenant, dict) and tenant.get("tenant_id")
        ]

        if tenant_id:
            tenants = [tenant for tenant in tenants if tenant.get("tenant_id") == tenant_id]
            if not tenants:
                return {
                    "tenant_id": tenant_id,
                    "error": f"Unknown tenant_id: {tenant_id}",
                    "usage": {},
                    "limits": {},
                    "exceeded": {},
                }

        def _coerce_int(value: Any) -> int:
            try:
                return int(value or 0)
            except (TypeError, ValueError):
                return 0

        reports: list[dict[str, Any]] = []
        nodes = [node for node in state.get("nodes", []) if isinstance(node, dict)]
        for tenant in tenants:
            current_tenant_id = str(tenant.get("tenant_id"))
            tier = str(tenant.get("tier") or TenantTier.FREE)
            tenant_nodes = [node for node in nodes if node.get("tenant_id") == current_tenant_id]

            nodes_count = len(tenant_nodes)
            apps_per_node = [_coerce_int(node.get("apps_count")) for node in tenant_nodes]
            apps_total = sum(apps_per_node)
            max_apps_on_single_node = max(apps_per_node) if apps_per_node else 0
            storage_used_gb = sum(_coerce_int(node.get("storage_gb")) for node in tenant_nodes)

            limits = {
                "max_nodes": get_quota_limit(tier, "max_nodes"),
                "max_apps_per_node": get_quota_limit(tier, "max_apps_per_node"),
                "max_storage_gb": get_quota_limit(tier, "max_storage_gb"),
            }
            usage = {
                "nodes_count": nodes_count,
                "apps_total": apps_total,
                "max_apps_on_single_node": max_apps_on_single_node,
                "storage_used_gb": storage_used_gb,
            }
            exceeded = {
                "max_nodes": is_quota_exceeded(tier, "max_nodes", nodes_count),
                "max_apps_per_node": is_quota_exceeded(tier, "max_apps_per_node", max_apps_on_single_node),
                "max_storage_gb": is_quota_exceeded(tier, "max_storage_gb", storage_used_gb),
            }

            reports.append(
                {
                    "tenant_id": current_tenant_id,
                    "organization_id": tenant.get("org_id"),
                    "tier": tier,
                    "subscription_status": (
                        (get_subscription_by_tenant(state, current_tenant_id) or {}).get("status")
                    ),
                    "entitlements": get_tenant_entitlements(tier),
                    "usage": usage,
                    "limits": limits,
                    "exceeded": exceeded,
                    "within_quota": not any(exceeded.values()),
                }
            )

        if tenant_id:
            return reports[0]
        return {"tenants": reports, "total_tenants": len(reports)}

    def adoption_report(self, domain: str | None = None, path: str | None = None) -> dict[str, Any]:
        return build_adoption_report(self.local_inventory(), domain, path)

    def purge_tenant_data(self, tenant_id: str) -> dict[str, Any]:
        """Securely purge all data related to a tenant (GDPR/Offboarding)."""
        state = self.state.load()

        tenant_nodes = [n for n in state.get("nodes", []) if n.get("tenant_id") == tenant_id]
        node_ids = [n.get("node_id") for n in tenant_nodes]

        from nexora_node_sdk.auth import SecretStore

        store = SecretStore(self.state.path.parent / "secrets")
        store.purge_tenant_secrets(tenant_id)

        state["nodes"] = [n for n in state.get("nodes", []) if n.get("tenant_id") != tenant_id]
        state["tenants"] = [t for t in state.get("tenants", []) if t.get("tenant_id") != tenant_id]

        if "security_audit" in state:
            state["security_audit"] = [e for e in state["security_audit"] if e.get("tenant_id") != tenant_id]

        if "enrollment_events" in state:
            state["enrollment_events"] = [e for e in state["enrollment_events"] if e.get("tenant_id") != tenant_id]

        if "fleet" in state and "managed_nodes" in state["fleet"]:
            state["fleet"]["managed_nodes"] = [nid for nid in state["fleet"]["managed_nodes"] if nid not in node_ids]

        self.state.save(state)
        self.invalidate_cache()

        return {
            "success": True,
            "tenant_id": tenant_id,
            "purged_nodes_count": len(node_ids),
            "message": f"Tenant {tenant_id} and all associated data have been purged successfully.",
        }

    def onboard_tenant(self, tenant_id: str, organization_id: str, tier: str = "free") -> dict[str, Any]:
        """Formalize tenant onboarding and environment separation."""
        state = self.state.load()
        state.setdefault("tenants", [])

        if any(t.get("tenant_id") == tenant_id for t in state["tenants"]):
            return {"success": False, "error": f"Tenant {tenant_id} already exists"}

        new_tenant = {
            "tenant_id": tenant_id,
            "org_id": organization_id,
            "tier": tier,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "active",
        }
        state["tenants"].append(new_tenant)
        emit_security_event(
            state,
            "audit",
            "tenant_onboarded",
            severity="info",
            tenant_id=tenant_id,
            organization_id=organization_id,
            tier=tier,
        )
        self.state.save(state)

        return {"success": True, "tenant": new_tenant}

    def list_tenants(self, organization_id: str | None = None) -> list[dict[str, Any]]:
        state = self.state.load()
        tenants = state.get("tenants", [])
        if organization_id:
            tenants = [t for t in tenants if t.get("org_id") == organization_id]
        return tenants

    # ------------------------------------------------------------------
    # Subscription management
    # ------------------------------------------------------------------

    def create_org(self, *, name: str, contact_email: str, billing_address: str = "") -> dict[str, Any]:
        state = self.state.load()
        result = create_organization(state, name=name, contact_email=contact_email, billing_address=billing_address)
        if result.get("success"):
            org = result.get("organization", {})
            emit_security_event(
                state,
                "audit",
                "organization_created",
                severity="info",
                organization_id=org.get("org_id"),
                organization_name=org.get("name"),
            )
            self.state.save(state)
        return result

    def list_orgs(self) -> list[dict[str, Any]]:
        return list_organizations(self.state.load())

    def get_org(self, org_id: str) -> dict[str, Any] | None:
        return get_organization(self.state.load(), org_id)

    def subscribe(self, *, org_id: str, plan_tier: str, tenant_label: str = "") -> dict[str, Any]:
        state = self.state.load()
        result = create_subscription(state, org_id=org_id, plan_tier=plan_tier, tenant_label=tenant_label)
        if result.get("success"):
            sub = result.get("subscription", {})
            emit_security_event(
                state,
                "audit",
                "subscription_created",
                severity="info",
                tenant_id=sub.get("tenant_id"),
                subscription_id=sub.get("subscription_id"),
                org_id=sub.get("org_id"),
                tier=sub.get("tier"),
            )
            self.state.save(state)
        return result

    def list_subs(self, org_id: str | None = None, tenant_id: str | None = None) -> list[dict[str, Any]]:
        return list_subscriptions(self.state.load(), org_id=org_id, tenant_id=tenant_id)

    def get_sub(self, subscription_id: str) -> dict[str, Any] | None:
        return get_subscription(self.state.load(), subscription_id)

    def suspend_sub(self, subscription_id: str, reason: str = "") -> dict[str, Any]:
        state = self.state.load()
        result = suspend_subscription(state, subscription_id, reason)
        if result.get("success"):
            sub = result.get("subscription", {})
            emit_security_event(
                state,
                "audit",
                "subscription_suspended",
                severity="warning",
                tenant_id=sub.get("tenant_id"),
                subscription_id=subscription_id,
                reason=reason,
            )
            self.state.save(state)
        return result

    def cancel_sub(self, subscription_id: str) -> dict[str, Any]:
        state = self.state.load()
        result = cancel_subscription(state, subscription_id)
        if result.get("success"):
            sub = result.get("subscription", {})
            emit_security_event(
                state,
                "audit",
                "subscription_cancelled",
                severity="warning",
                tenant_id=sub.get("tenant_id"),
                subscription_id=subscription_id,
            )
            self.state.save(state)
        return result

    def reactivate_sub(self, subscription_id: str) -> dict[str, Any]:
        state = self.state.load()
        result = reactivate_subscription(state, subscription_id)
        if result.get("success"):
            sub = result.get("subscription", {})
            emit_security_event(
                state,
                "audit",
                "subscription_reactivated",
                severity="info",
                tenant_id=sub.get("tenant_id"),
                subscription_id=subscription_id,
            )
            self.state.save(state)
        return result

    def upgrade_sub(self, subscription_id: str, new_tier: str) -> dict[str, Any]:
        state = self.state.load()
        result = upgrade_subscription(state, subscription_id, new_tier)
        if result.get("success"):
            sub = result.get("subscription", {})
            emit_security_event(
                state,
                "audit",
                "subscription_upgrade",
                severity="info",
                tenant_id=sub.get("tenant_id"),
                subscription_id=subscription_id,
                new_tier=new_tier,
                previous_tier=result.get("previous_tier"),
                downgrade=result.get("downgrade", False),
            )
            self.state.save(state)
        return result

    def get_plans(self) -> list[dict[str, Any]]:
        return list_plans()

    # ------------------------------------------------------------------
    # Feature provisioning — SaaS pushes features down to nodes
    # ------------------------------------------------------------------

    def provision_node(
        self,
        *,
        node_id: str,
        node_url: str,
        hmac_secret: str,
        api_token: str = "",
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        """Provision features on an enrolled node based on its tenant's subscription."""
        state = self.state.load()
        result = provision_node_features(
            state,
            node_id=node_id,
            node_url=node_url,
            hmac_secret=hmac_secret,
            api_token=api_token,
            tenant_id=tenant_id,
        )
        if result.get("success"):
            self.state.save(state)
        return result

    def deprovision_node_features(self, *, node_id: str, node_url: str, hmac_secret: str = "") -> dict[str, Any]:
        """Remove all features from a node (rollback)."""
        state = self.state.load()
        result = deprovision_node(state, node_id=node_id, node_url=node_url, hmac_secret=hmac_secret)
        if result.get("success"):
            self.state.save(state)
        return result

    def heartbeat_node(
        self,
        *,
        node_id: str,
        node_url: str,
        hmac_secret: str,
        api_token: str = "",
        lease_seconds: int = 86400,
    ) -> dict[str, Any]:
        """Send heartbeat to an enrolled node to keep feature leases alive."""
        state = self.state.load()
        return build_heartbeat_for_node(
            state,
            node_id=node_id,
            node_url=node_url,
            hmac_secret=hmac_secret,
            api_token=api_token,
            lease_seconds=lease_seconds,
        )

    def node_provisioning_status(self, node_id: str) -> dict[str, Any]:
        """Get provisioning history for a node."""
        return get_node_provisioning_status(self.state.load(), node_id)

    def resolve_node_features(self, node_id: str) -> dict[str, Any]:
        """Resolve the feature set for a node based on its tenant's subscription."""
        state = self.state.load()
        node = next((n for n in state.get("nodes", []) if n.get("node_id") == node_id), None)
        if not node:
            return {"error": f"Node '{node_id}' not found"}
        tenant_id = node.get("tenant_id")
        tier = "free"
        if tenant_id:
            sub = get_subscription_by_tenant(state, tenant_id)
            if sub:
                tier = sub.get("tier", "free")
            else:
                tenant = next((t for t in state.get("tenants", []) if t.get("tenant_id") == tenant_id), None)
                if tenant:
                    tier = tenant.get("tier", "free")
        features = resolve_features_for_tier(tier)
        return {
            "node_id": node_id,
            "tenant_id": tenant_id,
            "tier": tier,
            "features": [{"feature_id": f["feature_id"], "name": f["name"], "kind": f["kind"]} for f in features],
        }
