"""
Local-files sync: indexes documents from a configured folder on the host Mac.

Requires files_bridge.py running on the host:
  python3 files_bridge.py          # port 9998

GET  /api/sync/files/status  — bridge reachability + last sync info
POST /api/sync/files         — trigger background sync
POST /api/sync/files/reset   — clear synced-items for local_files source
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends
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

            # Build searchable text: filename + parent folder name + content preview
            folder_name = os.path.basename(os.path.dirname(path))
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
