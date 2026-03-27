"""Integration tests for Workstream 9: Multi-tenancy and SaaS Readiness."""

import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import pytest
from nexora_saas.orchestrator import NexoraService
from nexora_node_sdk.models import NodeSummary
from nexora_saas.enrollment import build_attestation_response
from nexora_node_sdk.version import NEXORA_VERSION

@pytest.fixture
def service():
    temp_dir = tempfile.mkdtemp()
    state_path = Path(temp_dir) / "state.json"
    service = NexoraService(state_path=str(state_path), repo_root=temp_dir)
    yield service
    shutil.rmtree(temp_dir)

def test_tenant_onboarding_and_isolation(service):
    # 1. Onboard two tenants
    service.onboard_tenant("tenant-a", "org-1", tier="pro")
    service.onboard_tenant("tenant-b", "org-1", tier="free")
    
    tenants = service.list_tenants()
    assert len(tenants) == 2
    assert any(t["tenant_id"] == "tenant-a" for t in tenants)
    
    # 2. Verify quota enforcement (Mock node registration for simplicity in this integration test)
    # Since we can't easily run full enrollment in a unit test without mocks, 
    # we verify the quota calculation logic.
    from nexora_saas.quotas import is_quota_exceeded, get_quota_limit
    
    assert get_quota_limit("free", "max_nodes") == 5
    assert get_quota_limit("pro", "max_nodes") == 50
    
    assert is_quota_exceeded("free", "max_nodes", 5) is True
    assert is_quota_exceeded("free", "max_nodes", 4) is False

def test_data_purging(service):
    # 1. Setup tenant and data
    service.onboard_tenant("tenant-purge", "org-purge", tier="free")
    # Add a mock node for this tenant in state
    state = service.state.load()
    state.setdefault("nodes", []).append({
        "node_id": "node-to-purge",
        "tenant_id": "tenant-purge",
        "hostname": "test-node"
    })
    service.state.save(state)
    
    # 2. Purge data
    result = service.purge_tenant_data("tenant-purge")
    assert result["success"] is True
    assert result["purged_nodes_count"] == 1
    
    # 3. Verify state is clean
    new_state = service.state.load()
    assert not any(n["tenant_id"] == "tenant-purge" for n in new_state.get("nodes", []))
    assert not any(t["tenant_id"] == "tenant-purge" for t in new_state.get("tenants", []))

def test_api_tenant_header_safety():
    temp_dir = tempfile.mkdtemp()
    try:
        state_path = Path(temp_dir) / "state.json"
        service = NexoraService(state_path=str(state_path), repo_root=temp_dir)

        # Create 2 tenants and one remote node for tenant-a
        service.onboard_tenant("tenant-a", "org-1", tier="pro")
        service.onboard_tenant("tenant-b", "org-1", tier="free")

        state = service.state.load()
        state.setdefault("nodes", []).append(
            {
                "node_id": "remote-tenant-a-1",
                "hostname": "tenant-a-node-1",
                "tenant_id": "tenant-a",
                "domains_count": 2,
                "apps_count": 3,
                "health_score": 90,
                "status": "healthy",
                "domains": ["a.example.org", "shop.a.example.org"],
            }
        )
        service.state.save(state)

        # Simulate control-plane tenant scoping behavior used by header-based filtering:
        # when tenant_id is provided, returned topology must only include this tenant.
        with patch.object(
            service,
            "local_node_summary",
            return_value=NodeSummary(
                node_id="local-node",
                hostname="local-node",
                status="healthy",
                tenant_id=None,
                apps_count=1,
                domains_count=1,
                health_score=80,
            ),
        ):
            fleet_tenant_a = service.fleet_summary(tenant_id="tenant-a").model_dump()
        assert all(node.get("tenant_id") in ("tenant-a", None) for node in fleet_tenant_a["nodes"])
        assert any(node.get("tenant_id") == "tenant-a" for node in fleet_tenant_a["nodes"])

        with patch.object(
            service,
            "local_node_summary",
            return_value=NodeSummary(
                node_id="local-node",
                hostname="local-node",
                status="healthy",
                tenant_id=None,
                apps_count=1,
                domains_count=1,
                health_score=80,
            ),
        ):
            fleet_tenant_b = service.fleet_summary(tenant_id="tenant-b").model_dump()
        assert all(node.get("tenant_id") in ("tenant-b", None) for node in fleet_tenant_b["nodes"])
        # tenant-b has no dedicated remote node in this setup
        assert not any(node.get("tenant_id") == "tenant-a" for node in fleet_tenant_b["nodes"])
    finally:
        shutil.rmtree(temp_dir)


