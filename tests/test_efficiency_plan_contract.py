from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


class EfficiencyPlanContractTests(unittest.TestCase):
    def test_bootstrap_emits_slo_records(self):
        script = Path("deploy/bootstrap-node.sh").read_text(encoding="utf-8")
        self.assertIn('BOOTSTRAP_SLO_LOG="${BOOTSTRAP_SLO_LOG:-/var/log/nexora/bootstrap-slo.jsonl}"', script)
        self.assertIn('emit_bootstrap_slo()', script)
        self.assertIn("trap 'emit_bootstrap_slo $?'", script)

    def test_nightly_operator_workflow_exists_with_schedule(self):
        workflow_path = Path('.github/workflows/nightly-operator-e2e.yml')
        self.assertTrue(workflow_path.exists())
        workflow = yaml.safe_load(workflow_path.read_text(encoding='utf-8'))
        triggers = workflow.get('on') or workflow.get(True) or {}
        self.assertIn('schedule', triggers)
        self.assertIn('workflow_dispatch', triggers)

    def test_ci_tests_job_generates_cost_report(self):
        workflow = yaml.safe_load(Path('.github/workflows/ci.yml').read_text(encoding='utf-8'))
        steps = workflow['jobs']['tests'].get('steps', [])
        joined = '\n'.join(str(step.get('run', '')) for step in steps)
        self.assertIn('--junitxml=dist/ci/junit.xml', joined)
        self.assertIn('scripts/ci_cost_report.py', joined)

    def test_ci_cost_report_script_produces_expected_fields(self):
        sample = """<testsuite tests=\"2\"><testcase classname=\"a\" name=\"t1\" time=\"0.1\"/><testcase classname=\"b\" name=\"t2\" time=\"0.3\"/></testsuite>"""
        with tempfile.TemporaryDirectory() as tmp:
            junit = Path(tmp) / 'junit.xml'
            out = Path(tmp) / 'report.json'
            junit.write_text(sample, encoding='utf-8')
            subprocess.run([
                'python',
                'scripts/ci_cost_report.py',
                '--junit',
                str(junit),
                '--output',
                str(out),
            ], check=True)
            payload = json.loads(out.read_text(encoding='utf-8'))
            self.assertEqual(payload['test_cases'], 2)
            self.assertIn('p95_seconds', payload)
            self.assertEqual(len(payload['top_slowest']), 2)

    def test_e2e_operator_matrix_script_declares_three_modes(self):
        script = Path("scripts/e2e_operator_matrix.sh").read_text(encoding="utf-8")
        self.assertIn("run_case adopt", script)
        self.assertIn("run_case augment", script)
        self.assertIn("run_case fresh", script)

    def test_node_coherence_audit_exists_and_outputs_status(self):
        script = Path("scripts/node_coherence_audit.py")
        self.assertTrue(script.exists())
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "coherence.json"
            proc = subprocess.run(
                [
                    "python",
                    str(script),
                    "--scope",
                    "operator",
                    "--profile",
                    "control-plane",
                    "--mode",
                    "adopt",
                    "--yunohost-version",
                    "12.1.2",
                    "--output",
                    str(out),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 2)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "blocked")
            blockers = set(payload["blockers"])
            self.assertTrue(
                {"saas_requires_operator_scope", "unsupported_distribution_non_debian"}.intersection(blockers),
                f"Unexpected blockers set: {sorted(blockers)}",
            )


if __name__ == '__main__':
    unittest.main()
