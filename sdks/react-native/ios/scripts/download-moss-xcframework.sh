#!/usr/bin/env bash
# Downloads Moss.xcframework (MossC) used by the Expo iOS module.
# Invoked while MossReactNative.podspec is evaluated (not from prepare_command,
# which CocoaPods skips for development pods) so the binary is not committed.
# Idempotent: exits early when the framework is already in place.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FRAMEWORKS_DIR="${ROOT_DIR}/Frameworks"
XCFRAMEWORK="${FRAMEWORKS_DIR}/Moss.xcframework"
VERSION="${MOSS_XCFRAMEWORK_VERSION:-v0.6.2}"
URL="https://github.com/usemoss/moss/releases/download/${VERSION}/Moss.xcframework.zip"
EXPECTED_SHA256="${MOSS_XCFRAMEWORK_SHA256:-db6bffcd27fec51ad275e27777f2037746a173c5c3e05f1b8d67981229b9e7d1}"

if [[ -d "${XCFRAMEWORK}" ]]; then
  echo "Moss.xcframework already present at ${XCFRAMEWORK}"
  exit 0
fi

mkdir -p "${FRAMEWORKS_DIR}"
TMP_ZIP="$(mktemp -t Moss.xcframework.XXXXXX.zip)"
cleanup() { rm -f "${TMP_ZIP}"; }
trap cleanup EXIT

echo "Downloading Moss.xcframework ${VERSION}…"
curl -fsSL -o "${TMP_ZIP}" "${URL}"

ACTUAL_SHA256="$(shasum -a 256 "${TMP_ZIP}" | awk '{print $1}')"
if [[ "${ACTUAL_SHA256}" != "${EXPECTED_SHA256}" ]]; then
  echo "error: Moss.xcframework.zip checksum mismatch" >&2
  echo "  expected: ${EXPECTED_SHA256}" >&2
  echo "  actual:   ${ACTUAL_SHA256}" >&2
  exit 1
fi

unzip -qo "${TMP_ZIP}" -d "${FRAMEWORKS_DIR}"
if [[ ! -d "${XCFRAMEWORK}" ]]; then
  echo "error: unzip did not produce ${XCFRAMEWORK}" >&2
  exit 1
fi

echo "Installed Moss.xcframework → ${XCFRAMEWORK}"
