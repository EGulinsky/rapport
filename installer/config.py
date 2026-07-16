"""Per-OS standard app-data location for the resolved compose file —
mirrors agent/config.py's app_data_dir() pattern (same reasoning: survives
app updates, doesn't clutter the repo, matches where real apps on each OS
keep their own config).
"""
from __future__ import annotations

import os
import platform
from pathlib import Path


def app_data_dir() -> Path:
    system = platform.system()
    if system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    elif system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    path = base / "RapportInstaller"
    path.mkdir(parents=True, exist_ok=True)
    return path
