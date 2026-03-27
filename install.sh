#!/bin/bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "This repository deploys the Nexora SaaS control plane."
echo "Example: DOMAIN=example.org PATH_URL=/nexora $ROOT_DIR/deploy/bootstrap-ynh-local.sh"
