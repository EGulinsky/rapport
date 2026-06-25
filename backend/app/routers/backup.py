"""
Backup: creates timestamped SQLite snapshots on the host Mac via files_bridge.

GET  /api/backup/status    — config + list of existing backups
POST /api/backup/settings  — save config
POST /api/backup/run       — trigger backup now
"""
from __future__ import annotations

import base64
import os
import sqlite3
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app import models

router = APIRouter(prefix="/api/backup", tags=["backup"])

FILES_BRIDGE_URL = os.getenv("FILES_BRIDGE_URL", "http://host.docker.internal:9998")
DB_PATH = "/app/data/jobtracker.db"


class BackupSettings(BaseModel):
    enabled: bool
    backup_folder: str | None = None
    frequency_hours: int = 24
    keep_count: int = 7


def _get_or_create(db: Session) -> models.BackupConfig:
    cfg = db.query(models.BackupConfig).first()
    if not cfg:
        cfg = models.BackupConfig()
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


async def _list_backups(folder: str) -> list[dict]:
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{FILES_BRIDGE_URL}/backups", params={"folder": folder})
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass
    return []


async def do_backup() -> dict:
    """Read DB, send to bridge, return {success, filename, error}."""
    import httpx
    db = SessionLocal()
    try:
        cfg = _get_or_create(db)
        if not cfg.enabled or not cfg.backup_folder:
            return {"success": False, "error": "Backup nicht konfiguriert oder deaktiviert"}

        # Read DB via sqlite3 backup API (safe even while in use)
        src = sqlite3.connect(DB_PATH)
        tmp = sqlite3.connect(":memory:")
        src.backup(tmp)
        src.close()
        tmp_path = "/tmp/_jobtracker_backup_tmp.db"
        disk = sqlite3.connect(tmp_path)
        tmp.backup(disk)
        disk.close()
        tmp.close()
        with open(tmp_path, "rb") as f:
            data = f.read()
        os.unlink(tmp_path)

        data_b64 = base64.b64encode(data).decode()
        ts = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        filename = f"jobtracker_backup_{ts}.db"

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{FILES_BRIDGE_URL}/backup-write",
                json={
                    "folder": cfg.backup_folder,
                    "filename": filename,
                    "data_b64": data_b64,
                    "keep_count": cfg.keep_count,
                },
            )
            if resp.status_code != 200:
                return {"success": False, "error": resp.text}

        cfg.last_backup = datetime.now(timezone.utc)
        db.commit()
        return {"success": True, "filename": filename}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        db.close()


@router.get("/status")
async def backup_status(db: Session = Depends(get_db)):
    cfg = _get_or_create(db)
    backups = []
    if cfg.backup_folder:
        backups = await _list_backups(cfg.backup_folder)
    return {
        "enabled": cfg.enabled,
        "backup_folder": cfg.backup_folder,
        "frequency_hours": cfg.frequency_hours,
        "keep_count": cfg.keep_count,
        "last_backup": cfg.last_backup.isoformat() if cfg.last_backup else None,
        "backups": backups,
    }


@router.post("/settings")
def save_settings(body: BackupSettings, db: Session = Depends(get_db)):
    cfg = _get_or_create(db)
    cfg.enabled = body.enabled
    cfg.backup_folder = body.backup_folder
    cfg.frequency_hours = max(1, body.frequency_hours)
    cfg.keep_count = max(1, body.keep_count)
    db.commit()
    db.refresh(cfg)
    return {
        "enabled": cfg.enabled,
        "backup_folder": cfg.backup_folder,
        "frequency_hours": cfg.frequency_hours,
        "keep_count": cfg.keep_count,
        "last_backup": cfg.last_backup.isoformat() if cfg.last_backup else None,
    }


@router.post("/run")
async def run_backup():
    result = await do_backup()
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error", "Backup fehlgeschlagen"))
    return result
