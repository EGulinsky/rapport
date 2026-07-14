"""Picks the provider set for the current platform. This is the only place
that needs to change when a new platform is added — everything
above (routers, auth, main.py) stays untouched."""
from __future__ import annotations

from agent.config import platform_name
from agent.providers.base import CallsProvider, FilesProvider, NotesProvider


def make_files_provider() -> FilesProvider:
    system = platform_name()
    if system == "Darwin":
        from agent.providers.mac.files import MacFilesProvider
        return MacFilesProvider()
    elif system == "Windows":
        from agent.providers.windows.files import WindowsFilesProvider
        return WindowsFilesProvider()
    elif system == "Linux":
        from agent.providers.linux.files import LinuxFilesProvider
        return LinuxFilesProvider()
    raise NotImplementedError(f"No FilesProvider for {system}")


def make_notes_provider() -> NotesProvider:
    system = platform_name()
    if system == "Darwin":
        from agent.providers.mac.notes import MacNotesProvider
        return MacNotesProvider()
    elif system == "Windows":
        from agent.providers.windows.notes import WindowsNotesProvider
        return WindowsNotesProvider()
    elif system == "Linux":
        from agent.providers.linux.notes import LinuxNotesProvider
        return LinuxNotesProvider()
    raise NotImplementedError(f"No NotesProvider for {system}")


def make_calls_provider() -> CallsProvider:
    system = platform_name()
    if system == "Darwin":
        from agent.providers.mac.calls import MacCallsProvider
        return MacCallsProvider()
    elif system == "Windows":
        from agent.providers.windows.calls import WindowsCallsProvider
        return WindowsCallsProvider()
    elif system == "Linux":
        from agent.providers.linux.calls import LinuxCallsProvider
        return LinuxCallsProvider()
    raise NotImplementedError(f"No CallsProvider for {system}")
