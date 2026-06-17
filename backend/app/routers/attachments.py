"""
Attachment storage and download.

Files are stored in /data/attachments/{event_id}/{filename} inside the container.
"""
from __future__ import annotations

import hashlib
import mimetypes
import os
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db, DATABASE_URL
from app import models

router = APIRouter(prefix="/api/attachments", tags=["attachments"])

MAX_INLINE_BYTES = 100 * 1024 * 1024  # 100 MB

_DB_DIR = os.path.dirname(DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", ""))
ATTACHMENTS_ROOT = os.path.join(_DB_DIR, "attachments")


def _attachment_dir(event_id: int) -> str:
    return os.path.join(ATTACHMENTS_ROOT, str(event_id))


def store_attachment(
    db: Session,
    event_id: int,
    filename: str,
    data: bytes,
    source: str = "manual",
    external_id: Optional[str] = None,
    content_type: Optional[str] = None,
) -> models.Attachment:
    """Store attachment bytes on disk and create DB record. Returns the Attachment."""
    size = len(data)

    if size > MAX_INLINE_BYTES:
        # Create PendingMatch instead
        from datetime import date as _date
        ev = db.query(models.Event).get(event_id)
        app_id = ev.application_id if ev else None
        db.add(models.PendingMatch(
            source="attachment",
            external_id=f"attachment_{event_id}_{hashlib.md5(filename.encode()).hexdigest()[:8]}",
            confidence=99,
            event_type="large_attachment",
            datum=_date.today(),
            titel=f"Großer Anhang: {filename}",
            extract=f"Datei {filename} ({size / 1024 / 1024:.1f} MB) ist zu groß für automatische Speicherung.",
            suggested_app_id=app_id,
        ))
        raise ValueError(f"Datei {filename} ist größer als 100 MB und wurde zur manuellen Prüfung weitergeleitet.")

    target_dir = _attachment_dir(event_id)
    os.makedirs(target_dir, exist_ok=True)

    safe_name = os.path.basename(filename)
    target_path = os.path.join(target_dir, safe_name)
    # Avoid overwriting: append counter if needed
    if os.path.exists(target_path):
        base, ext = os.path.splitext(safe_name)
        counter = 1
        while os.path.exists(target_path):
            target_path = os.path.join(target_dir, f"{base}_{counter}{ext}")
            counter += 1
        safe_name = os.path.basename(target_path)

    with open(target_path, "wb") as f:
        f.write(data)

    rel_path = os.path.join(str(event_id), safe_name)
    if not content_type:
        content_type, _ = mimetypes.guess_type(safe_name)

    attachment = models.Attachment(
        event_id=event_id,
        filename=safe_name,
        content_type=content_type,
        size_bytes=size,
        storage_path=rel_path,
        source=source,
        external_id=external_id,
    )
    db.add(attachment)
    return attachment


@router.get("/{attachment_id}/download")
def download_attachment(attachment_id: int, db: Session = Depends(get_db)):
    att = db.query(models.Attachment).get(attachment_id)
    if not att:
        raise HTTPException(404, "Anhang nicht gefunden.")
    full_path = os.path.join(ATTACHMENTS_ROOT, att.storage_path)
    if not os.path.exists(full_path):
        raise HTTPException(404, "Datei nicht mehr vorhanden.")
    return FileResponse(
        full_path,
        media_type=att.content_type or "application/octet-stream",
        filename=att.filename,
    )


@router.post("/{event_id}/upload", status_code=201)
async def upload_attachment(event_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    ev = db.query(models.Event).get(event_id)
    if not ev:
        raise HTTPException(404, "Timeline-Eintrag nicht gefunden.")

    data = await file.read()
    filename = file.filename or "attachment"
    try:
        att = store_attachment(db, event_id, filename, data, source="manual", content_type=file.content_type)
        db.commit()
        db.refresh(att)
    except ValueError as e:
        db.commit()
        raise HTTPException(413, str(e))

    return {
        "id": att.id,
        "filename": att.filename,
        "size_bytes": att.size_bytes,
        "content_type": att.content_type,
    }


@router.delete("/{attachment_id}", status_code=204)
def delete_attachment(attachment_id: int, db: Session = Depends(get_db)):
    att = db.query(models.Attachment).get(attachment_id)
    if not att:
        raise HTTPException(404, "Anhang nicht gefunden.")
    full_path = os.path.join(ATTACHMENTS_ROOT, att.storage_path)
    if os.path.exists(full_path):
        os.remove(full_path)
    db.delete(att)
    db.commit()
