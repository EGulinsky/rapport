"""Resolves the bundled compose template (with the version this installer
was built for baked in) and writes it to a per-OS app-data location, ready
for `docker compose -f <path> up -d`.
"""
from __future__ import annotations

import sys
from pathlib import Path

from installer.config import app_data_dir
from installer.version import INSTALLER_VERSION

_TEMPLATE_PLACEHOLDER = "__VERSION__"
_DEV_VERSION = "0.0.0-dev"


def _template_path() -> Path:
    """Location of the bundled compose_template.yml — works both from a
    normal source checkout and from a PyInstaller onedir bundle
    (sys._MEIPASS), which is where PyInstaller's `datas=` entries land."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "compose_template.yml"  # type: ignore[attr-defined]
    return Path(__file__).parent / "compose_template.yml"


def resolved_compose_text(version: str = INSTALLER_VERSION) -> str:
    # Unpackaged dev checkouts never have a real stamped version — fall
    # back to :latest so `python -m installer.main` stays usable locally.
    tag = "latest" if version == _DEV_VERSION else version
    template = _template_path().read_text()
    return template.replace(_TEMPLATE_PLACEHOLDER, tag)


def write_compose_file() -> Path:
    path = app_data_dir() / "docker-compose.yml"
    path.write_text(resolved_compose_text())
    return path
