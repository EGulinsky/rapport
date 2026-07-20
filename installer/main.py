"""Rapport Installer entry point (macOS/Linux) — a one-shot bootstrap, not
a persistent service (unlike agent/tray.py): Docker Desktop's own
restart-at-login plus docker-compose's `restart: unless-stopped` keep the
app running across reboots once containers are up once, so there's
nothing further for this process to supervise.

Windows has its own installer entirely — a WiX MSI/Burn bootstrapper
(installer/packaging/windows-wix/), not this Python flow at all. See
installer/README.md.

Flow: check Docker -> install it if missing -> write the resolved compose
file -> `docker compose pull && up -d` -> poll /health -> open the browser.
"""
from __future__ import annotations

import subprocess
import sys

from installer.browser import open_app
from installer.compose_writer import write_compose_file
from installer.docker_check import docker_cli_available, docker_cmd_prefix, docker_daemon_running
from installer.docker_install import install_docker
from installer.health import wait_for_healthy


def main() -> int:
    print("Rapport Installer")
    print("==================")

    if not docker_daemon_running():
        if docker_cli_available():
            print("Docker is installed but the daemon isn't running yet.")
        if not install_docker():
            print(
                "\nCouldn't get Docker running automatically. Please install Docker "
                "manually from https://www.docker.com/get-started/ and run this "
                "installer again."
            )
            return 1

    print("Docker is ready.")

    compose_path = write_compose_file()
    prefix = docker_cmd_prefix()

    print("Pulling rapport images (this can take a few minutes the first time)...")
    pull = subprocess.run(prefix + ["compose", "-f", str(compose_path), "pull"])
    if pull.returncode != 0:
        print("Failed to pull rapport images. Check your internet connection and try again.")
        return 1

    print("Starting rapport...")
    up = subprocess.run(prefix + ["compose", "-f", str(compose_path), "up", "-d"])
    if up.returncode != 0:
        print("Failed to start rapport.")
        return 1

    print("Waiting for rapport to be ready...")
    if not wait_for_healthy():
        print("rapport didn't become healthy in time. Check `docker compose logs` for details.")
        return 1

    print("rapport is running — opening in your browser: http://localhost:3000")
    open_app()
    print(
        "\nYou can close this window. rapport keeps running in the background "
        "(managed by Docker) and restarts automatically when your computer restarts."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
