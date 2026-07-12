"""Agent configuration: per-OS app-data dir, port, bearer token.

Token is generated once on first run and persisted — the agent and the
rapport backend must share it (pasted into Settings → Agent). Storing it
in the app-data dir (not the repo, not stdout logs) keeps it out of backups
of the codebase.
"""
from __future__ import annotations

import json
import os
import platform
import secrets
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PORT = 9996
CONFIG_FILENAME = "config.json"


def app_data_dir() -> Path:
    """Per-OS standard location for app config — same pattern real macOS/Windows
    apps use, so this survives app updates and doesn't clutter the repo."""
    system = platform.system()
    if system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    elif system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    path = base / "RapportAgent"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class AgentConfig:
    token: str
    port: int = DEFAULT_PORT
    ui_language: str = "de"

    @property
    def path(self) -> Path:
        return app_data_dir() / CONFIG_FILENAME

    def save(self) -> None:
        self.path.write_text(json.dumps(
            {"token": self.token, "port": self.port, "ui_language": self.ui_language}, indent=2,
        ))

    @classmethod
    def load_or_create(cls) -> "AgentConfig":
        path = app_data_dir() / CONFIG_FILENAME
        if path.exists():
            data = json.loads(path.read_text())
            return cls(
                token=data["token"],
                port=data.get("port", DEFAULT_PORT),
                ui_language=data.get("ui_language", "de"),
            )
        cfg = cls(token=secrets.token_urlsafe(32))
        cfg.save()
        return cfg


def platform_name() -> str:
    return platform.system()  # "Darwin" | "Windows" | "Linux"
