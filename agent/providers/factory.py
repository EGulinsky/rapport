"""Picks the provider set for the current platform. This is the only place
that needs to change when a Windows implementation is added — everything
above (routers, auth, main.py) stays untouched."""
from __future__ import annotations

from agent.config import platform_name
from agent.providers.base import CallsProvider, FilesProvider, NotesProvider


def make_files_provider() -> FilesProvider:
    if platform_name() == "Darwin":
        from agent.providers.mac.files import MacFilesProvider
        return MacFilesProvider()
    raise NotImplementedError(f"Kein FilesProvider für {platform_name()}")


def make_notes_provider() -> NotesProvider:
    if platform_name() == "Darwin":
        from agent.providers.mac.notes import MacNotesProvider
        return MacNotesProvider()
    raise NotImplementedError(f"Kein NotesProvider für {platform_name()}")


def make_calls_provider() -> CallsProvider:
    if platform_name() == "Darwin":
        from agent.providers.mac.calls import MacCallsProvider
        return MacCallsProvider()
    raise NotImplementedError(f"Kein CallsProvider für {platform_name()}")
