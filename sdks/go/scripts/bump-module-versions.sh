#!/usr/bin/env bash
set -euo pipefail

# Pins the public sdk module to a published bindings version.
#
# Usage:
#   ./sdks/go/scripts/bump-module-versions.sh v0.9.0

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <go-module-version>" >&2
  echo "Example: $0 v0.9.0" >&2
  exit 1
fi

VERSION="$1"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SDK_DIR="${ROOT_DIR}/sdk"

(
  cd "${SDK_DIR}"
  go mod edit -require="github.com/usemoss/moss/sdks/go/bindings@${VERSION}"
  go mod edit -dropreplace=github.com/usemoss/moss/sdks/go/bindings 2>/dev/null || true
)

echo "Pinned sdk module to bindings ${VERSION}"
