#!/bin/bash
set -euo pipefail
MODE="${MODE:-fresh}"
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/bootstrap-full-platform.sh"
