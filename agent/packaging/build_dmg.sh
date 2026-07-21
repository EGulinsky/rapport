#!/usr/bin/env bash
# Builds "Rapport Agent.app" via PyInstaller, then packages it into a
# drag-to-Applications .dmg using hdiutil (no extra Homebrew tool needed —
# hdiutil ships with macOS).
#
# Usage: agent/packaging/build_dmg.sh [version]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VERSION="${1:-0.1.0}"

DIST_DIR="$SCRIPT_DIR/dist"
BUILD_DIR="$SCRIPT_DIR/build"
APP_NAME="Rapport Agent.app"
DMG_NAME="Rapport-Agent-${VERSION}.dmg"
STAGING_DIR="$SCRIPT_DIR/dmg_staging"

echo "==> Baue ${APP_NAME} mit PyInstaller…"
export AGENT_VERSION="$VERSION"
pyinstaller "$SCRIPT_DIR/agent.spec" --distpath "$DIST_DIR" --workpath "$BUILD_DIR" --noconfirm

if [ ! -d "$DIST_DIR/$APP_NAME" ]; then
  echo "Fehler: $DIST_DIR/$APP_NAME wurde nicht erzeugt." >&2
  exit 1
fi

echo "==> Bereite DMG-Inhalt vor…"
rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"
cp -R "$DIST_DIR/$APP_NAME" "$STAGING_DIR/"
ln -s /Applications "$STAGING_DIR/Applications"

echo "==> Erzeuge ${DMG_NAME}…"
rm -f "$DIST_DIR/$DMG_NAME"
hdiutil create -volname "Rapport Agent" \
  -srcfolder "$STAGING_DIR" \
  -ov -format UDZO \
  "$DIST_DIR/$DMG_NAME"

rm -rf "$STAGING_DIR"

echo "==> Fertig: $DIST_DIR/$DMG_NAME"
