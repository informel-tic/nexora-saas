from __future__ import annotations

import re
import unittest
from pathlib import Path

DOCS_ROOT = Path("docs")
MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


class DocsCompletenessTests(unittest.TestCase):
    def test_all_docs_markdown_files_are_non_empty_and_titled(self):
        files = sorted(DOCS_ROOT.rglob("*.md"))
        self.assertTrue(files, "No markdown files found in docs/")

        for path in files:
            text = path.read_text(encoding="utf-8")
            self.assertTrue(text.strip(), f"{path} is empty")

            first_non_empty = next((line.strip() for line in text.splitlines() if line.strip()), "")
            self.assertTrue(
                first_non_empty.startswith("#"),
                f"{path} should start with a markdown heading",
            )

    def test_relative_markdown_links_resolve_in_docs_tree(self):
        files = sorted(DOCS_ROOT.rglob("*.md"))
        self.assertTrue(files, "No markdown files found in docs/")

        broken_links: list[str] = []

        for source in files:
            content = source.read_text(encoding="utf-8")
            for raw_target in MARKDOWN_LINK_PATTERN.findall(content):
                target = raw_target.strip()
                if not target or target.startswith(("http://", "https://", "mailto:", "#")):
                    continue

                target_path = target.split("#", 1)[0].split("?", 1)[0]
                if not target_path:
                    continue

                resolved = (source.parent / target_path).resolve()
                if not resolved.exists():
                    broken_links.append(f"{source}: {target}")

        self.assertFalse(
            broken_links,
            "Broken relative markdown links found:\n" + "\n".join(sorted(broken_links)),
        )


if __name__ == "__main__":
    unittest.main()
