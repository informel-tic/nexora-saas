"""Bootstrap orchestration service and CLI for Nexora."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .compatibility import (
    assess_compatibility,
    load_compatibility_matrix,
    resolve_compatibility_matrix_path,
)
from .orchestrator import NexoraService
from .state import normalize_node_record, transition_node_status
from .version import NEXORA_VERSION

SUPPORTED_PROFILES = {"control-plane", "node-agent-only", "control-plane+node-agent"}
SUPPORTED_ENROLLMENT_MODES = {"push", "pull"}
SUPPORTED_MODES = {"fresh", "adopt", "augment"}
PACKAGE_LIFECYCLE_CAPABILITIES = {
    "install": "install_app",
    "upgrade": "upgrade_app",
    "restore": "upgrade_app",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _error_contract(
    code: str,
    message: str,
    *,
    retryable: bool,
    rollback_hint: str,
    retry_delay_seconds: int = 0,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "retryable": retryable,
            "retry_delay_seconds": retry_delay_seconds,
            "rollback_hint": rollback_hint,
            "details": details or {},
        },
    }


def _success_contract(action: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": True,
        "action": action,
        "timestamp": _utc_now(),
        **payload,
    }


@dataclass(slots=True)
class BootstrapOrchestrator:
    """Canonical bootstrap orchestration facade consumed by shell scripts."""

    service: NexoraService

    def _validate_inputs(
        self,
        *,
        profile: str,
        enrollment_mode: str,
        mode: str,
        domain: str | None = None,
    ) -> dict[str, Any] | None:
        if profile not in SUPPORTED_PROFILES:
            return _error_contract(
                "unsupported_profile",
                f"Unsupported PROFILE={profile}",
                retryable=False,
                rollback_hint="Use one of control-plane, node-agent-only, control-plane+node-agent.",
            )
        if enrollment_mode not in SUPPORTED_ENROLLMENT_MODES:
            return _error_contract(
                "unsupported_enrollment_mode",
                f"Unsupported ENROLLMENT_MODE={enrollment_mode}",
                retryable=False,
                rollback_hint="Use push or pull.",
            )
        if mode not in SUPPORTED_MODES:
            return _error_contract(
                "unsupported_mode",
                f"Unsupported MODE={mode}",
                retryable=False,
                rollback_hint="Use fresh, adopt or augment.",
            )
        return None

    def assess_target(
        self,
        *,
        profile: str,
        enrollment_mode: str,
        mode: str,
        yunohost_version: str,
        target_host: str,
        domain: str | None = None,
        path_url: str | None = None,
    ) -> dict[str, Any]:
        invalid = self._validate_inputs(
            profile=profile,
            enrollment_mode=enrollment_mode,
            mode=mode,
            domain=domain,
        )
        if invalid:
            return invalid
        matrix_path = resolve_compatibility_matrix_path(self.service.repo_root)
        matrix = load_compatibility_matrix(
            matrix_path if matrix_path.exists() else None
        )
        compatibility = assess_compatibility(
            NEXORA_VERSION, yunohost_version, matrix=matrix
        )
        if not compatibility.get("bootstrap_allowed"):
            return _error_contract(
                "bootstrap_blocked_by_compatibility",
                "Bootstrap aborted because the YunoHost version is not compatible with this Nexora baseline.",
                retryable=False,
                rollback_hint="Upgrade/downgrade YunoHost or use a Nexora version compatible with this node.",
                details={
                    "compatibility": compatibility,
                    "profile": profile,
                    "enrollment_mode": enrollment_mode,
                    "mode": mode,
                    "target_host": target_host,
                    "domain": domain,
                    "path_url": path_url,
                },
            )
        return _success_contract(
            "assess-target",
            {
                "profile": profile,
                "enrollment_mode": enrollment_mode,
                "mode": mode,
                "target_host": target_host,
                "domain": domain or None,
                "path_url": path_url or None,
                "compatibility": compatibility,
            },
        )

    def bootstrap_local_node(
        self,
        *,
        profile: str,
        enrollment_mode: str,
        mode: str,
        yunohost_version: str,
        target_host: str,
        domain: str | None = None,
        path_url: str | None = None,
        enrolled_by: str = "bootstrap-node.sh",
    ) -> dict[str, Any]:
        assessment = self.assess_target(
            profile=profile,
            enrollment_mode=enrollment_mode,
            mode=mode,
            yunohost_version=yunohost_version,
            target_host=target_host,
            domain=domain,
            path_url=path_url,
        )
        if not assessment.get("success"):
            return assessment

        state = self.service.state.load()
        identity = self.service.identity()
        node = normalize_node_record(
            {
                "node_id": identity["node_id"],
                "hostname": target_host,
                "status": "bootstrap_pending",
                "enrollment_mode": enrollment_mode,
                "enrolled_by": enrolled_by,
                "token_id": identity.get("token_id"),
                "agent_version": NEXORA_VERSION,
                "ynh_version": yunohost_version,
                "yunohost_version": yunohost_version,
                "debian_version": "12",
                "last_seen": None,
                "last_inventory_at": None,
                "profile": profile,
                "domain": domain or None,
                "path": path_url or None,
                "compatibility": assessment["compatibility"],
            }
        )
        transitions = ["agent_installed", "attested", "registered"]
        for target in transitions:
            node = transition_node_status(node, target)
        state["nodes"] = [
            n for n in state.get("nodes", []) if n.get("node_id") != node["node_id"]
        ] + [node]
        state.setdefault("fleet", {}).setdefault("managed_nodes", [])
        if node["node_id"] not in state["fleet"]["managed_nodes"]:
            state["fleet"]["managed_nodes"].append(node["node_id"])
        state.setdefault("bootstrap_runs", []).append(
            {
                "timestamp": _utc_now(),
                "mode": mode,
                "profile": profile,
                "enrollment_mode": enrollment_mode,
                "node_id": node["node_id"],
                "status": node["status"],
                "target_host": target_host,
                "domain": domain or None,
                "path_url": path_url or None,
                "operator": enrolled_by,
            }
        )
        self.service.state.save(state)
        return _success_contract(
            "bootstrap-local-node",
            {
                "node": node,
                "transitions_applied": transitions,
                "retry_contract": {
                    "retryable": False,
                    "retry_delay_seconds": 0,
                    "condition": "Only retry after correcting environment-level failures.",
                },
                "rollback_contract": {
                    "hint": "Disable services and remove the node from state if bootstrap must be rolled back.",
                },
            },
        )

    def adoption_report(
        self, *, domain: str | None = None, path_url: str | None = None
    ) -> dict[str, Any]:
        return _success_contract(
            "adoption-report",
            {"report": self.service.adoption_report(domain, path_url)},
        )

    def apply_adoption(
        self, *, domain: str | None = None, path_url: str | None = None
    ) -> dict[str, Any]:
        imported = self.service.import_existing_state(domain, path_url)
        return _success_contract(
            "apply-adoption",
            {
                "imported": imported,
                "retry_contract": {
                    "retryable": True,
                    "retry_delay_seconds": 5,
                    "condition": "Safe to retry after resolving package/path conflicts.",
                },
                "rollback_contract": {
                    "hint": "Remove the imported Nexora node state and uninstall the package if adoption must be cancelled.",
                },
            },
        )

    def apply_augment(
        self, *, domain: str | None = None, path_url: str | None = None
    ) -> dict[str, Any]:
        imported = self.service.import_existing_state(domain, path_url)
        return _success_contract(
            "apply-augment",
            {
                "imported": imported,
                "retry_contract": {
                    "retryable": True,
                    "retry_delay_seconds": 5,
                    "condition": "Safe to retry after resolving package/path conflicts.",
                },
                "rollback_contract": {
                    "hint": "Restore the previous package version or remove the Nexora package if augmentation must be rolled back.",
                },
            },
        )

    def assess_package_lifecycle(
        self, *, yunohost_version: str, operation: str
    ) -> dict[str, Any]:
        capability = PACKAGE_LIFECYCLE_CAPABILITIES.get(operation)
        if capability is None:
            return _error_contract(
                "unsupported_package_operation",
                f"Unsupported package lifecycle operation: {operation}",
                retryable=False,
                rollback_hint="Use one of install, upgrade or restore.",
            )
        matrix_path = resolve_compatibility_matrix_path(self.service.repo_root)
        matrix = load_compatibility_matrix(
            matrix_path if matrix_path.exists() else None
        )
        compatibility = assess_compatibility(
            NEXORA_VERSION, yunohost_version, matrix=matrix
        )
        capability_verdict = compatibility.get("capability_verdicts", {}).get(
            capability, {}
        )
        package_allowed = bool(capability_verdict.get("allowed"))
        if not package_allowed:
            return _error_contract(
                "package_lifecycle_blocked_by_compatibility",
                "Package lifecycle operation blocked by compatibility policy.",
                retryable=False,
                rollback_hint="Align YunoHost version with the tested/supported matrix for this Nexora release.",
                details={
                    "operation": operation,
                    "required_capability": capability,
                    "compatibility": compatibility,
                },
            )
        return _success_contract(
            "assess-package-lifecycle",
            {
                "operation": operation,
                "required_capability": capability,
                "compatibility": compatibility,
            },
        )


def _build_service(args: argparse.Namespace) -> NexoraService:
    return NexoraService(Path(args.repo_root), Path(args.state_path))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m nexora_core.bootstrap")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common_arguments(target: argparse.ArgumentParser) -> None:
        target.add_argument("--repo-root", required=True)
        target.add_argument("--state-path", required=True)
        target.add_argument("--domain", default="")
        target.add_argument("--path-url", default="/nexora")

    assess = subparsers.add_parser("assess")
    add_common_arguments(assess)
    assess.add_argument("--profile", required=True)
    assess.add_argument("--enrollment-mode", required=True)
    assess.add_argument("--mode", required=True)
    assess.add_argument("--yunohost-version", required=True)
    assess.add_argument("--target-host", required=True)

    bootstrap = subparsers.add_parser("bootstrap-node")
    add_common_arguments(bootstrap)
    bootstrap.add_argument("--profile", required=True)
    bootstrap.add_argument("--enrollment-mode", required=True)
    bootstrap.add_argument("--mode", required=True)
    bootstrap.add_argument("--yunohost-version", required=True)
    bootstrap.add_argument("--target-host", required=True)
    bootstrap.add_argument("--enrolled-by", default="bootstrap-node.sh")

    adoption_report = subparsers.add_parser("adoption-report")
    add_common_arguments(adoption_report)

    adopt = subparsers.add_parser("apply-adoption")
    add_common_arguments(adopt)

    augment = subparsers.add_parser("apply-augment")
    add_common_arguments(augment)

    package_lifecycle = subparsers.add_parser("assess-package-lifecycle")
    add_common_arguments(package_lifecycle)
    package_lifecycle.add_argument("--yunohost-version", required=True)
    package_lifecycle.add_argument(
        "--operation", required=True, choices=sorted(PACKAGE_LIFECYCLE_CAPABILITIES)
    )

    args = parser.parse_args(argv)
    orchestrator = BootstrapOrchestrator(_build_service(args))
    if args.command == "assess":
        payload = orchestrator.assess_target(
            profile=args.profile,
            enrollment_mode=args.enrollment_mode,
            mode=args.mode,
            yunohost_version=args.yunohost_version,
            target_host=args.target_host,
            domain=args.domain or None,
            path_url=args.path_url or None,
        )
    elif args.command == "bootstrap-node":
        payload = orchestrator.bootstrap_local_node(
            profile=args.profile,
            enrollment_mode=args.enrollment_mode,
            mode=args.mode,
            yunohost_version=args.yunohost_version,
            target_host=args.target_host,
            domain=args.domain or None,
            path_url=args.path_url or None,
            enrolled_by=args.enrolled_by,
        )
    elif args.command == "adoption-report":
        payload = orchestrator.adoption_report(
            domain=args.domain or None, path_url=args.path_url or None
        )
    elif args.command == "apply-adoption":
        payload = orchestrator.apply_adoption(
            domain=args.domain or None, path_url=args.path_url or None
        )
    elif args.command == "assess-package-lifecycle":
        payload = orchestrator.assess_package_lifecycle(
            yunohost_version=args.yunohost_version,
            operation=args.operation,
        )
    else:
        payload = orchestrator.apply_augment(
            domain=args.domain or None, path_url=args.path_url or None
        )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
