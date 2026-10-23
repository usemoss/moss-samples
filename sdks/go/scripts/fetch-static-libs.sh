#!/usr/bin/env bash
set -euo pipefail

# Downloads static libmoss archives for all supported platforms.
#
# Usage:
#   ./sdks/go/scripts/fetch-static-libs.sh [c-sdk-tag]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RELEASE_TAG="${1:-c-sdk-v0.9.0}"

cd "${ROOT_DIR}"
go run ./tools/install --all --release "${RELEASE_TAG}"
