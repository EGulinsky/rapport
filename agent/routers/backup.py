"""Backup file storage on the host — opaque bytes in, opaque bytes out. The
rapport backend decides content/format (DB+fernet.key zip bundle); this
module only knows about files on disk."""
from __future__ import annotations

import base64
import datetime
import pathlib

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/backup", tags=["backup"])

BACKUP_EXTS = {".db", ".zip"}


def _select_files_to_keep(
    files: list[tuple[pathlib.Path, float]],
    keep_hourly: int,
    keep_daily: int,
    keep_weekly: int,
) -> set[pathlib.Path]:
    """Grandfather-father-son retention: a flat "keep newest N" (the original
    scheme) only ever gives a recovery window of N * backup-frequency — with
    the default hourly frequency and keep_count=7, that's 7 hours, which
    turned out to be far too short to recover from a mistake noticed even a
    day later (real incident: mass contact deletion discovered days after
    the fact, with every backup from that day long since rotated out).

    Three tiers, evaluated newest-first:
    - hourly: the keep_hourly most recent files, unconditionally.
    - daily: one file per distinct calendar day (the newest that day) for
      the keep_daily most recent days not already covered by the hourly tier.
    - weekly: one file per distinct ISO (year, week) for the keep_weekly
      most recent weeks not already covered by the tiers above.
    Everything else is rotated out."""
    ordered = sorted(files, key=lambda f: f[1], reverse=True)
    keep: set[pathlib.Path] = set()

    hourly = ordered[:keep_hourly]
    keep.update(p for p, _ in hourly)
    remaining = ordered[keep_hourly:]

    seen_days: dict[datetime.date, pathlib.Path] = {}
    for path, mtime in remaining:
        day = datetime.datetime.fromtimestamp(mtime).date()
        seen_days.setdefault(day, path)
    for day in sorted(seen_days, reverse=True)[:keep_daily]:
        keep.add(seen_days[day])

    remaining = [(p, m) for p, m in remaining if p not in keep]
    seen_weeks: dict[tuple[int, int], pathlib.Path] = {}
    for path, mtime in remaining:
        iso = datetime.datetime.fromtimestamp(mtime).isocalendar()
        week_key = (iso[0], iso[1])
        seen_weeks.setdefault(week_key, path)
    for week_key in sorted(seen_weeks, reverse=True)[:keep_weekly]:
        keep.add(seen_weeks[week_key])

    return keep


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
    keep_count: int = 24
    keep_daily: int = 14
    keep_weekly: int = 8


@router.post("/backup-write")
def write_backup(body: BackupWriteRequest):
    if not body.folder or not body.filename or not body.data_b64:
        raise HTTPException(400, "folder, filename und data_b64 erforderlich")

    target_dir = pathlib.Path(body.folder)
    target_dir.mkdir(parents=True, exist_ok=True)
    data = base64.b64decode(body.data_b64)
    (target_dir / body.filename).write_bytes(data)

    # Rotation: tiered hourly/daily/weekly retention (see _select_files_to_keep)
    files = [(f, f.stat().st_mtime) for f in target_dir.iterdir() if f.suffix in BACKUP_EXTS and f.is_file()]
    keep = _select_files_to_keep(files, body.keep_count, body.keep_daily, body.keep_weekly)
    for path, _ in files:
        if path not in keep:
            path.unlink(missing_ok=True)

    return {"success": True, "filename": body.filename}
