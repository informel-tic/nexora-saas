#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec env MODE=fresh PROFILE="${PROFILE:-control-plane+node-agent}" ENROLLMENT_MODE="${ENROLLMENT_MODE:-pull}" bash "$ROOT/deploy/bootstrap-node.sh"
