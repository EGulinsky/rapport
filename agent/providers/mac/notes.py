"""macOS NotesProvider — ported 1:1 from notes_bridge.py's JXA script."""
from __future__ import annotations

import json
import subprocess
from typing import Any

from agent.providers.base import NotesProvider

_JXA_LIST_NOTES = """
const app = Application('Notes')
app.includeStandardAdditions = true
const notes = app.notes()
const result = notes.map(n => {
    try {
        return {
            id: n.id(),
            name: n.name() || '',
            body: n.plaintext() || '',
            date: n.modificationDate() ? n.modificationDate().toISOString() : '',
            creationDate: n.creationDate() ? n.creationDate().toISOString() : ''
        }
    } catch(e) {
        return {id: '', name: '', body: '', date: ''}
    }
})
JSON.stringify(result)
"""

_JXA_COUNT_NOTES = "Application('Notes').notes.length"


class MacNotesProvider(NotesProvider):
    def list_notes(self) -> list[dict[str, Any]]:
        result = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", _JXA_LIST_NOTES],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "osascript failed")
        return json.loads(result.stdout.strip())

    def health(self) -> dict[str, Any]:
        result = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", _JXA_COUNT_NOTES],
            capture_output=True, text=True, timeout=10,
        )
        return {"ok": result.returncode == 0}
