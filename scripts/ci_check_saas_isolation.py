"""CI Gate: verify nexora_saas depends only on nexora_node_sdk for shared modules.

This script ensures no raw nexora_core references survive in the SaaS codebase
(excluding documentation files).
"""
from __future__ import annotations

import pathlib
import re
import sys


PATTERN = re.compile(r"\bfrom nexora_core[.\s]|\bimport nexora_core\b")


def check_no_nexora_core() -> list[str]:
    violations: list[str] = []
    roots = [
        pathlib.Path("src/nexora_saas"),
        pathlib.Path("src/yunohost_mcp"),
        pathlib.Path("apps/control_plane"),
        pathlib.Path("apps/console"),
        pathlib.Path("scripts"),
        pathlib.Path("deploy"),
        pathlib.Path("tests"),
    ]
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if PATTERN.search(line):
                    violations.append(f"{p}:{i}: {line.strip()}")
    return violations


def main() -> None:
    violations = check_no_nexora_core()
    if violations:
        print("FAIL: nexora_core references found in SaaS repo:")
        for v in violations:
            print(f"  {v}")
        sys.exit(1)
    print("OK: no nexora_core references in SaaS repo code")


if __name__ == "__main__":
    main()
