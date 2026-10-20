#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
PACKAGES_DIR="$ROOT_DIR/packages"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ── Configuration ──────────────────────────────────────────────────────────────

NPM_PACKAGES=(
  "moss-md-indexer"
  "vercel-sdk"
  "vitepress-plugin-moss"
)

PYPI_PACKAGES=(
  "elevenlabs-moss"
  "pipecat-moss"
  "strands-agents-moss"
  "vapi-moss"
)

# ── Helpers ────────────────────────────────────────────────────────────────────

log()   { echo -e "${BLUE}[release]${NC} $*"; }
ok()    { echo -e "${GREEN}  ✓${NC} $*"; }
warn()  { echo -e "${YELLOW}  ⚠${NC} $*"; }
fail()  { echo -e "${RED}  ✗${NC} $*"; }
hr()    { echo -e "${BLUE}─────────────────────────────────────────────────${NC}"; }

FAILED=()
SUCCEEDED=()

# ── Preflight checks ──────────────────────────────────────────────────────────

preflight() {
  log "Running preflight checks..."
  local missing=0

  if ! command -v npm &>/dev/null; then
    fail "npm not found"; missing=1
  else
    ok "npm $(npm --version)"
  fi

  if ! command -v node &>/dev/null; then
    fail "node not found"; missing=1
  else
    ok "node $(node --version)"
  fi

  if ! command -v pnpm &>/dev/null; then
    warn "pnpm not found — packages with pnpm-lock.yaml will fall back to npm"
  else
    ok "pnpm $(pnpm --version)"
  fi

  if ! command -v python3 &>/dev/null; then
    fail "python3 not found"; missing=1
  else
    ok "python3 $(python3 --version 2>&1 | awk '{print $2}')"
  fi

  if ! command -v uv &>/dev/null; then
    if ! command -v pip &>/dev/null; then
      fail "Neither uv nor pip found — need one for Python builds"; missing=1
    else
      ok "pip $(pip --version | awk '{print $2}')"

      if python3 -m build --version &>/dev/null; then
        ok "python3 -m build available"
      else
        fail "Python 'build' module not found — install with: pip install build"; missing=1
      fi

      if python3 -m twine --version &>/dev/null; then
        ok "python3 -m twine available"
      else
        fail "Python 'twine' module not found — install with: pip install twine"; missing=1
      fi
    fi
  else
    ok "uv $(uv --version 2>&1 | awk '{print $2}')"
  fi

  # Check npm auth
  if npm whoami &>/dev/null 2>&1; then
    ok "npm authenticated as $(npm whoami)"
  else
    warn "npm not authenticated — npm publish will prompt or fail"
  fi

  if [[ $missing -eq 1 ]]; then
    fail "Missing required tools. Aborting."
    exit 1
  fi

  echo ""
}

# ── npm package release ───────────────────────────────────────────────────────

release_npm() {
  local pkg_dir="$1"
  local pkg_name
  pkg_name=$(basename "$pkg_dir")
  local full_name
  full_name=$(node -p "require('$pkg_dir/package.json').name") || return 1
  local version
  version=$(node -p "require('$pkg_dir/package.json').version") || return 1

  hr
  log "Publishing ${full_name}@${version} to npm"

  cd "$pkg_dir" || return 1

  # Install dependencies
  if [[ -f "pnpm-lock.yaml" ]] && command -v pnpm &>/dev/null; then
    { pnpm install --frozen-lockfile 2>/dev/null || pnpm install; } || return 1
  elif [[ -f "package-lock.json" ]]; then
    { npm ci 2>/dev/null || npm install; } || return 1
  else
    npm install || return 1
  fi

  # Build
  if node -p "require('./package.json').scripts?.build" 2>/dev/null | grep -qv "undefined"; then
    log "  Building..."
    npm run build || return 1
  fi

  # Publish
  if [[ "$DRY_RUN" == "true" ]]; then
    log "  [DRY RUN] Would publish ${full_name}@${version}"
    npm pack --dry-run || return 1
    ok "Dry run complete for ${full_name}"
  else
    npm publish --access public || return 1
    ok "Published ${full_name}@${version}"
  fi

  SUCCEEDED+=("${full_name}@${version}")
  cd "$ROOT_DIR"
}

# ── PyPI package release ──────────────────────────────────────────────────────

