from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


class DocsObsolescenceContractTests(unittest.TestCase):
    def test_no_obsolete_docs_marker_remaining(self):
        script = Path("scripts/docs_obsolescence_audit.py")
        self.assertTrue(script.exists(), "docs obsolescence audit script must exist")

        proc = subprocess.run(
            ["python", str(script), "--enforce-removal"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            proc.returncode,
            0,
            f"Obsolete docs must be removed before merge.\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
