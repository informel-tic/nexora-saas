#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${MODE:-auto}"
PROFILE="${PROFILE:-control-plane+node-agent}"
ENROLLMENT_MODE="${ENROLLMENT_MODE:-pull}"
if [[ "$MODE" == "auto" ]]; then
  MODE="$(bash "$ROOT/deploy/bootstrap-detect-mode.sh")"
fi
exec env MODE="$MODE" PROFILE="$PROFILE" ENROLLMENT_MODE="$ENROLLMENT_MODE" bash "$ROOT/deploy/bootstrap-node.sh"
