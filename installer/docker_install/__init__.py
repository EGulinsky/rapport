"""Cross-platform Docker install dispatch for the macOS/Linux Python
installer flow — mirrors agent/service.py's per-OS dispatcher shape.

macOS: Docker Desktop, MDM-style silent install (docker_install/macos.py)
Linux: Docker Engine via the get.docker.com convenience script (docker_install/linux.py)

Windows isn't dispatched here at all: the Windows installer is a WiX
MSI/Burn bootstrapper (installer/packaging/windows-wix/) that chains the
official Docker Desktop installer as a prerequisite package directly, no
Python involved. See installer/README.md.
"""
from __future__ import annotations

import platform


def _get_impl():
    system = platform.system()
    if system == "Darwin":
        from installer.docker_install import macos
        return macos
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
