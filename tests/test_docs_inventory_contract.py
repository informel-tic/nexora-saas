from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

DOCS_ROOT = Path('docs')
INVENTORY_PATH = DOCS_ROOT / 'docs_inventory.yaml'
DATE_MARKER = re.compile(r'20\d{2}-\d{2}-\d{2}')


class DocsInventoryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not INVENTORY_PATH.exists():
            raise AssertionError(f'{INVENTORY_PATH} should exist')
        cls.inventory = yaml.safe_load(INVENTORY_PATH.read_text(encoding='utf-8'))
        cls.docs = sorted(path.as_posix() for path in DOCS_ROOT.rglob('*.md'))
        cls.entries = cls.inventory.get('documents', [])
        cls.entry_paths = sorted(entry['path'] for entry in cls.entries)

    def test_inventory_matches_markdown_docs_set(self):
        self.assertEqual(
            self.docs,
            self.entry_paths,
            'docs_inventory.yaml must list all markdown docs (and only them)',
        )

    def test_scope_count_matches_actual(self):
        expected = self.inventory.get('scope', {}).get('markdown_docs_count')
        self.assertEqual(
            expected,
            len(self.docs),
            'scope.markdown_docs_count should match real markdown docs count',
        )

    def test_dependencies_resolve_to_existing_files(self):
        available = set(self.docs)
        available.add('.github/workflows/ci.yml')
        available.update(path.as_posix() for path in Path('tests').glob('test_*.py'))

        unresolved: list[str] = []
        for entry in self.entries:
            for dep in entry.get('depends_on', []):
                if dep not in available:
                    unresolved.append(f"{entry['path']} -> {dep}")

        self.assertFalse(
            unresolved,
            'Every dependency in docs_inventory.yaml must resolve:\n' + '\n'.join(unresolved),
        )

    def test_audit_snapshot_docs_are_explicitly_dated(self):
        missing: list[str] = []
        for entry in self.entries:
            if entry.get('type') != 'audit_snapshot':
                continue
            path = Path(entry['path'])
            snippet = '\n'.join(path.read_text(encoding='utf-8').splitlines()[:25])
            if not DATE_MARKER.search(snippet):
                missing.append(entry['path'])

        self.assertFalse(
            missing,
            'Audit snapshot docs must expose a date marker near the header: ' + ', '.join(missing),
        )


if __name__ == '__main__':
    unittest.main()
