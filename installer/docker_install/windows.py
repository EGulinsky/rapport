"""Windows: Docker Desktop, installed via its documented silent-install
flags (install --quiet --accept-license) — still triggers a UAC elevation
prompt (unavoidable for installing privileged virtualization software),
but no further interactive setup-wizard clicks.
"""
from __future__ import annotations

import platform
import subprocess
import tempfile
import time
from pathlib import Path

import requests

from installer.docker_check import docker_daemon_running

_INSTALLER_URLS = {
    "ARM64": "https://desktop.docker.com/win/main/arm64/Docker Desktop Installer.exe",
    "AMD64": "https://desktop.docker.com/win/main/amd64/Docker Desktop Installer.exe",
}

# Docker Desktop's installer returns this exit code when a restart is
# required to finish (e.g. WSL2 was just enabled for the first time) —
# surfaced distinctly so it isn't treated as a generic failure.
_REBOOT_REQUIRED_EXIT_CODE = 3010

_DOCKER_DESKTOP_EXE = Path(r"C:\Program Files\Docker\Docker\Docker Desktop.exe")


def _installer_url() -> str:
    return _INSTALLER_URLS.get(platform.machine().upper(), _INSTALLER_URLS["AMD64"])


def install_docker() -> bool:
    print("Docker not found — downloading Docker Desktop for Windows...")
    with tempfile.TemporaryDirectory() as tmp:
        installer_path = Path(tmp) / "Docker Desktop Installer.exe"
        try:
            resp = requests.get(_installer_url(), stream=True, timeout=300)
            resp.raise_for_status()
            with installer_path.open("wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    f.write(chunk)
        except requests.RequestException as e:
            print(f"Download failed: {e}")
            return False

        print("Installing Docker Desktop (you may see a Windows admin-permission prompt)...")
        result = subprocess.run(
            [str(installer_path), "install", "--quiet", "--accept-license"],
            timeout=600,
        )
        if result.returncode == _REBOOT_REQUIRED_EXIT_CODE:
            print(
                "Docker Desktop needs your computer to restart to finish installing "
                "(this happens the first time WSL2 is enabled). Please restart, "
                "then run this installer again."
            )
            return False
        if result.returncode != 0:
            print(f"Docker Desktop installation failed (exit code {result.returncode}).")
            return False

    print("Starting Docker Desktop...")
    if _DOCKER_DESKTOP_EXE.exists():
        subprocess.Popen([str(_DOCKER_DESKTOP_EXE)])
    return _wait_for_daemon()


def _wait_for_daemon(attempts: int = 30, interval_seconds: float = 3.0) -> bool:
    for _ in range(attempts):
        if docker_daemon_running():
            return True
        time.sleep(interval_seconds)
    return False