release_pypi() {
  local pkg_dir="$1"
  local pkg_name
  pkg_name=$(python3 -c "
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib
import pathlib
p = pathlib.Path('$pkg_dir/pyproject.toml')
d = tomllib.loads(p.read_text())
print(d['project']['name'])
") || return 1
  local version
  version=$(python3 -c "
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib
import pathlib
p = pathlib.Path('$pkg_dir/pyproject.toml')
d = tomllib.loads(p.read_text())
print(d['project']['version'])
") || return 1

  hr
  log "Publishing ${pkg_name}==${version} to PyPI"

  cd "$pkg_dir" || return 1

  # Clean previous builds
  rm -rf dist/ build/ *.egg-info src/*.egg-info

  # Build
  log "  Building sdist + wheel..."
  if command -v uv &>/dev/null; then
    uv build || return 1
  else
    python3 -m build || return 1
  fi

  # Publish
  if [[ "$DRY_RUN" == "true" ]]; then
    log "  [DRY RUN] Would publish ${pkg_name}==${version}"
    ls -lh dist/
    ok "Dry run complete for ${pkg_name}"
  else
    if command -v uv &>/dev/null; then
      uv publish || return 1
    elif command -v twine &>/dev/null; then
      twine upload dist/* || return 1
    else
      python3 -m twine upload dist/* || return 1
    fi
    ok "Published ${pkg_name}==${version}"
  fi

  SUCCEEDED+=("${pkg_name}==${version}")
  cd "$ROOT_DIR"
}

# ── Main ──────────────────────────────────────────────────────────────────────

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS] [PACKAGE...]

Release Moss packages to npm and PyPI.

Options:
  --dry-run       Build and pack without publishing
  --npm-only      Only release npm packages
  --pypi-only     Only release PyPI packages
  --help          Show this help

Packages:
  If no packages specified, all packages are released.
  Specify package directory names to release selectively:
    $(basename "$0") vercel-sdk pipecat-moss

Examples:
  $(basename "$0") --dry-run                    # Dry run all packages
  $(basename "$0") vercel-sdk                   # Release only vercel-sdk
  $(basename "$0") --pypi-only --dry-run        # Dry run all Python packages
EOF
}

DRY_RUN="false"
NPM_ONLY="false"
PYPI_ONLY="false"
SELECTED_PACKAGES=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)   DRY_RUN="true"; shift ;;
    --npm-only)  NPM_ONLY="true"; shift ;;
    --pypi-only) PYPI_ONLY="true"; shift ;;
    --help|-h)   usage; exit 0 ;;
    -*)          fail "Unknown option: $1"; usage; exit 1 ;;
    *)           SELECTED_PACKAGES+=("$1"); shift ;;
  esac
done

echo ""
log "Moss Package Release"
[[ "$DRY_RUN" == "true" ]] && warn "DRY RUN MODE — nothing will be published"
echo ""

preflight

# Determine which packages to release
do_npm=()
do_pypi=()

if [[ ${#SELECTED_PACKAGES[@]} -gt 0 ]]; then
  for sel in "${SELECTED_PACKAGES[@]}"; do
    matched=false
    if [[ "$PYPI_ONLY" != "true" ]]; then
      for np in "${NPM_PACKAGES[@]}"; do
        if [[ "$np" == "$sel" ]]; then
          do_npm+=("$np")
          matched=true
        fi
      done
    fi
    if [[ "$NPM_ONLY" != "true" ]]; then
      for pp in "${PYPI_PACKAGES[@]}"; do
        if [[ "$pp" == "$sel" ]]; then
          do_pypi+=("$pp")
          matched=true
        fi
      done
    fi
    if [[ "$matched" == "false" ]]; then
      fail "Unknown package: $sel"
      exit 1
    fi
  done
else
  if [[ "$PYPI_ONLY" != "true" ]]; then
    do_npm=("${NPM_PACKAGES[@]}")
  fi
  if [[ "$NPM_ONLY" != "true" ]]; then
    do_pypi=("${PYPI_PACKAGES[@]}")
  fi
fi

# Release npm packages
for pkg in "${do_npm[@]}"; do
  if ! release_npm "$PACKAGES_DIR/$pkg"; then
    fail "Failed to release $pkg"
    FAILED+=("$pkg")
  fi
done

# Release PyPI packages
for pkg in "${do_pypi[@]}"; do
  if ! release_pypi "$PACKAGES_DIR/$pkg"; then
    fail "Failed to release $pkg"
    FAILED+=("$pkg")
  fi
done

# ── Summary ───────────────────────────────────────────────────────────────────

echo ""
hr
log "Release Summary"
echo ""

if [[ ${#SUCCEEDED[@]} -gt 0 ]]; then
  ok "Released (${#SUCCEEDED[@]}):"
  for s in "${SUCCEEDED[@]}"; do
    echo -e "     ${GREEN}•${NC} $s"
  done
fi

if [[ ${#FAILED[@]} -gt 0 ]]; then
  echo ""
  fail "Failed (${#FAILED[@]}):"
  for f in "${FAILED[@]}"; do
    echo -e "     ${RED}•${NC} $f"
  done
  exit 1
fi

echo ""
ok "All packages released successfully!"
