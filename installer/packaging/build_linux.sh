#!/usr/bin/env bash
# Builds the "rapport-installer" Linux onedir bundle via PyInstaller, then
# packages it into a tarball for distribution. Must run ON Linux —
# PyInstaller does not cross-compile. Mirrors agent/packaging/build_linux.sh,
# plus a version-stamping step for installer/version.py.
#
# Usage (from a venv with requirements-packaging-linux.txt installed):
#   installer/packaging/build_linux.sh [version]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VERSION="${1:-0.1.0}"

DIST_DIR="$SCRIPT_DIR/dist"
BUILD_DIR="$SCRIPT_DIR/build"
APP_DIR="$DIST_DIR/rapport-installer"
TARBALL_NAME="rapport-installer-${VERSION}-linux.tar.gz"

VERSION_FILE="$REPO_ROOT/installer/version.py"
ORIGINAL_VERSION_CONTENT="$(cat "$VERSION_FILE")"
trap 'echo "$ORIGINAL_VERSION_CONTENT" > "$VERSION_FILE"' EXIT

echo "==> Stamping version ${VERSION}..."
echo "INSTALLER_VERSION = \"${VERSION}\"" > "$VERSION_FILE"

echo "==> Building rapport-installer with PyInstaller..."
pyinstaller "$SCRIPT_DIR/installer-linux.spec" --distpath "$DIST_DIR" --workpath "$BUILD_DIR" --noconfirm

if [ ! -d "$APP_DIR" ]; then
  echo "Error: $APP_DIR was not produced." >&2
  exit 1
fi

echo "==> Packaging ${TARBALL_NAME}..."
rm -f "$DIST_DIR/$TARBALL_NAME"
tar -czf "$DIST_DIR/$TARBALL_NAME" -C "$DIST_DIR" "rapport-installer"

echo "==> Done: $DIST_DIR/$TARBALL_NAME"
