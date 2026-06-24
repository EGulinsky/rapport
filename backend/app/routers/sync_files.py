"""
Local-files sync: indexes documents from a configured folder on the host Mac.

Requires files_bridge.py running on the host:
  python3 files_bridge.py          # port 9998

GET  /api/sync/files/status       — bridge reachability + last sync info
POST /api/sync/files              — trigger background sync
POST /api/sync/files/reset        — clear synced-items for local_files source
GET  /api/sync/files/browse       — browse folders/files under root (manual sync)
POST /api/sync/files/attach       — attach a specific file to an application
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime, date as _date, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app import models
from app.routers.sync_common import (
    is_synced, mark_synced, purge_source,
    build_firm_index, find_hint_apps,
    _classify_deterministic, _save_deterministic_event,
    init_progress, update_progress, finish_progress,
    set_batch_result,
)

router = APIRouter(prefix="/api/sync/files", tags=["sync"])

FILES_BRIDGE_URL = os.getenv("FILES_BRIDGE_URL", "http://host.docker.internal:9998")


def _get_cfg(db: Session) -> Optional[models.FilesConfig]:
    return db.query(models.FilesConfig).first()


def _get_or_create_cfg(db: Session) -> models.FilesConfig:
    cfg = _get_cfg(db)
    if not cfg:
        cfg = models.FilesConfig(enabled=True)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


@router.get("/status")
async def files_status(db: Session = Depends(get_db)):
    import httpx
    cfg = _get_or_create_cfg(db)
    reachable = False
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{FILES_BRIDGE_URL}/health")
            reachable = resp.status_code == 200
    except Exception:
        pass
    return {
        "enabled": cfg.enabled,
        "folder_path": cfg.folder_path,
        "last_sync": cfg.last_sync.isoformat() if cfg.last_sync else None,
        "bridge_reachable": reachable,
    }


@router.post("/reset", status_code=204)
def reset_files_sync(db: Session = Depends(get_db)):
    cfg = _get_cfg(db)
    if cfg:
        cfg.last_sync = None
    purge_source(db, "local_files")
    db.commit()


async def _do_local_files() -> dict:
    import httpx
    db = SessionLocal()
    processed = created = skipped = 0
    errors: list[str] = []
    try:
        cfg = db.query(models.FilesConfig).first()
        if not cfg or not cfg.enabled:
            finish_progress("local_files")
            return {"processed": 0, "created": 0, "skipped": 0, "errors": []}
        if not cfg.folder_path:
            finish_progress("local_files")
            return {"processed": 0, "created": 0, "skipped": 0, "errors": ["Kein Ordner konfiguriert."]}

        _, term_to_apps = build_firm_index(db)
        if not term_to_apps:
            finish_progress("local_files")
            return {"processed": 0, "created": 0, "skipped": 0, "errors": []}

        update_progress("local_files", 0, 0, "Dokumente werden geladen…")
        params: dict = {"folder": cfg.folder_path}
        if cfg.last_sync:
            params["since"] = str(cfg.last_sync.timestamp())

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.get(f"{FILES_BRIDGE_URL}/files", params=params)
                if resp.status_code != 200:
                    err = resp.json().get("error", resp.text) if resp.headers.get("content-type", "").startswith("application/json") else resp.text
                    finish_progress("local_files")
                    return {"processed": 0, "created": 0, "skipped": 0, "errors": [f"Bridge-Fehler: {err}"]}
                files = resp.json()
        except Exception as e:
            finish_progress("local_files")
            return {"processed": 0, "created": 0, "skipped": 0, "errors": [
                f"Files Bridge nicht erreichbar ({e}). Starte files_bridge.py auf deinem Mac."
            ]}

        total = len(files)
        update_progress("local_files", 0, total, f"{total} Dateien gefunden")

        for i, file_info in enumerate(files):
            update_progress("local_files", i, total, f"Datei {i + 1}/{total}: {file_info.get('name', '')}")

            path: str = file_info.get("path", "")
            name: str = file_info.get("name", os.path.basename(path))
            text: str = file_info.get("text", "")
            modified: Optional[float] = file_info.get("modified")

            if not path:
                skipped += 1
                continue

            # Stable ID from file path
            file_id = hashlib.md5(path.encode()).hexdigest()[:20]
            if is_synced(db, "local_files", file_id):
                skipped += 1
                continue

            # Use first-level subfolder under root (bridge provides this directly)
            folder_name = file_info.get("subfolder") or os.path.basename(os.path.dirname(path))
            raw = f"Datei: {name}\nOrdner: {folder_name}\n\n{text[:2000]}"

            hint_apps = find_hint_apps(raw, term_to_apps)
            if not hint_apps:
                # No firm match — don't mark as synced (may match later if apps added)
                skipped += 1
                continue

            det = _classify_deterministic("local_files", raw, None, hint_apps)
            if det is None:
                # Multiple matches — skip files (can't disambiguate without AI)
                mark_synced(db, "local_files", file_id)
                skipped += 1
                continue

            # Set notiz to relative file path for traceability
            det["notiz"] = path

            date_hint = datetime.fromtimestamp(modified, tz=timezone.utc) if modified else None
            ok = _save_deterministic_event(db, "local_files", file_id, det, raw, date_hint)
            processed += 1
            if ok:
                created += 1
                # Store file as attachment if bridge provides raw content
                raw_bytes_b64: Optional[str] = file_info.get("raw_bytes")
                if raw_bytes_b64:
                    try:
                        import base64
                        from app.routers.attachments import store_attachment
                        raw_bytes = base64.b64decode(raw_bytes_b64)
                        # Find the event we just created
                        ev = db.query(models.Event).filter_by(
                            source="local_files", external_id=file_id
                        ).order_by(models.Event.id.desc()).first()
                        if ev:
                            size_mb = len(raw_bytes) / 1024 / 1024
                            if size_mb > 100:
                                from datetime import date as _date
                                db.add(models.PendingMatch(
                                    source="attachment",
                                    external_id=f"attachment_{file_id}",
                                    confidence=99,
                                    event_type="large_attachment",
                                    datum=_date.today(),
                                    titel=f"Großer Anhang: {name}",
                                    extract=f"Datei {name} ({size_mb:.1f} MB) ist zu groß.",
                                    suggested_app_id=ev.application_id,
                                ))
                            else:
                                store_attachment(db, ev.id, name, raw_bytes, source="local_files", external_id=file_id)
                    except Exception:
                        pass

        db.commit()
        cfg.last_sync = datetime.now(timezone.utc)
        db.commit()
        finish_progress("local_files")
        return {"processed": processed, "created": created, "skipped": skipped, "errors": errors}
    except Exception as e:
        finish_progress("local_files")
        return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [str(e)]}
    finally:
        db.close()


@router.post("", response_model=dict)
async def sync_files(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    cfg = _get_or_create_cfg(db)
    if not cfg.enabled or not cfg.folder_path:
        return {"processed": 0, "created": 0, "skipped": 0, "errors": []}

    set_batch_result("local_files", {"done": False})
    init_progress("local_files", "Dokumente", "Starte…")

    async def _bg():
        result = await _do_local_files()
        set_batch_result("local_files", {**result, "done": True})

    background_tasks.add_task(_bg)
    return {"processed": 0, "created": 0, "skipped": 0, "errors": []}


@router.get("/browse")
async def browse_files(path: str = "", db: Session = Depends(get_db)):
    """List items at a given absolute host path. Defaults to configured root."""
    import httpx
    cfg = _get_cfg(db)
    target = path or (cfg.folder_path if cfg else "")
    if not target:
        raise HTTPException(status_code=400, detail="Kein Pfad angegeben und kein Dokumentenordner konfiguriert.")
    default_root = cfg.folder_path if cfg else ""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{FILES_BRIDGE_URL}/browse", params={"folder": target})
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail=resp.json().get("error", "Bridge-Fehler"))
            return {"path": target, "default_root": default_root, "items": resp.json()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Files Bridge nicht erreichbar: {e}")


class AttachRequest(BaseModel):
    app_id: int
    path: str
    name: Optional[str] = None
    is_folder: bool = False


@router.post("/attach")
async def attach_file(req: AttachRequest, db: Session = Depends(get_db)):
    """Manually attach a file or folder from the host to an application."""
    import httpx
    app_obj = db.query(models.Application).filter_by(id=req.app_id).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail="Bewerbung nicht gefunden")

    name = req.name or os.path.basename(req.path)

    if req.is_folder:
        # Attach all files in the folder (recursive via bridge)
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(f"{FILES_BRIDGE_URL}/files", params={"folder": req.path})
                files = resp.json() if resp.status_code == 200 else []
        except Exception:
            files = []

        created = 0
        for file_info in files:
            fpath = file_info.get("path", "")
            fname = file_info.get("name", os.path.basename(fpath))
            if not fpath:
                continue
            file_id = hashlib.md5(fpath.encode()).hexdigest()[:20]
            if db.query(models.SyncedItem).filter_by(source="local_files", external_id=file_id).first():
                continue
            db.add(models.Event(
                application_id=req.app_id,
                source="local_files",
                external_id=file_id,
                typ="file",
                datum=_date.today(),
                titel=fname,
                notiz=fpath,
            ))
            mark_synced(db, "local_files", file_id)
            created += 1
        db.commit()
        return {"created": created, "titel": name}

    file_id = hashlib.md5(req.path.encode()).hexdigest()[:20]
    ev = models.Event(
        application_id=req.app_id,
        source="local_files",
        external_id=file_id,
        typ="file",
        datum=_date.today(),
        titel=name,
        notiz=req.path,
    )
    db.add(ev)
    mark_synced(db, "local_files", file_id)
    db.commit()
    db.refresh(ev)
    return {"event_id": ev.id, "created": 1, "titel": name}
