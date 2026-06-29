"""
GET /api/startup-check  — checks all local bridges and external connections.
Returns a list of check results, each with {name, ok, message}.
"""
from __future__ import annotations

import asyncio
import os
from typing import Optional

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app import models

router = APIRouter(prefix="/api", tags=["startup"])

FILES_BRIDGE  = os.getenv("FILES_BRIDGE_URL",  "http://host.docker.internal:9998")
NOTES_BRIDGE  = "http://host.docker.internal:9999"
CALLS_BRIDGE  = "http://host.docker.internal:9997"


async def _http_ok(url: str, timeout: float = 3.0) -> tuple[bool, str]:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(url)
            return r.status_code < 500, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)[:80]


async def _check_files_bridge() -> dict:
    ok, msg = await _http_ok(f"{FILES_BRIDGE}/health")
    return {"name": "Files Bridge", "group": "bridges", "ok": ok,
            "message": None if ok else f"Nicht erreichbar: {msg}"}


async def _check_notes_bridge() -> dict:
    ok, msg = await _http_ok(f"{NOTES_BRIDGE}/notes")
    return {"name": "Notes Bridge", "group": "bridges", "ok": ok,
            "message": None if ok else f"Nicht erreichbar: {msg}"}


async def _check_calls_bridge() -> dict:
    ok, msg = await _http_ok(f"{CALLS_BRIDGE}/health")
    return {"name": "Calls Bridge", "group": "bridges", "ok": ok,
            "message": None if ok else f"Nicht erreichbar: {msg}"}


def _check_google(db: Session) -> dict:
    cfg = db.query(models.GoogleSync).first()
    if not cfg or not cfg.refresh_token_enc:
        return {"name": "Google (Gmail/GCal)", "group": "connections", "ok": False,
                "message": "Nicht verbunden — bitte in Einstellungen verbinden"}
    return {"name": "Google (Gmail/GCal)", "group": "connections", "ok": True, "message": None}


def _check_icloud(db: Session) -> dict:
    cfg = db.query(models.ICloudSync).first()
    if not cfg or not cfg.apple_id:
        return {"name": "iCloud", "group": "connections", "ok": False,
                "message": "Nicht konfiguriert — bitte in Einstellungen einrichten"}
    return {"name": "iCloud", "group": "connections", "ok": True, "message": None}


def _check_ai(db: Session) -> dict:
    cfg = db.query(models.AiSettings).first()
    if not cfg or not cfg.api_key_enc:
        return {"name": "AI (Anthropic/OpenAI)", "group": "connections", "ok": False,
                "message": "Kein API-Key konfiguriert — AI-Funktionen nicht verfügbar"}
    return {"name": "AI (Anthropic/OpenAI)", "group": "connections", "ok": True, "message": None}


def _check_files_config(db: Session) -> dict:
    cfg = db.query(models.FilesConfig).first()
    if not cfg or not cfg.enabled or not cfg.folder:
        return {"name": "Lokale Dateien", "group": "connections", "ok": False,
                "message": "Kein Ordner konfiguriert — in Einstellungen einrichten"}
    return {"name": "Lokale Dateien", "group": "connections", "ok": True, "message": None}


@router.get("/startup-check")
async def startup_check(db: Session = Depends(get_db)):
    # Bridges in parallel
    bridge_results = await asyncio.gather(
        _check_files_bridge(),
        _check_notes_bridge(),
        _check_calls_bridge(),
    )

    # Connection checks (sync, fast)
    connection_results = [
        _check_google(db),
        _check_icloud(db),
        _check_ai(db),
        _check_files_config(db),
    ]

    all_checks = list(bridge_results) + connection_results
    return {
        "checks": all_checks,
        "all_ok": all(c["ok"] for c in all_checks),
        "errors": [c for c in all_checks if not c["ok"]],
    }
