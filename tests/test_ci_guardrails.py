from __future__ import annotations

import unittest
from pathlib import Path


class SaaSCIWorkflowTests(unittest.TestCase):
    def test_ci_workflow_is_saas_scoped(self):
        source = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("security-scan", source)
        self.assertIn("docs-quality", source)
        self.assertIn("tests:", source)
        self.assertNotIn("package-lint:", source)

    def test_nightly_workflow_is_present(self):
        source = Path(".github/workflows/nightly-operator-e2e.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("operator-e2e-matrix", source)


if __name__ == "__main__":
    unittest.main()