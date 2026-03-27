"""API request models for HTTP surfaces exposed by Nexora."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


EnrollmentMode = str


class EnrollmentTokenRequest(BaseModel):
    """Request body used to issue an enrollment token."""

    requested_by: str
    mode: EnrollmentMode
    ttl_minutes: int = 30
    node_id: Optional[str] = None


class EnrollmentAttestationRequest(BaseModel):
    """Request body used by a node to prove compatibility and freshness."""

    token: str
    challenge: str
    challenge_response: str
    hostname: str
    node_id: str
    agent_version: str
    yunohost_version: Optional[str] = None
    debian_version: Optional[str] = None
    observed_at: str


class EnrollmentRegisterRequest(BaseModel):
    """Request body used to finalize node registration after attestation."""

    token: str
    hostname: str
    node_id: str
    enrollment_mode: EnrollmentMode
    profile: Optional[str] = None
    roles: List[str] = Field(default_factory=list)
    apps_count: int = 0
    storage_gb: int = 0


class LifecycleActionRequest(BaseModel):
    """Request body for lifecycle commands exposed by the control plane."""

    operator: str
    confirmation: bool = False


__all__ = [
    "EnrollmentAttestationRequest",
    "EnrollmentMode",
    "EnrollmentRegisterRequest",
    "EnrollmentTokenRequest",
    "LifecycleActionRequest",
]