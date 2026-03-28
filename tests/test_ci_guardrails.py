from __future__ import annotations

import unittest
from pathlib import Path

import yaml

CI_WORKFLOW_PATH = Path('.github/workflows/ci.yml')


class CIGuardrailsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not CI_WORKFLOW_PATH.exists():
            raise AssertionError(f'{CI_WORKFLOW_PATH} should exist')
        cls.workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding='utf-8'))

    def test_workflow_runs_on_pull_request(self):
        triggers = self.workflow.get('on') or self.workflow.get(True) or {}
        self.assertIn('pull_request', triggers, 'CI workflow must run on every PR')

    def test_required_jobs_exist(self):
        jobs = self.workflow.get('jobs', {})
        for job in ('changes', 'test-collection', 'docs-quality', 'tests', 'vision-final-ready'):
            self.assertIn(job, jobs, f'Missing CI job: {job}')

    def test_tests_job_depends_on_quality_gates(self):
        jobs = self.workflow['jobs']
        needs = jobs['tests'].get('needs', [])
        if isinstance(needs, str):
            needs = [needs]

        self.assertCountEqual(
            needs,
            ['changes', 'test-collection', 'docs-quality'],
            'The main tests job must wait for change detection, collection and docs checks',
        )

    def test_code_jobs_use_docs_only_fast_path(self):
        jobs = self.workflow['jobs']
        test_collection_steps = jobs['test-collection'].get('steps', [])
        tests_steps = jobs['tests'].get('steps', [])

        self.assertIsNone(
            jobs['test-collection'].get('if'),
            'test-collection should complete on every PR (real run or docs-only fast path)',
        )
        self.assertIsNone(
            jobs['tests'].get('if'),
            'tests should complete on every PR (real run or docs-only fast path)',
        )
        self.assertTrue(
            any(step.get('name') == 'Collect tests' and step.get('if') == "needs.changes.outputs.code_changed == 'true'" for step in test_collection_steps),
            'Collect tests step must run only when code_changed == true',
        )
        self.assertTrue(
            any(step.get('name') == 'Docs-only fast path' and step.get('if') == "needs.changes.outputs.code_changed != 'true'" for step in test_collection_steps),
            'test-collection must include a docs-only fast path step',
        )
        self.assertTrue(
            any(step.get('name') == 'Run tests' and step.get('if') == "needs.changes.outputs.code_changed == 'true'" for step in tests_steps),
            'Run tests step must run only when code_changed == true',
        )
        self.assertTrue(
            any(step.get('name') == 'Docs-only fast path' and step.get('if') == "needs.changes.outputs.code_changed != 'true'" for step in tests_steps),
            'tests must include a docs-only fast path step',
        )

    def test_docs_quality_job_checks_docs_and_ci_contract(self):
        steps = self.workflow['jobs']['docs-quality'].get('steps', [])
        run_blocks = [step.get('run', '') for step in steps]
        joined = '\n'.join(run_blocks)

        self.assertIn('tests/test_docs_completeness.py', joined)
        self.assertIn('tests/test_docs_inventory_contract.py', joined)
        self.assertIn('tests/test_docs_obsolescence_contract.py', joined)
        self.assertIn('tests/test_ci_guardrails.py', joined)
        self.assertIn('tests/test_repo_split_contract.py', joined)
        self.assertIn('tests/test_auth_runtime_resilience.py', joined)
        self.assertIn('scripts/docs_obsolescence_audit.py --enforce-removal', joined)

    def test_vision_final_ready_depends_on_core_jobs_and_runs_expected_checks(self):
        jobs = self.workflow['jobs']
        needs = jobs['vision-final-ready'].get('needs', [])
        if isinstance(needs, str):
            needs = [needs]
        self.assertCountEqual(
            needs,
            ['changes', 'test-collection', 'docs-quality', 'tests', 'lint', 'security-scan'],
            'vision-final-ready must depend on core CI jobs',
        )
        steps = jobs['vision-final-ready'].get('steps', [])
        run_blocks = [step.get('run', '') for step in steps]
        joined = '\n'.join(run_blocks)
        self.assertIn('tests/test_persistence_backend.py', joined)
        self.assertIn('scripts/load_test_multitenant.py', joined)


if __name__ == '__main__':
    unittest.main()