def test_dashboard_tenant_scope_warning_and_filtering():
    temp_dir = tempfile.mkdtemp()
    try:
        state_path = Path(temp_dir) / "state.json"
        service = NexoraService(state_path=str(state_path), repo_root=temp_dir)

        service.onboard_tenant("tenant-a", "org-1", tier="pro")
        state = service.state.load()
        state.setdefault("nodes", []).append(
            {
                "node_id": "remote-tenant-a",
                "tenant_id": "tenant-a",
                "hostname": "tenant-a.example.org",
                "domains": ["tenant-a.example.org"],
            }
        )
        service.state.save(state)

        fake_node = NodeSummary(
            node_id="local-node",
            hostname="local-node",
            status="healthy",
            tenant_id="tenant-b",
            apps_count=1,
            domains_count=1,
            health_score=80,
        )
        with patch.object(service, "local_node_summary", return_value=fake_node), patch.object(
            service, "_fetch_section"
        ) as fetch:
            fetch.side_effect = lambda section: {
                "apps": {"apps": [{"name": "portal", "domain": "tenant-a.example.org"}]},
                "services": {"services": {"nginx": {"status": "running", "domain": "tenant-a.example.org"}}},
                "certs": {"certificates": {"tenant-a.example.org": {"style": "ok"}}},
                "backups": {"archives": ["backup-tenant-a.example.org"]},
            }.get(section, {})
            dashboard = service.dashboard(tenant_id="tenant-a").model_dump()
        assert dashboard["raw"]["tenant_filter_applied"] is True
        assert dashboard["raw"]["tenant_id"] == "tenant-a"
        assert any("differs from requested tenant" in msg for msg in dashboard["alerts"])
    finally:
        shutil.rmtree(temp_dir)


def test_register_enrolled_node_enforces_apps_and_storage_quota(service):
    service.onboard_tenant("tenant-free", "org-1", tier="free")
    issued = service.request_enrollment_token(
        requested_by="qa",
        mode="pull",
        ttl_minutes=30,
        node_id="node-free-1",
        tenant_id="tenant-free",
    )
    service.attest_enrollment(
        token=issued["token"],
        challenge=issued["challenge"],
        challenge_response=build_attestation_response(
            challenge=issued["challenge"],
            node_id="node-free-1",
            token_id=issued["token_id"],
        ),
        hostname="node-free-1.local",
        node_id="node-free-1",
        agent_version=NEXORA_VERSION,
        yunohost_version="12.1.2",
        debian_version="12",
        observed_at=datetime.now(timezone.utc).isoformat(),
    )
    result = service.register_enrolled_node(
        token=issued["token"],
        hostname="node-free-1.local",
        node_id="node-free-1",
        enrollment_mode="pull",
        apps_count=12,
        storage_gb=5,
    )
    assert result["registered"] is False
    assert "apps per node" in result["error"]


def test_register_enrolled_node_reenrollment_uses_effective_metrics_for_quota(service):
    service.onboard_tenant("tenant-free", "org-1", tier="free")
    state = service.state.load()
    state.setdefault("nodes", []).append(
        {
            "node_id": "node-free-existing",
            "tenant_id": "tenant-free",
            "apps_count": 12,
            "storage_gb": 5,
            "status": "healthy",
        }
    )
    service.state.save(state)

    issued = service.request_enrollment_token(
        requested_by="qa",
        mode="pull",
        ttl_minutes=30,
        node_id="node-free-existing",
        tenant_id="tenant-free",
    )
    service.attest_enrollment(
        token=issued["token"],
        challenge=issued["challenge"],
        challenge_response=build_attestation_response(
            challenge=issued["challenge"],
            node_id="node-free-existing",
            token_id=issued["token_id"],
        ),
        hostname="node-free-existing.local",
        node_id="node-free-existing",
        agent_version=NEXORA_VERSION,
        yunohost_version="12.1.2",
        debian_version="12",
        observed_at=datetime.now(timezone.utc).isoformat(),
    )
    result = service.register_enrolled_node(
        token=issued["token"],
        hostname="node-free-existing.local",
        node_id="node-free-existing",
        enrollment_mode="pull",
        apps_count=0,
        storage_gb=0,
    )
    assert result["registered"] is False
    assert "apps per node" in result["error"]


def test_usage_vs_quota_reports_exceeded_dimensions(service):
    service.onboard_tenant("tenant-free", "org-1", tier="free")
    state = service.state.load()
    state.setdefault("nodes", []).append(
        {
            "node_id": "node-over",
            "tenant_id": "tenant-free",
            "apps_count": 12,
            "storage_gb": 11,
            "status": "healthy",
        }
    )
    service.state.save(state)

    report = service.tenant_usage_vs_quota("tenant-free")
    assert report["tenant_id"] == "tenant-free"
    assert report["exceeded"]["max_apps_per_node"] is True
    assert report["exceeded"]["max_storage_gb"] is True
