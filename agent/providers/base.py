"""OS-neutral interfaces. Each module (files/notes/calls) is implemented once
per platform behind these — the HTTP layer, auth and the JobTracker backend
never see which OS they're talking to. Only agent/providers/mac/* exists
today; a future agent/providers/windows/* implements the same interfaces
without touching anything else.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class FilesProvider(ABC):
    """Native folder/file pickers and 'reveal in file manager' — the only
    files-related operations that are actually OS-specific. Plain file I/O
    (read/write/list bytes) is the same on every OS and lives directly in the
    files router, not behind this interface."""

    @abstractmethod
    def pick_folder(self, prompt: str) -> str | None: ...

    @abstractmethod
    def pick_file(self, prompt: str, extensions: list[str]) -> str | None: ...

    @abstractmethod
    def open_path(self, path: str) -> None: ...


class NotesProvider(ABC):
    @abstractmethod
    def list_notes(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    def health(self) -> dict[str, Any]: ...


class CallsProvider(ABC):
    @abstractmethod
    def list_calls(self, since_days: int, source: str = "all") -> list[dict[str, Any]]: ...

    @abstractmethod
    def health(self) -> dict[str, Any]: ...
