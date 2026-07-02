"""
Backup: creates timestamped snapshots on the host Mac via files_bridge.

Backups are a zip bundle of the SQLite DB *and* fernet.key — the key lives
outside the DB (data/fernet.key) and is never itself stored in the DB, so a
DB-only backup would restore application data but leave every encrypted
field (AI API key, iCloud app password, Google client secret, Maps API key)
permanently undecryptable on a fresh machine/volume. Bundling both keeps a
backup fully self-contained. Older plain-.db backups (pre-bundle) remain
listable and restorable for backward compatibility.

GET  /api/backup/status    — config + list of existing backups
POST /api/backup/settings  — save config
POST /api/backup/run       — trigger backup now
"""
from __future__ import annotations

import base64
import io
import os
import sqlite3
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app import models

router = APIRouter(prefix="/api/backup", tags=["backup"])

FILES_BRIDGE_URL = os.getenv("FILES_BRIDGE_URL", "http://host.docker.internal:9998")
DB_PATH = "/app/data/jobtracker.db"
FERNET_KEY_PATH = "/app/data/fernet.key"
DB_ENTRY_NAME = "jobtracker.db"
KEY_ENTRY_NAME = "fernet.key"


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
            db_bytes = f.read()
        os.unlink(tmp_path)

        # Bundle DB + fernet.key into one zip so a backup is self-contained —
        # the key isn't stored in the DB, so a DB-only backup would leave
        # encrypted fields undecryptable after a restore onto a fresh volume.
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(DB_ENTRY_NAME, db_bytes)
            if os.path.exists(FERNET_KEY_PATH):
                zf.write(FERNET_KEY_PATH, KEY_ENTRY_NAME)
        data_b64 = base64.b64encode(zip_buf.getvalue()).decode()
        ts = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        filename = f"jobtracker_backup_{ts}.zip"

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


@router.get("/pick-folder")
async def pick_folder():
    import httpx
    try:
        async with httpx.AsyncClient(timeout=65) as client:
            resp = await client.get(f"{FILES_BRIDGE_URL}/pick-folder")
        data = resp.json()
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail=data.get("error", "Kein Ordner ausgewählt"))
        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"files_bridge nicht erreichbar: {e}")


class RestoreRequest(BaseModel):
    filename: str
    folder: str


@router.post("/restore")
async def restore_backup(body: RestoreRequest, db: Session = Depends(get_db)):
    import httpx
    from app.database import engine

    backups = await _list_backups(body.folder)
    target = next((b for b in backups if b["name"] == body.filename), None)
    if not target:
        raise HTTPException(status_code=404, detail="Backup-Datei nicht gefunden")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{FILES_BRIDGE_URL}/backup-read", params={"path": target["path"]})
    if resp.status_code != 200:
        raise HTTPException(status_code=500, detail="Backup-Datei konnte nicht gelesen werden")

    data = base64.b64decode(resp.json()["data_b64"])

    # New backups are a zip bundle (DB + fernet.key); older backups are a raw
    # .db file (pre-bundle) — support restoring both for backward compatibility.
    db_bytes = data
    key_bytes: bytes | None = None
    if body.filename.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            db_bytes = zf.read(DB_ENTRY_NAME)
            if KEY_ENTRY_NAME in zf.namelist():
                key_bytes = zf.read(KEY_ENTRY_NAME)

    tmp_path = "/tmp/_jobtracker_restore.db"
    with open(tmp_path, "wb") as f:
        f.write(db_bytes)

    # Copy backup into live DB via sqlite3 backup API
    src = sqlite3.connect(tmp_path)
    dst = sqlite3.connect(DB_PATH)
    src.backup(dst)
    src.close()

    # Restore fernet.key alongside the DB — key and ciphertext must always
    # travel together, otherwise encrypted fields become undecryptable.
    if key_bytes is not None:
        with open(FERNET_KEY_PATH, "wb") as f:
            f.write(key_bytes)
    dst.close()
    os.unlink(tmp_path)

    # Reset SQLAlchemy connection pool so next requests use restored data
    engine.dispose()

    return {"success": True, "filename": body.filename}
