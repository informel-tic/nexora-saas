#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import json
import logging
import sys
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.control_plane.api import app
from nexora_node_sdk.auth import get_api_token

logging.getLogger("httpx").setLevel(logging.WARNING)


def _request_once(client: TestClient, tenant_id: str, api_token: str) -> dict[str, object]:
    started = time.perf_counter()
    headers = {
        "X-Nexora-Token": api_token,
        "X-Nexora-Tenant-Id": tenant_id,
    }
    response = client.get("/api/scores", headers=headers)
    payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return {
        "status_code": response.status_code,
        "tenant_id": payload.get("tenant_id"),
        "requested_tenant_id": tenant_id,
        "latency_ms": elapsed_ms,
    }


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = int(round((len(sorted_values) - 1) * ratio))
    return float(sorted_values[index])


def run_smoke(tenants: int, requests: int, workers: int, duration_seconds: int) -> dict[str, object]:
    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "state.json"
        state_path.write_text(json.dumps({"nodes": []}), encoding="utf-8")
        with TestClient(app) as client:
            api_token = get_api_token()
            tenant_ids = [f"tenant-{idx}" for idx in range(tenants)]
            futures = []
            started = time.perf_counter()
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
                for index in range(requests):
                    if duration_seconds > 0 and (time.perf_counter() - started) >= duration_seconds:
                        break
                    tenant_id = tenant_ids[index % len(tenant_ids)]
                    futures.append(pool.submit(_request_once, client, tenant_id, api_token))
            results = [future.result() for future in futures]
            elapsed_seconds = time.perf_counter() - started

    failures = [
        result
        for result in results
        if result["status_code"] != 200
        or str(result.get("tenant_id", "")).strip() != str(result.get("requested_tenant_id", "")).strip()
    ]
    latencies = [float(item.get("latency_ms", 0.0)) for item in results]
    throughput = (len(results) / elapsed_seconds) if elapsed_seconds > 0 else 0.0
    return {
        "requests_requested": requests,
        "requests_executed": len(results),
        "tenants": tenants,
        "workers": workers,
        "duration_seconds": round(elapsed_seconds, 3),
        "latency_ms": {
            "p50": round(_percentile(latencies, 0.50), 3),
            "p95": round(_percentile(latencies, 0.95), 3),
            "p99": round(_percentile(latencies, 0.99), 3),
            "max": round(max(latencies), 3) if latencies else 0.0,
        },
        "throughput_rps": round(throughput, 3),
        "failures": len(failures),
        "sample_failure": failures[0] if failures else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Lightweight multi-tenant load smoke test")
    parser.add_argument("--tenants", type=int, default=8)
    parser.add_argument("--requests", type=int, default=500)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--duration-seconds", type=int, default=30)
    parser.add_argument("--max-failures", type=int, default=0)
    parser.add_argument("--max-p95-ms", type=float, default=500.0)
    args = parser.parse_args()

    report = run_smoke(
        tenants=args.tenants,
        requests=args.requests,
        workers=args.workers,
        duration_seconds=args.duration_seconds,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    has_failure_budget = int(report["failures"]) <= args.max_failures
    has_latency_budget = float(report["latency_ms"]["p95"]) <= args.max_p95_ms
    return 0 if has_failure_budget and has_latency_budget else 1


if __name__ == "__main__":
    raise SystemExit(main())
