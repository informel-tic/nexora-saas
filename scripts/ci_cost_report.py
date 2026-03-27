#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    idx = int(round((len(values) - 1) * p))
    return values[idx]


def parse_junit(path: Path) -> list[dict]:
    tree = ET.parse(path)
    root = tree.getroot()
    cases: list[dict] = []
    for testcase in root.iter("testcase"):
        name = testcase.attrib.get("name", "unknown")
        classname = testcase.attrib.get("classname", "unknown")
        duration = float(testcase.attrib.get("time", "0") or 0)
        cases.append({"name": name, "classname": classname, "duration": duration})
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a CI runtime cost report from a junit XML file")
    parser.add_argument("--junit", required=True, help="Path to junit XML report")
    parser.add_argument("--output", default="", help="Optional output JSON path")
    args = parser.parse_args()

    cases = parse_junit(Path(args.junit))
    durations = [c["duration"] for c in cases]

    report = {
        "test_cases": len(cases),
        "total_seconds": round(sum(durations), 3),
        "median_seconds": round(percentile(durations, 0.5), 3),
        "p95_seconds": round(percentile(durations, 0.95), 3),
        "top_slowest": sorted(cases, key=lambda c: c["duration"], reverse=True)[:10],
    }

    payload = json.dumps(report, indent=2)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
