"""Detect whether Docker is installed and the daemon is reachable."""
from __future__ import annotations

import shutil
import subprocess


def docker_cli_available() -> bool:
    return shutil.which("docker") is not None


def docker_daemon_running(use_sudo: bool = False) -> bool:
    """True if `docker info` succeeds — CLI present AND daemon reachable.

    use_sudo=True is for Linux right after a fresh install: the current
    process's group membership hasn't caught up yet (needs a new login
    session), but a privileged `sudo docker info` already works."""
    if not docker_cli_available():
        return False
    cmd = (["sudo"] if use_sudo else []) + ["docker", "info"]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=10)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def docker_cmd_prefix() -> list[str]:
    """The command prefix to use for docker/compose invocations for the
    rest of this run — plain `docker` if the current user can already talk
    to the daemon, `sudo docker` if only the privileged path works (fresh
    Linux installs before the new group membership takes effect)."""
    if docker_daemon_running(use_sudo=False):
        return ["docker"]
    if docker_daemon_running(use_sudo=True):
        return ["sudo", "docker"]
    return ["docker"]  # caller should have already verified Docker works
