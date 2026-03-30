"""Repo-split architectural contract tests.

Enforces the hard boundary between nexora_node_sdk (shared SDK) and
nexora_saas (SaaS control-plane):

  - nexora_node_sdk must NOT import anything from nexora_saas
  - nexora_saas must NOT import anything from the legacy nexora_core module
  - src/ must contain exactly the expected top-level packages
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

SRC_ROOT = Path("src")
NODE_SDK_ROOT = SRC_ROOT / "nexora_node_sdk"
SAAS_ROOT = SRC_ROOT / "nexora_saas"

# Pattern that would indicate node_sdk is importing from saas (forbidden)
_SDK_IMPORTS_SAAS = re.compile(r"^\s*(from|import)\s+nexora_saas\b", re.MULTILINE)
# Pattern for legacy nexora_core references (forbidden everywhere in src/apps)
_NEXORA_CORE_REF = re.compile(r"\bfrom nexora_core[.\s]|\bimport nexora_core\b")

_EXPECTED_SRC_PACKAGES = {"nexora_node_sdk", "nexora_saas", "yunohost_mcp", "nexora_node_sdk"}


class RepoSplitBoundaryTests(unittest.TestCase):
    def _py_files(self, root: Path) -> list[Path]:
        return sorted(root.rglob("*.py"))

    def test_node_sdk_does_not_import_nexora_saas(self):
        violations: list[str] = []
        for path in self._py_files(NODE_SDK_ROOT):
            src = path.read_text(encoding="utf-8")
            if _SDK_IMPORTS_SAAS.search(src):
                violations.append(str(path))

        self.assertFalse(
            violations,
            "nexora_node_sdk must not import from nexora_saas — found violations:\n"
            + "\n".join(violations),
        )

    def test_no_nexora_core_references_in_src(self):
        violations: list[str] = []
        for root in (NODE_SDK_ROOT, SAAS_ROOT):
            for path in self._py_files(root):
                src = path.read_text(encoding="utf-8")
                if _NEXORA_CORE_REF.search(src):
                    violations.append(str(path))

        self.assertFalse(
            violations,
            "Legacy nexora_core references found (must use nexora_node_sdk instead):\n"
            + "\n".join(violations),
        )

    def test_no_nexora_core_references_in_apps(self):
        apps_root = Path("apps")
        violations: list[str] = []
        if apps_root.exists():
            for path in sorted(apps_root.rglob("*.py")):
                src = path.read_text(encoding="utf-8")
                if _NEXORA_CORE_REF.search(src):
                    violations.append(str(path))

        self.assertFalse(
            violations,
            "Legacy nexora_core references found in apps/ (must use nexora_node_sdk instead):\n"
            + "\n".join(violations),
        )

    def test_required_src_packages_exist(self):
        for pkg in ("nexora_node_sdk", "nexora_saas", "yunohost_mcp"):
            self.assertTrue(
                (SRC_ROOT / pkg).is_dir(),
                f"Expected package src/{pkg}/ is missing",
            )

    def test_saas_imports_node_sdk_not_directly_coupled_to_apps(self):
        """nexora_saas should not import directly from apps/ modules."""
        _apps_import = re.compile(r"^\s*(from|import)\s+apps\b", re.MULTILINE)
        violations: list[str] = []
        for path in self._py_files(SAAS_ROOT):
            src = path.read_text(encoding="utf-8")
            if _apps_import.search(src):
                violations.append(str(path))

        self.assertFalse(
            violations,
            "nexora_saas must not import directly from apps/ — found violations:\n"
            + "\n".join(violations),
        )


if __name__ == "__main__":
    unittest.main()
