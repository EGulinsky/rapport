"""Backup file storage on the host — opaque bytes in, opaque bytes out. The
rapport backend decides content/format (DB+fernet.key zip bundle); this
module only knows about files on disk."""
from __future__ import annotations

import base64
import pathlib

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/backup", tags=["backup"])

BACKUP_EXTS = {".db", ".zip"}


@router.get("/backups")
def list_backups(folder: str = Query(...)):
    if not folder or not pathlib.Path(folder).is_dir():
        return []
    target_dir = pathlib.Path(folder)
    backups = []
    for f in sorted(target_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if f.is_file() and f.suffix in BACKUP_EXTS:
            st = f.stat()
            backups.append({"name": f.name, "path": str(f), "modified": st.st_mtime, "size": st.st_size})
    return backups


@router.get("/backup-read")
def read_backup(path: str = Query(...)):
    if not path or not pathlib.Path(path).is_file():
        raise HTTPException(404, f"Datei nicht gefunden: {path}")
    data = pathlib.Path(path).read_bytes()
    return {"data_b64": base64.b64encode(data).decode(), "name": pathlib.Path(path).name}


class BackupWriteRequest(BaseModel):
    folder: str
    filename: str
    data_b64: str
    keep_count: int = 7


@router.post("/backup-write")
def write_backup(body: BackupWriteRequest):
    if not body.folder or not body.filename or not body.data_b64:
        raise HTTPException(400, "folder, filename und data_b64 erforderlich")

    target_dir = pathlib.Path(body.folder)
    target_dir.mkdir(parents=True, exist_ok=True)
    data = base64.b64decode(body.data_b64)
    (target_dir / body.filename).write_bytes(data)

    # Rotation: keep only the newest keep_count backup files
    backups = sorted(
        [f for f in target_dir.iterdir() if f.suffix in BACKUP_EXTS and f.is_file()],
        key=lambda f: f.stat().st_mtime,
    )
    for old in backups[:-body.keep_count]:
        old.unlink(missing_ok=True)

    return {"success": True, "filename": body.filename}
