"""macOS: Docker Desktop, installed via its documented MDM-style silent
install path (the same mechanism tools like Jamf use for unattended
deployment) — mounting the official .dmg and running the bundled installer
binary directly with --accept-license, rather than requiring interactive
drag-to-Applications + first-run wizard clicks. Still triggers macOS's own
admin-password prompt once (unavoidable for installing privileged
virtualization software).
"""
from __future__ import annotations

import platform
import re
import subprocess
import tempfile
import time
from pathlib import Path

import requests

from installer.docker_check import docker_daemon_running

_DMG_URLS = {
    "arm64": "https://desktop.docker.com/mac/main/arm64/Docker.dmg",
    "x86_64": "https://desktop.docker.com/mac/main/amd64/Docker.dmg",
}


def _dmg_url() -> str:
    return _DMG_URLS.get(platform.machine(), _DMG_URLS["x86_64"])


def _download(url: str, dest: Path) -> None:
    resp = requests.get(url, stream=True, timeout=300)
    resp.raise_for_status()
    with dest.open("wb") as f:
        for chunk in resp.iter_content(chunk_size=1024 * 1024):
            f.write(chunk)


def _mount_point(attach_output: str) -> str:
    """Parses `hdiutil attach`'s output for the mounted volume path."""
    for line in attach_output.splitlines():
        match = re.search(r"(/Volumes/\S.*)$", line)
        if match:
            return match.group(1).strip()
    raise RuntimeError(f"Could not find mount point in hdiutil output:\n{attach_output}")


def install_docker() -> bool:
    print("Docker not found — downloading Docker Desktop for Mac...")
    with tempfile.TemporaryDirectory() as tmp:
        dmg_path = Path(tmp) / "Docker.dmg"
        try:
            _download(_dmg_url(), dmg_path)
        except requests.RequestException as e:
            print(f"Download failed: {e}")
            return False

        print("Mounting installer...")
        attach = subprocess.run(
            ["hdiutil", "attach", str(dmg_path), "-nobrowse"],
            capture_output=True, text=True, timeout=60,
        )
        if attach.returncode != 0:
            print(f"Failed to mount Docker.dmg: {attach.stderr}")
            return False
        mount_point = _mount_point(attach.stdout)

        try:
            print("Installing Docker Desktop (you may be prompted for your Mac password)...")
            install = subprocess.run(
                ["sudo", f"{mount_point}/Docker.app/Contents/MacOS/install", "--accept-license"],
                timeout=300,
            )
            if install.returncode != 0:
                print("Docker Desktop installation failed.")
                return False
        finally:
            subprocess.run(["hdiutil", "detach", mount_point, "-quiet"], timeout=30)

    print("Starting Docker Desktop...")
    subprocess.run(["open", "-a", "Docker"])
    return _wait_for_daemon()


def _wait_for_daemon(attempts: int = 30, interval_seconds: float = 3.0) -> bool:
    for _ in range(attempts):
        if docker_daemon_running():
            return True
        time.sleep(interval_seconds)
    return False
