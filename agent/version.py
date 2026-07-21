"""The agent's own version — baked into the frozen binary as a bundled
resource file at build time (see packaging/agent*.spec + build_dmg.sh /
build_windows.ps1 / build_linux.sh, all of which pass the release version
through an AGENT_VERSION env var), not edited by hand here. That way there
is exactly one place a human sets the number — the build script's version
argument — with no risk of this file drifting out of sync with what the
DMG/zip/tarball is actually named.

A `python -m agent.main` / `-m agent.tray` dev run is never frozen and has
no such bundled resource, hence the "dev" fallback.
"""
from __future__ import annotations

import sys
from pathlib import Path

_FALLBACK_VERSION = "dev"


def _candidate_paths() -> list[Path]:
    """Onedir Windows/Linux builds put bundled datas right next to the
    executable (sys._MEIPASS). A macOS .app BUNDLE is different: PyInstaller
    6.x moves non-executable resources out to Contents/Resources (Apple's
    code-signing conventions require executables and resources to live in
    separate directories) and leaves Contents/MacOS with nothing but the
    binary itself — hardware-verified against a real built .app, where a
    plain `_MEIPASS / "VERSION"` lookup silently found nothing."""
    meipass = Path(getattr(sys, "_MEIPASS", "."))
    exe_dir = Path(sys.executable).resolve().parent
    return [meipass / "VERSION", exe_dir.parent / "Resources" / "VERSION"]


def _read_bundled_version() -> str:
    if not getattr(sys, "frozen", False):
        return _FALLBACK_VERSION
    for path in _candidate_paths():
        try:
            value = path.read_text().strip()
            if value:
                return value
        except OSError:
            continue
    return _FALLBACK_VERSION


__version__ = _read_bundled_version()
