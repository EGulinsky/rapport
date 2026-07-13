"""Cross-platform service registration — start at login, restart on crash.

macOS: launchd LaunchAgent (existing launchd.py)
Windows: Task Scheduler
Linux: systemd user service

All three follow the same interface: is_registered(), register(), unregister().
"""
from __future__ import annotations

import platform


def _get_impl():
    system = platform.system()
    if system == "Darwin":
        from agent import launchd
        return launchd
    elif system == "Windows":
        from agent import task_scheduler
        return task_scheduler
    elif system == "Linux":
        from agent import systemd_service
        return systemd_service
    raise NotImplementedError(f"No service registration for {system}")


def is_registered() -> bool:
    return _get_impl().is_registered()


def register(command: str, args: list[str] | None = None) -> None:
    _get_impl().register(command, args)


def unregister() -> None:
    _get_impl().unregister()
