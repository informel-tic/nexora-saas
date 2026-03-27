#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-$ROOT/dist/e2e-matrix}"
OUT_JSON="$OUT_DIR/operator-e2e-matrix.json"

mkdir -p "$OUT_DIR"
cd "$ROOT"

run_case() {
  local scenario="$1"
  local command="$2"
  local started ended duration status
  local case_log
  started="$(date +%s)"
  case_log="$(mktemp)"
  status="passed"
  if ! bash -lc "$command" >"$case_log" 2>&1; then
    status="failed"
  fi
  ended="$(date +%s)"
  duration="$((ended - started))"
  echo "==> scenario=$scenario status=$status duration=${duration}s"
  cat "$case_log"
  rm -f "$case_log"
  printf '{"scenario":"%s","status":"%s","duration_seconds":%s}' "$scenario" "$status" "$duration"
}

adopt_case="$(run_case adopt 'PYTHONPATH=src python -m pytest tests/test_adoption_report.py -q' | tail -n1)"
augment_case="$(run_case augment 'PYTHONPATH=src python -m pytest tests/test_bootstrap_orchestration.py -q' | tail -n1)"
fresh_case="$(run_case fresh 'PYTHONPATH=src python -m pytest tests/test_packaging.py -q' | tail -n1)"

python3 - <<'PY' "$OUT_JSON" "$adopt_case" "$augment_case" "$fresh_case"
import json
import sys
from datetime import datetime, timezone

out_path = sys.argv[1]
cases = [json.loads(arg) for arg in sys.argv[2:]]
report = {
    "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "profile": "operator",
    "scenarios": cases,
    "all_passed": all(case.get("status") == "passed" for case in cases),
}
with open(out_path, "w", encoding="utf-8") as fh:
    json.dump(report, fh, indent=2)
    fh.write("\n")
print(json.dumps(report, indent=2))
sys.exit(0 if report["all_passed"] else 1)
PY
