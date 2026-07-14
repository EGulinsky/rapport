"""Linux service registration via systemd user service.

Creates a .service unit file in ~/.config/systemd/user/ that runs at
login and restarts on failure.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from agent.config import app_data_dir

SERVICE_NAME = "rapport-agent"


def _service_dir() -> Path:
    path = Path.home() / ".config" / "systemd" / "user"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _service_file() -> Path:
    return _service_dir() / f"{SERVICE_NAME}.service"


def is_registered() -> bool:
    return _service_file().exists()


def _service_content(command: str, args: list[str]) -> str:
    log_dir = app_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    exec_start = command if not args else f"{command} {' '.join(args)}"

    return f"""[Unit]
Description=Rapport Agent
After=network.target

[Service]
Type=simple
ExecStart={exec_start}
Restart=always
RestartSec=5
StandardOutput=append:{log_dir / "agent.log"}
StandardError=append:{log_dir / "agent.err.log"}

[Install]
WantedBy=default.target
"""


def register(command: str, args: list[str] | None = None) -> None:
    """Creates and enables the systemd user service.

    `command` is the executable (frozen binary, or the Python interpreter
    for dev/source runs); `args` (e.g. ["-m", "agent.main"]) are appended to
    ExecStart rather than being embedded in `command`."""
    _service_file().write_text(_service_content(command, args or []))
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, timeout=10)
    subprocess.run(["systemctl", "--user", "enable", SERVICE_NAME], capture_output=True, timeout=10)
    subprocess.run(["systemctl", "--user", "start", SERVICE_NAME], capture_output=True, timeout=10)


def unregister() -> None:
    subprocess.run(["systemctl", "--user", "stop", SERVICE_NAME], capture_output=True, timeout=10)
    subprocess.run(["systemctl", "--user", "disable", SERVICE_NAME], capture_output=True, timeout=10)
    _service_file().unlink(missing_ok=True)
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, timeout=10)
