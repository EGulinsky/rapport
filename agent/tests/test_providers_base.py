"""L0 — base.py: the abstract interfaces themselves have no logic, but
NotesProvider/CallsProvider's `platform_limited` property has a concrete
default (False) that concrete providers only override when they're a stub
(see Windows/Linux notes.py/calls.py). Exercised via minimal concrete
subclasses since the base classes are abstract."""
from typing import Any

from agent.providers.base import CallsProvider, FilesProvider, NotesProvider


class _FullFilesProvider(FilesProvider):
    def pick_folder(self, prompt: str) -> str | None:
        return None

    def pick_file(self, prompt: str, extensions: list[str]) -> str | None:
        return None

    def open_path(self, path: str) -> None:
        pass


class _FullNotesProvider(NotesProvider):
    def list_notes(self) -> list[dict[str, Any]]:
        return []

    def health(self) -> dict[str, Any]:
        return {"ok": True}


class _FullCallsProvider(CallsProvider):
    def list_calls(self, since_days: int, source: str = "all") -> list[dict[str, Any]]:
        return []

    def health(self) -> dict[str, Any]:
        return {"ok": True}


class TestPlatformLimitedDefault:
    def test_positiv_notes_provider_default_ist_false(self):
        assert _FullNotesProvider().platform_limited is False

    def test_positiv_calls_provider_default_ist_false(self):
        assert _FullCallsProvider().platform_limited is False


class TestFilesProviderHatKeinPlatformLimited:
    def test_negativ_files_provider_definiert_die_property_nicht(self):
        assert not hasattr(FilesProvider, "platform_limited")
        assert not hasattr(_FullFilesProvider(), "platform_limited")
