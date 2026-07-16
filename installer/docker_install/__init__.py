"""Cross-platform Docker install dispatch — mirrors agent/service.py's
per-OS dispatcher shape.

macOS: Docker Desktop, MDM-style silent install (docker_install/macos.py)
Windows: Docker Desktop, --quiet install (docker_install/windows.py)
Linux: Docker Engine via the get.docker.com convenience script (docker_install/linux.py)
"""
from __future__ import annotations

import platform


def _get_impl():
    system = platform.system()
    if system == "Darwin":
        from installer.docker_install import macos
        return macos
    elif system == "Windows":
        from installer.docker_install import windows
        return windows
    elif system == "Linux":
        from installer.docker_install import linux
        return linux
    raise NotImplementedError(f"No Docker install support for {system}")


def install_docker() -> bool:
    """Attempts a fully scripted, silent Docker install for the current OS.
    Returns True if Docker is confirmed working (docker info succeeds)
    afterward, False otherwise — the implementation itself prints a clear
    diagnostic message before returning False, so the caller (main.py)
    just needs to exit non-zero rather than hang."""
    return _get_impl().install_docker()
