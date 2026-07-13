"""Windows NotesProvider — not available (Apple Notes is macOS-only).

This is a stub that returns empty results. If Windows users want notes
integration in the future, we could support OneNote via Microsoft Graph API.
"""
from __future__ import annotations

from typing import Any

from agent.providers.base import NotesProvider


class WindowsNotesProvider(NotesProvider):
    def list_notes(self) -> list[dict[str, Any]]:
        return []

    def health(self) -> dict[str, Any]:
        return {"ok": False, "error": "Apple Notes not available on Windows"}
