"""
Local-files sync: indexes documents from a configured folder on the host.

Requires the Rapport Agent running on the host (see agent/README.md).

GET  /api/sync/files/status       — agent reachability + last sync info
POST /api/sync/files              — trigger background sync
POST /api/sync/files/reset        — clear synced-items for local_files source
GET  /api/sync/files/browse       — browse folders/files under root (manual sync)
POST /api/sync/files/attach       — attach a specific file to an application
"""
from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, date as _date, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agent_client import agent_get, agent_post
from app.audit import add_audit
from app.i18n_strings import resolve_ui_language, t
from app.database import get_db, SessionLocal, set_session_user
from app import models
from app.auth.dependencies import get_current_user
from app.routers.sync_common import (
    is_synced, mark_synced, purge_source,
    build_firm_index, find_hint_apps,
    init_progress, update_progress, finish_progress,
    set_batch_result, _to_naive_utc,
)

router = APIRouter(prefix="/api/sync/files", tags=["sync"])


def _rolle_in_name(rolle: str, name_lower: str) -> bool:
    cleaned = re.sub(r'\s*\(m[/|]w[/|]d\)\s*$', '', rolle, flags=re.IGNORECASE).strip().lower()
    return bool(cleaned) and cleaned in name_lower


def _get_cfg(db: Session) -> Optional[models.FilesConfig]:
    return db.query(models.FilesConfig).first()


def _get_or_create_cfg(db: Session, user_id: int) -> models.FilesConfig:
    cfg = _get_cfg(db)
    if not cfg:
        cfg = models.FilesConfig(enabled=True, user_id=user_id)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


