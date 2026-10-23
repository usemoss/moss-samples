#!/usr/bin/env bash
set -euo pipefail

# Publishes source-only bindings + sdk module tags.
#
# Usage:
#   ./sdks/go/scripts/publish-sdk-module-tags.sh v0.1.2

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <version> [remote]" >&2
  exit 1
fi

VERSION="$1"
REMOTE="${2:-origin}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "${ROOT_DIR}/../.." && pwd)"

cd "${REPO_ROOT}"

TAGS=(
  "sdks/go/bindings/${VERSION}"
  "sdks/go/sdk/${VERSION}"
  "sdks/go/tools/install/${VERSION}"
)

for tag in "${TAGS[@]}"; do
  if git rev-parse --verify --quiet "refs/tags/${tag}" >/dev/null; then
    echo "Refusing to overwrite existing local tag ${tag}" >&2
    exit 1
  fi
  if [[ -n "$(git ls-remote --tags "${REMOTE}" "refs/tags/${tag}")" ]]; then
    echo "Refusing to overwrite existing remote tag ${tag}" >&2
    exit 1
  fi
done

"${ROOT_DIR}/scripts/bump-module-versions.sh" "${VERSION}"

git add sdks/go/bindings/go.mod sdks/go/sdk/go.mod sdks/go/bindings/version.go
git add sdks/go/bindings/include/libmoss.h sdks/go/bindings/generate.go
git add sdks/go/tools/install

if ! git diff --cached --quiet; then
  git commit -m "chore(go): publish bindings and sdk ${VERSION}"
fi

for tag in "${TAGS[@]}"; do
  git tag "${tag}"
done

REFS=("${TAGS[@]/#/refs/tags/}")
if ! git push --atomic "${REMOTE}" "${REFS[@]}"; then
  git tag -d "${TAGS[@]}" >/dev/null
  exit 1
fi

printf 'Published %s\n' "${TAGS[@]}"
