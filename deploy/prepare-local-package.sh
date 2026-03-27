#!/bin/bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${REPO_ROOT}/.build/local-source"
SRC_ARCHIVE="${REPO_ROOT}/.build/nexora-source.tar.gz"
mkdir -p "${BUILD_DIR}" "${REPO_ROOT}/.build"
rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}/repo"
# Copy sources excluding .git and .build (works with or without rsync)
if command -v rsync >/dev/null 2>&1; then
  rsync -a --exclude '.git' --exclude '.build' "${REPO_ROOT}/" "${BUILD_DIR}/repo/"
else
  # Use tar pipe to copy while excluding .git and .build (avoids cp self-nesting issue)
  tar -C "${REPO_ROOT}" \
    --exclude='./.git' \
    --exclude='./.build' \
    -cf - . | tar -C "${BUILD_DIR}/repo" -xf -
fi
tar -czf "${SRC_ARCHIVE}" -C "${BUILD_DIR}/repo" .
echo "${SRC_ARCHIVE}"