@router.get("/status")
async def files_status(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    cfg = _get_or_create_cfg(db, current_user.id)
    reachable = False
    try:
        resp = await agent_get(db, "/health", timeout=3)
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
def reset_files_sync(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    cfg = _get_cfg(db)
    if cfg:
        cfg.last_sync = None
    purge_source(db, "local_files", current_user.id)
    db.commit()


async def _do_local_files(user_id: int) -> dict:
    db = SessionLocal()
    set_session_user(db, user_id)
    lang = resolve_ui_language(db, user_id)
    processed = created = skipped = 0
    errors: list[str] = []
    try:
        cfg = db.query(models.FilesConfig).first()
        if not cfg or not cfg.enabled:
            finish_progress("local_files", lang=lang)
            return {"processed": 0, "created": 0, "skipped": 0, "errors": []}
        if not cfg.folder_path:
            finish_progress("local_files", lang=lang)
            return {"processed": 0, "created": 0, "skipped": 0, "errors": [t("no_folder_configured", lang)]}

        _, term_to_apps = build_firm_index(db)
        if not term_to_apps:
            finish_progress("local_files", lang=lang)
            return {"processed": 0, "created": 0, "skipped": 0, "errors": []}

        update_progress("local_files", 0, 0, t("loading_documents", lang))
        params: dict = {"folder": cfg.folder_path}
        if cfg.last_sync:
            params["since"] = str(cfg.last_sync.timestamp())

        try:
            resp = await agent_get(db, "/files", params=params, timeout=60)
            if resp.status_code != 200:
                err = resp.json().get("error", resp.text) if resp.headers.get("content-type", "").startswith("application/json") else resp.text
                finish_progress("local_files", lang=lang)
                return {"processed": 0, "created": 0, "skipped": 0, "errors": [t("agent_error", lang, error=err)]}
            files = resp.json()
        except Exception as e:
            finish_progress("local_files", lang=lang)
            return {"processed": 0, "created": 0, "skipped": 0, "errors": [
                t("agent_unreachable", lang, error=e)
            ]}

        # Group files by first-level subfolder under root
        from collections import defaultdict
        by_subfolder: dict[str, list[dict]] = defaultdict(list)
        for file_info in files:
            sf = file_info.get("subfolder", "")
            if sf:
                by_subfolder[sf].append(file_info)

        total = len(by_subfolder)
        update_progress("local_files", 0, total, t("folders_found", lang, count=total))

        for folder_idx, (subfolder_name, subfolder_files) in enumerate(by_subfolder.items()):
            update_progress("local_files", folder_idx, total, t("folder_progress", lang, current=folder_idx + 1, total=total, name=subfolder_name))

            # Match subfolder name against firm index
            hint_apps = find_hint_apps(subfolder_name, term_to_apps)
            if not hint_apps:
                skipped += len(subfolder_files)
                continue

            if len(hint_apps) > 1:
                # Multiple apps for same firm — try to disambiguate via role in folder name
                name_lower = subfolder_name.lower()
                by_role = [a for a in hint_apps if _rolle_in_name(a.get("rolle", ""), name_lower)]
                if len(by_role) != 1:
                    skipped += len(subfolder_files)
                    continue
                hint_apps = by_role

            app_id = hint_apps[0]["id"]
            processed += 1

            for file_info in subfolder_files:
                path: str = file_info.get("path", "")
                name: str = file_info.get("name", "") or os.path.basename(path)
                modified: Optional[float] = file_info.get("modified")

                if not path:
                    skipped += 1
                    continue

                file_id = hashlib.md5(path.encode()).hexdigest()[:20]
                if is_synced(db, "local_files", file_id):
                    skipped += 1
                    continue

                date_hint = datetime.fromtimestamp(modified, tz=timezone.utc) if modified else None
                new_event = models.Event(
                    application_id=app_id,
                    source="local_files",
                    external_id=file_id,
                    typ="file",
                    datum=date_hint.date() if date_hint else None,
                    datum_zeit=_to_naive_utc(date_hint),
                    titel=name,
                    notiz=path,
                    user_id=user_id,
                )
                db.add(new_event)
                db.flush()
                add_audit(db, "create", "local_files", app_id=app_id, event_id=new_event.id,
                          new_value=name, user_id=user_id)
                mark_synced(db, "local_files", file_id, user_id)
                created += 1

        db.commit()
        # Only advance last_sync when files were actually created; otherwise
        # the since-filter would permanently exclude unmatched files on future runs.
        if created > 0:
            cfg.last_sync = datetime.now(timezone.utc)
            db.commit()
        finish_progress("local_files", lang=lang)
        return {"processed": processed, "created": created, "skipped": skipped, "errors": errors}
    except Exception as e:
        finish_progress("local_files", lang=lang)
        return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [str(e)]}
    finally:
        db.close()


@router.post("", response_model=dict)
async def sync_files(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    cfg = _get_or_create_cfg(db, current_user.id)
    if not cfg.enabled or not cfg.folder_path:
        return {"processed": 0, "created": 0, "skipped": 0, "errors": []}

    set_batch_result("local_files", {"done": False})
    init_progress("local_files", t("label_documents", current_user.ui_language), lang=current_user.ui_language)

    async def _bg():
        result = await _do_local_files(current_user.id)
        set_batch_result("local_files", {**result, "done": True})

    background_tasks.add_task(_bg)
    return {"processed": 0, "created": 0, "skipped": 0, "errors": []}


@router.get("/browse")
async def browse_files(
    path: str = "",
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """List items at a given absolute host path. Defaults to configured root."""
    cfg = _get_cfg(db)
    target = path or (cfg.folder_path if cfg else "")
    if not target:
        raise HTTPException(status_code=400, detail="Kein Pfad angegeben und kein Dokumentenordner konfiguriert.")
    default_root = cfg.folder_path if cfg else ""
    try:
        resp = await agent_get(db, "/files/browse", params={"folder": target}, timeout=10)
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=resp.json().get("error", "Agent-Fehler"))
        return {"path": target, "default_root": default_root, "items": resp.json()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Rapport Agent nicht erreichbar: {e}")


class AttachRequest(BaseModel):
    app_id: int
    path: str
    name: Optional[str] = None
    is_folder: bool = False


@router.post("/attach")
async def attach_file(
    req: AttachRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Manually attach a file or folder from the host to an application."""
    app_obj = db.query(models.Application).filter_by(id=req.app_id).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail="Bewerbung nicht gefunden")

    name = req.name or os.path.basename(req.path)

    if req.is_folder:
        # Attach all files in the folder (recursive via agent)
        try:
            resp = await agent_get(db, "/files", params={"folder": req.path}, timeout=30)
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
            file_event = models.Event(
                application_id=req.app_id,
                source="local_files",
                external_id=file_id,
                typ="file",
                datum=_date.today(),
                titel=fname,
                notiz=fpath,
                user_id=current_user.id,
            )
            db.add(file_event)
            db.flush()
            add_audit(db, "create", "user", app_id=req.app_id, event_id=file_event.id,
                      new_value=fname, reason_key="file_attached_manually", user_id=current_user.id)
            mark_synced(db, "local_files", file_id, current_user.id)
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
        user_id=current_user.id,
    )
    db.add(ev)
    db.flush()
    add_audit(db, "create", "user", app_id=req.app_id, event_id=ev.id,
              new_value=name, reason_key="file_attached_manually", user_id=current_user.id)
    mark_synced(db, "local_files", file_id, current_user.id)
    db.commit()
    db.refresh(ev)
    return {"event_id": ev.id, "created": 1, "titel": name}


@router.post("/open")
async def open_file(
    body: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Ask the host agent to open a file with the default OS application."""
    path = body.get("path", "")
    if not path:
        raise HTTPException(status_code=400, detail="path erforderlich")
    try:
        resp = await agent_post(db, "/files/open", json={"path": path}, timeout=5)
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=resp.text)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"success": True}
