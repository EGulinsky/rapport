"""Linux NotesProvider — not available (Apple Notes is macOS-only).

This is a stub that returns empty results. If Linux users want notes
integration in the future, we could support GNOME Notes or other
Linux note-taking apps.
"""
from __future__ import annotations

from typing import Any

from agent.providers.base import NotesProvider


class LinuxNotesProvider(NotesProvider):
    @property
    def platform_limited(self) -> bool:
        return True

    def list_notes(self) -> list[dict[str, Any]]:
        return []

    def health(self) -> dict[str, Any]:
        return {"ok": False, "error": "Apple Notes not available on Linux", "platform_limited": True}
