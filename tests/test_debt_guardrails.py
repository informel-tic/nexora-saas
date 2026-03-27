from __future__ import annotations

import re
import unittest
from pathlib import Path


FORBIDDEN_PATTERNS = [
    re.compile(r"except\s+Exception\s*:\s*pass"),
    re.compile(r"except\s*:\s*pass"),
]

FORBIDDEN_SUBSTRINGS = [
    "._tool_manager",
]

# Runtime-critical files where silent failure is not tolerated.
GUARDED_FILES = [
    Path("src/nexora_node_sdk/orchestrator.py"),
    Path("src/nexora_node_sdk/admin_actions.py"),
    Path("src/yunohost_mcp/server.py"),
    Path("src/yunohost_mcp/utils/runner.py"),
    Path("apps/control_plane/api.py"),
    Path("apps/node_agent/api.py"),
]


class DebtGuardrailsTests(unittest.TestCase):
    def test_no_silent_exception_swallowing_in_guarded_files(self):
        violations: list[str] = []
        for path in GUARDED_FILES:
            source = path.read_text(encoding="utf-8")
            for pattern in FORBIDDEN_PATTERNS:
                for match in pattern.finditer(source):
                    line = source.count("\n", 0, match.start()) + 1
                    violations.append(f"{path}:{line}: {pattern.pattern}")

        self.assertFalse(
            violations,
            "Silent exception swallowing is forbidden in guarded files:\n" + "\n".join(violations),
        )

    def test_no_private_fastmcp_registry_access(self):
        violations: list[str] = []
        for path in GUARDED_FILES:
            source = path.read_text(encoding="utf-8")
            for forbidden in FORBIDDEN_SUBSTRINGS:
                if forbidden in source:
                    line = source.index(forbidden)
                    line_no = source.count("\n", 0, line) + 1
                    violations.append(f"{path}:{line_no}: contains {forbidden!r}")

        self.assertFalse(
            violations,
            "Private FastMCP internals are forbidden in guarded files:\n" + "\n".join(violations),
        )


if __name__ == "__main__":
    unittest.main()
