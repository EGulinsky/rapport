from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from agent.providers.base import NotesProvider

router = APIRouter(prefix="/notes", tags=["notes"])


def get_notes_provider() -> NotesProvider:  # overridden in main.py
    raise NotImplementedError


@router.get("")
def list_notes(provider: NotesProvider = Depends(get_notes_provider)):
    try:
        return provider.list_notes()
    except Exception as e:
        raise HTTPException(500, str(e))
