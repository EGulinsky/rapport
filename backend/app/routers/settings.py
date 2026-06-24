import json
from typing import Optional

import litellm
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.ai.provider import encrypt_api_key, decrypt_api_key, AINotConfigured
from app.ai.tasks import test_connection

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _to_read(cfg: models.AiSettings) -> schemas.AiSettingsRead:
    return schemas.AiSettingsRead(
        provider=cfg.provider,
        model=cfg.model,
        has_key=bool(cfg.api_key_enc),
        base_url=cfg.base_url,
        enabled=cfg.enabled,
    )


@router.get("/ai", response_model=schemas.AiSettingsRead)
def get_ai_settings(db: Session = Depends(get_db)):
    cfg = db.query(models.AiSettings).first()
    if not cfg:
        return schemas.AiSettingsRead(
            provider="groq",
            model="groq/llama-3.3-70b-versatile",
            has_key=False,
            base_url=None,
            enabled=False,
        )
    return _to_read(cfg)


@router.post("/ai", response_model=schemas.AiSettingsRead)
def save_ai_settings(payload: schemas.AiSettingsWrite, db: Session = Depends(get_db)):
    cfg = db.query(models.AiSettings).first()
    if not cfg:
        cfg = models.AiSettings()
        db.add(cfg)

    cfg.provider = payload.provider
    cfg.model    = payload.model
    cfg.base_url = payload.base_url or None
    cfg.enabled  = payload.enabled

    if payload.api_key and payload.api_key.strip():
        cfg.api_key_enc = encrypt_api_key(payload.api_key.strip())

    db.commit()
    db.refresh(cfg)
    return _to_read(cfg)


@router.delete("/ai/key", response_model=schemas.AiSettingsRead)
def clear_api_key(db: Session = Depends(get_db)):
    cfg = db.query(models.AiSettings).first()
    if cfg:
        cfg.api_key_enc = None
        db.commit()
        db.refresh(cfg)
        return _to_read(cfg)
    raise HTTPException(404, "Keine Einstellungen vorhanden")


@router.get("/sync")
def get_sync_settings(db: Session = Depends(get_db)):
    cfg = db.query(models.SyncSettings).first()
    if not cfg:
        cfg = models.SyncSettings()
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return {
        "google_enabled": cfg.google_enabled,
        "gmail_enabled": cfg.gmail_enabled,
        "gcal_enabled": cfg.gcal_enabled,
        "icloud_enabled": cfg.icloud_enabled,
        "icloud_mail_enabled": cfg.icloud_mail_enabled,
        "icloud_cal_enabled": cfg.icloud_cal_enabled,
        "icloud_notes_enabled": cfg.icloud_notes_enabled,
        "icloud_reminders_enabled": cfg.icloud_reminders_enabled,
        "icloud_contacts_enabled": cfg.icloud_contacts_enabled,
        "icloud_calls_enabled": cfg.icloud_calls_enabled,
        "linkedin_enabled": cfg.linkedin_enabled,
        "files_enabled": cfg.files_enabled,
        "audit_log_level": cfg.audit_log_level or "normal",
    }


@router.post("/sync")
def save_sync_settings(payload: dict, db: Session = Depends(get_db)):
    cfg = db.query(models.SyncSettings).first()
    if not cfg:
        cfg = models.SyncSettings()
        db.add(cfg)
    for key, val in payload.items():
        if hasattr(cfg, key) and isinstance(val, bool):
            setattr(cfg, key, val)
    if "audit_log_level" in payload and payload["audit_log_level"] in ("off", "normal", "verbose"):
        cfg.audit_log_level = payload["audit_log_level"]
    db.commit()
    db.refresh(cfg)
    return get_sync_settings(db)


@router.get("/files")
def get_files_config(db: Session = Depends(get_db)):
    cfg = db.query(models.FilesConfig).first()
    if not cfg:
        cfg = models.FilesConfig(enabled=True)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return {
        "folder_path": cfg.folder_path,
        "enabled": cfg.enabled,
        "last_sync": cfg.last_sync.isoformat() if cfg.last_sync else None,
    }


@router.post("/files")
def save_files_config(payload: dict, db: Session = Depends(get_db)):
    cfg = db.query(models.FilesConfig).first()
    if not cfg:
        cfg = models.FilesConfig()
        db.add(cfg)
    if "folder_path" in payload:
        fp = (payload["folder_path"] or "").strip().strip("'\"") or None
        cfg.folder_path = fp
    if "enabled" in payload and isinstance(payload["enabled"], bool):
        cfg.enabled = payload["enabled"]
    db.commit()
    db.refresh(cfg)
    return get_files_config(db)


@router.post("/ai/test")
async def test_ai(payload: Optional[schemas.AiSettingsWrite] = None, db: Session = Depends(get_db)):
    # If form values are passed, test against them directly (without saving)
    if payload:
        try:
            # Resolve api_key: use provided key, or fall back to stored one
            api_key: Optional[str] = None
            if payload.api_key and payload.api_key.strip():
                api_key = payload.api_key.strip()
            else:
                cfg = db.query(models.AiSettings).first()
                if cfg and cfg.api_key_enc:
                    api_key = decrypt_api_key(cfg.api_key_enc)

            kwargs: dict = {
                "model": payload.model,
                "messages": [{"role": "user", "content": 'Antworte mit dem JSON {"ok": true}'}],
                "max_tokens": 32,
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
            }
            if api_key:
                kwargs["api_key"] = api_key
            if payload.base_url and payload.base_url.strip():
                kwargs["api_base"] = payload.base_url.strip()

            response = await litellm.acompletion(**kwargs)
            content = response.choices[0].message.content or ""
            result = json.loads(content)
            return {"status": "ok", "message": "ok" if result.get("ok") else f"Unerwartete Antwort: {result}"}
        except Exception as e:
            raise HTTPException(502, f"Provider-Fehler: {e}")

    try:
        result = await test_connection(db)
        return {"status": "ok", "message": result}
    except AINotConfigured as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"Provider-Fehler: {e}")
