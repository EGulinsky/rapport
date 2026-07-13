"""
Backup: creates timestamped snapshots on the host via the Rapport Agent.

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
import tempfile
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agent_client import agent_get, agent_post
from app.database import DATABASE_URL, get_db, SessionLocal, set_session_user
from app import models
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/api/backup", tags=["backup"])

_DB_FILE = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
DB_PATH = os.path.abspath(_DB_FILE)
FERNET_KEY_PATH = os.path.join(os.path.dirname(DB_PATH), "fernet.key")
DB_ENTRY_NAME = "jobtracker.db"
KEY_ENTRY_NAME = "fernet.key"


class BackupSettings(BaseModel):
    enabled: bool
    backup_folder: str | None = None
    frequency_hours: int = 24
    keep_count: int = 7


def _get_or_create(db: Session, user_id: int) -> models.BackupConfig:
    cfg = db.query(models.BackupConfig).first()
    if not cfg:
        cfg = models.BackupConfig(user_id=user_id)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


async def _list_backups(db: Session, folder: str) -> list[dict]:
    try:
        resp = await agent_get(db, "/backup/backups", params={"folder": folder}, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return []


async def do_backup(user_id: int) -> dict:
    """Read DB, send to the agent, return {success, filename, error}."""
    db = SessionLocal()
    try:
        set_session_user(db, user_id)
        cfg = _get_or_create(db, user_id)
        if not cfg.enabled or not cfg.backup_folder:
            return {"success": False, "error": "Backup nicht konfiguriert oder deaktiviert"}

        # Read DB via sqlite3 backup API (safe even while in use)
        src = sqlite3.connect(DB_PATH)
        tmp = sqlite3.connect(":memory:")
        src.backup(tmp)
        src.close()
        tmp_path = os.path.join(tempfile.gettempdir(), "_jobtracker_backup_tmp.db")
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
        filename = f"rapport_backup_{ts}.zip"

        resp = await agent_post(db, "/backup/backup-write", json={
            "folder": cfg.backup_folder,
            "filename": filename,
            "data_b64": data_b64,
            "keep_count": cfg.keep_count,
        })
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
async def backup_status(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    cfg = _get_or_create(db, current_user.id)
    backups = []
    if cfg.backup_folder:
        backups = await _list_backups(db, cfg.backup_folder)
    return {
        "enabled": cfg.enabled,
        "backup_folder": cfg.backup_folder,
        "frequency_hours": cfg.frequency_hours,
        "keep_count": cfg.keep_count,
        "last_backup": cfg.last_backup.isoformat() if cfg.last_backup else None,
        "backups": backups,
    }


@router.post("/settings")
def save_settings(
    body: BackupSettings,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    cfg = _get_or_create(db, current_user.id)
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
async def run_backup(current_user: models.User = Depends(get_current_user)):
    result = await do_backup(current_user.id)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error", "Backup fehlgeschlagen"))
    return result


@router.get("/pick-folder")
async def pick_folder(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    try:
        resp = await agent_get(db, "/files/pick-folder", timeout=65)
        data = resp.json()
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail=data.get("error", "Kein Ordner ausgewählt"))
        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Agent nicht erreichbar: {e}")


def _apply_restore(data: bytes, filename: str) -> dict:
    """Write backup bytes into the live DB (+ fernet.key if bundled). Shared by
    both restore paths (folder-scan lookup and direct-file picker) — restore
    works regardless of whether automatic backups are configured/enabled,
    since it only needs the raw bytes of a chosen file."""
    from app.database import engine

    # New backups are a zip bundle (DB + fernet.key); older backups are a raw
    # .db file (pre-bundle) — support restoring both for backward compatibility.
    db_bytes = data
    key_bytes: bytes | None = None
    if filename.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            db_bytes = zf.read(DB_ENTRY_NAME)
            if KEY_ENTRY_NAME in zf.namelist():
                key_bytes = zf.read(KEY_ENTRY_NAME)

    tmp_path = os.path.join(tempfile.gettempdir(), "_jobtracker_restore.db")
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

    return {"success": True, "filename": filename}


async def _read_agent_file(db: Session, path: str) -> bytes:
    resp = await agent_get(db, "/backup/backup-read", params={"path": path})
    if resp.status_code != 200:
        raise HTTPException(status_code=500, detail="Backup-Datei konnte nicht gelesen werden")
    return base64.b64decode(resp.json()["data_b64"])


class RestoreRequest(BaseModel):
    filename: str
    folder: str


@router.post("/restore")
async def restore_backup(
    body: RestoreRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    backups = await _list_backups(db, body.folder)
    target = next((b for b in backups if b["name"] == body.filename), None)
    if not target:
        raise HTTPException(status_code=404, detail="Backup-Datei nicht gefunden")

    data = await _read_agent_file(db, target["path"])
    return _apply_restore(data, body.filename)


class RestoreFileRequest(BaseModel):
    path: str


@router.get("/pick-file")
async def pick_file(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Native macOS file picker for a single backup file — manual restore path
    that works without any backup_folder/enabled configuration at all."""
    try:
        resp = await agent_get(db, "/files/pick-file", params={"extensions": "zip,db"}, timeout=65)
        data = resp.json()
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail=data.get("error", "Keine Datei ausgewählt"))
        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Agent nicht erreichbar: {e}")


@router.post("/restore-file")
async def restore_from_file(
    body: RestoreFileRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Manual restore from an arbitrary, freely picked file path — independent
    of the automatic-backup settings (no backup_folder/enabled required)."""
    if not body.path:
        raise HTTPException(status_code=400, detail="Kein Pfad angegeben")
    data = await _read_agent_file(db, body.path)
    filename = body.path.rsplit("/", 1)[-1]
    return _apply_restore(data, filename)
