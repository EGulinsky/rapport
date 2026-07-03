"""
GET /api/startup-check  — checks the JobTracker Agent and external connections.
Returns a list of check results, each with {name, ok, message}.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agent_client import agent_health
from app.database import get_db
from app import models

router = APIRouter(prefix="/api", tags=["startup"])


async def _check_agent_modules(db: Session) -> list[dict]:
    """One /health call to the agent, split back into the same three rows
    (Files/Notes/Calls) the old three-bridge checks produced — the frontend
    banner doesn't need to change."""
    health = await agent_health(db)
    if not health["reachable"]:
        detail = health.get("error", "nicht erreichbar")
        return [
            {"name": "Agent: Dateien", "group": "bridges", "ok": False, "message": f"Agent nicht erreichbar: {detail}"},
            {"name": "Agent: Notizen", "group": "bridges", "ok": False, "message": f"Agent nicht erreichbar: {detail}"},
            {"name": "Agent: Anrufe", "group": "bridges", "ok": False, "message": f"Agent nicht erreichbar: {detail}"},
        ]

    modules = health.get("modules", {})
    results = []
    for key, label in (("files", "Agent: Dateien"), ("notes", "Agent: Notizen"), ("calls", "Agent: Anrufe")):
        mod = modules.get(key, {})
        ok = bool(mod.get("ok"))
        results.append({
            "name": label, "group": "bridges", "ok": ok,
            "message": None if ok else (mod.get("error") or "Nicht verfügbar"),
        })
    return results


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
    if not cfg or not cfg.enabled or not cfg.folder_path:
        return {"name": "Lokale Dateien", "group": "connections", "ok": False,
                "message": "Kein Ordner konfiguriert — in Einstellungen einrichten"}
    return {"name": "Lokale Dateien", "group": "connections", "ok": True, "message": None}


@router.get("/startup-check")
async def startup_check(db: Session = Depends(get_db)):
    bridge_results = await _check_agent_modules(db)

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
