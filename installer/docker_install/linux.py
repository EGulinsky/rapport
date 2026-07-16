"""Linux: Docker Engine (not Docker Desktop — a GUI app isn't needed for a
locally self-hosted service) via the official get.docker.com convenience
script, the same one-liner Docker's own docs recommend for unattended
installs.
"""
from __future__ import annotations

import getpass
import subprocess
import tempfile
import time
from pathlib import Path

import requests

from installer.docker_check import docker_daemon_running

_GET_DOCKER_URL = "https://get.docker.com"


def install_docker() -> bool:
    print("Docker not found — installing Docker Engine...")
    with tempfile.TemporaryDirectory() as tmp:
        script_path = Path(tmp) / "get-docker.sh"
        try:
            resp = requests.get(_GET_DOCKER_URL, timeout=60)
            resp.raise_for_status()
            script_path.write_text(resp.text)
        except requests.RequestException as e:
            print(f"Download failed: {e}")
            return False

        print("Running the official Docker install script (you may be prompted for your sudo password)...")
        result = subprocess.run(["sudo", "sh", str(script_path)], timeout=600)
        if result.returncode != 0:
            print(f"Docker install script failed (exit code {result.returncode}).")
            return False

    # Best-effort: lets a future login session run docker without sudo.
    # This run still falls back to sudo (see docker_check.docker_cmd_prefix)
    # since group membership only takes effect in a new login session.
    subprocess.run(["sudo", "usermod", "-aG", "docker", getpass.getuser()], timeout=30)
    subprocess.run(["sudo", "systemctl", "enable", "--now", "docker"], timeout=30)

    return _wait_for_daemon()


def _wait_for_daemon(attempts: int = 15, interval_seconds: float = 2.0) -> bool:
    for _ in range(attempts):
        if docker_daemon_running(use_sudo=True):
            return True
        time.sleep(interval_seconds)
    return False
