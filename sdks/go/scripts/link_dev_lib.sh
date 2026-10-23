#!/usr/bin/env bash
set -euo pipefail

# Installs the native library for the current machine (local dev helper).
#
# Usage:
#   ./sdks/go/scripts/link_dev_lib.sh [c-sdk-tag]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RELEASE_TAG="${1:-c-sdk-v0.9.0}"

cd "${ROOT_DIR}"
go run ./tools/install --release "${RELEASE_TAG}"
