"""macOS LaunchAgent self-registration — lets the .app register itself to
start at login and restart on crash (KeepAlive), so opening the app once is
the entire "install" step. Windows equivalent (Task Scheduler / Service)
would live in a sibling module behind the same three functions.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from agent.config import app_data_dir

PLIST_LABEL = "com.jobtracker.agent"


def plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{PLIST_LABEL}.plist"


def is_registered() -> bool:
    return plist_path().exists()


def _plist_contents(executable_path: str) -> str:
    log_dir = app_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{PLIST_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{executable_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{log_dir / "agent.log"}</string>
    <key>StandardErrorPath</key>
    <string>{log_dir / "agent.err.log"}</string>
</dict>
</plist>
"""


def register(executable_path: str) -> None:
    """Idempotent: writes the plist and loads it via launchd. Safe to call
    even if already registered (launchctl load on an already-loaded label is
    a no-op error we can ignore)."""
    path = plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_plist_contents(executable_path))
    subprocess.run(["launchctl", "load", "-w", str(path)], capture_output=True, timeout=15)


def unregister() -> None:
    path = plist_path()
    if path.exists():
        subprocess.run(["launchctl", "unload", "-w", str(path)], capture_output=True, timeout=15)
        path.unlink(missing_ok=True)
