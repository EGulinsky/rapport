#!/usr/bin/env bash
# Builds the "rapport-agent" Linux onedir bundle via PyInstaller, then
# packages it into a tarball for distribution. Must run ON Linux —
# PyInstaller does not cross-compile, so this cannot be run from the Mac
# dev checkout.
#
# Usage (from a venv with requirements-packaging-linux.txt installed):
#   agent/packaging/build_linux.sh [version]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION="${1:-0.1.0}"

DIST_DIR="$SCRIPT_DIR/dist"
BUILD_DIR="$SCRIPT_DIR/build"
APP_DIR="$DIST_DIR/rapport-agent"
TARBALL_NAME="rapport-agent-${VERSION}-linux.tar.gz"

echo "==> Building rapport-agent with PyInstaller…"
export AGENT_VERSION="$VERSION"
pyinstaller "$SCRIPT_DIR/agent-linux.spec" --distpath "$DIST_DIR" --workpath "$BUILD_DIR" --noconfirm

if [ ! -d "$APP_DIR" ]; then
  echo "Error: $APP_DIR was not produced." >&2
  exit 1
fi

echo "==> Packaging ${TARBALL_NAME}…"
rm -f "$DIST_DIR/$TARBALL_NAME"
tar -czf "$DIST_DIR/$TARBALL_NAME" -C "$DIST_DIR" "rapport-agent"

echo "==> Done: $DIST_DIR/$TARBALL_NAME"
echo
echo "First launch of the extracted 'rapport-agent' binary self-registers a"
echo "systemd user service (see systemd_service.py) so it restarts at login"
echo "without a second manual start. Requires zenity/kdialog and xclip/xsel"
echo "for the file picker and clipboard actions — see agent/README.md."
