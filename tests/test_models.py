import pytest
from pydantic import ValidationError

from nexora_node_sdk import models


def test_tenant_defaults():
    t = models.Tenant(tenant_id="t1", org_id="o1", name="Tenant", created_at="now")
    assert t.tier == models.TenantTier.FREE
    assert t.max_nodes == 5


def test_enrollment_token_ttl_validation():
    with pytest.raises(ValidationError):
        models.EnrollmentTokenRequest(requested_by="u", mode="push", ttl_minutes=0)


def test_node_summary_and_record_defaults():
    ns = models.NodeSummary(node_id="n1", hostname="host1")
    assert ns.status == "discovered"
    assert ns.apps_count == 0
    assert isinstance(ns.roles, list)

    nr = models.NodeRecord(node_id="n2", hostname="host2")
    assert nr.compatibility == {}


def test_adoption_report_defaults():
    ar = models.AdoptionReport(recommended_mode="push")
    assert ar.safe_to_install is True
    assert isinstance(ar.notes, list)


def test_enrollment_token_request_valid():
    req = models.EnrollmentTokenRequest(requested_by="u", mode="push", ttl_minutes=30)
    assert req.ttl_minutes == 30


def test_enrollment_token_request_invalid_ttl():
    try:
        models.EnrollmentTokenRequest(requested_by="u", mode="push", ttl_minutes=0)
        assert False, "Validation should have failed for ttl_minutes=0"
    except ValidationError:
        pass


def test_node_summary_defaults():
    ns = models.NodeSummary(node_id="n1", hostname="h1")
    assert ns.node_id == "n1"
    assert ns.hostname == "h1"
    assert isinstance(ns.allowed_transitions, list)
