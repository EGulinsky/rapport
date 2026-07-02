import json
from typing import Optional

import httpx
import litellm
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
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


@router.get("/maps", response_model=schemas.MapsSettingsRead)
def get_maps_settings(db: Session = Depends(get_db)):
    cfg = db.query(models.MapsSettings).first()
    return schemas.MapsSettingsRead(has_key=bool(cfg and cfg.api_key_enc))


@router.post("/maps", response_model=schemas.MapsSettingsRead)
def save_maps_settings(payload: schemas.MapsSettingsWrite, db: Session = Depends(get_db)):
    cfg = db.query(models.MapsSettings).first()
    if not cfg:
        cfg = models.MapsSettings()
        db.add(cfg)

    if payload.api_key and payload.api_key.strip():
        cfg.api_key_enc = encrypt_api_key(payload.api_key.strip())
    else:
        cfg.api_key_enc = None

    db.commit()
    db.refresh(cfg)
    return schemas.MapsSettingsRead(has_key=bool(cfg.api_key_enc))


@router.delete("/maps/key", response_model=schemas.MapsSettingsRead)
def clear_maps_key(db: Session = Depends(get_db)):
    cfg = db.query(models.MapsSettings).first()
    if cfg:
        cfg.api_key_enc = None
        db.commit()
    return schemas.MapsSettingsRead(has_key=False)


@router.get("/logo")
def get_logo_settings(db: Session = Depends(get_db)):
    cfg = db.query(models.LogoSettings).first()
    return {"api_key": cfg.api_key if cfg else None}


@router.post("/logo")
def save_logo_settings(payload: dict, db: Session = Depends(get_db)):
    cfg = db.query(models.LogoSettings).first()
    if not cfg:
        cfg = models.LogoSettings()
        db.add(cfg)
    cfg.api_key = payload.get("api_key") or None
    db.commit()
    return {"api_key": cfg.api_key}


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
            # Resolve api_key: use provided key, or fall back to stored key only if
            # the same provider is being tested (prevents Groq key leaking into Ollama tests)
            api_key: Optional[str] = None
            if payload.api_key and payload.api_key.strip():
                api_key = payload.api_key.strip()
            else:
                cfg = db.query(models.AiSettings).first()
                if cfg and cfg.api_key_enc and cfg.provider == payload.provider:
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
        except litellm.RateLimitError:
            raise HTTPException(429, "Rate-Limit erreicht — bitte 30–60 Sekunden warten und nochmal testen.")
        except litellm.AuthenticationError:
            raise HTTPException(401, "API-Key ungültig oder abgelaufen.")
        except Exception as e:
            msg = str(e)
            # Truncate long provider error blobs
            if len(msg) > 300:
                msg = msg[:300] + "…"
            raise HTTPException(502, f"Provider-Fehler: {msg}")

    try:
        result = await test_connection(db)
        return {"status": "ok", "message": result}
    except AINotConfigured as e:
        raise HTTPException(400, str(e))
    except litellm.RateLimitError:
        raise HTTPException(429, "Rate-Limit erreicht — bitte 30–60 Sekunden warten und nochmal testen.")
    except Exception as e:
        msg = str(e)
        if len(msg) > 300:
            msg = msg[:300] + "…"
        raise HTTPException(502, f"Provider-Fehler: {msg}")


_POPULAR_OLLAMA_MODELS = [
    {"name": "llama3.2",       "display": "Llama 3.2",     "params": "3B",   "size_gb": 2.0},
    {"name": "llama3.2:1b",    "display": "Llama 3.2",     "params": "1B",   "size_gb": 0.8},
    {"name": "llama3.1:8b",    "display": "Llama 3.1",     "params": "8B",   "size_gb": 4.7},
    {"name": "qwen2.5:7b",     "display": "Qwen 2.5",      "params": "7B",   "size_gb": 4.4},
    {"name": "qwen2.5:14b",    "display": "Qwen 2.5",      "params": "14B",  "size_gb": 9.0},
    {"name": "mistral",        "display": "Mistral",        "params": "7B",   "size_gb": 4.1},
    {"name": "mistral-nemo",   "display": "Mistral Nemo",   "params": "12B",  "size_gb": 7.1},
    {"name": "phi4-mini",      "display": "Phi-4 Mini",     "params": "3.8B", "size_gb": 2.5},
    {"name": "phi4",           "display": "Phi-4",          "params": "14B",  "size_gb": 9.1},
    {"name": "gemma3:4b",      "display": "Gemma 3",        "params": "4B",   "size_gb": 3.3},
    {"name": "gemma3:12b",     "display": "Gemma 3",        "params": "12B",  "size_gb": 8.1},
    {"name": "deepseek-r1:7b", "display": "DeepSeek-R1",   "params": "7B",   "size_gb": 4.7},
]


@router.get("/ollama/models")
async def list_ollama_models(base_url: str = "http://localhost:11434"):
    installed: list[str] = []
    reachable = False
    try:
        async with httpx.AsyncClient(timeout=4) as client:
            r = await client.get(f"{base_url.rstrip('/')}/api/tags")
            if r.status_code == 200:
                reachable = True
                installed = [m["name"] for m in r.json().get("models", [])]
    except Exception:
        pass
    return {
        "reachable": reachable,
        "installed": installed,
        "popular": _POPULAR_OLLAMA_MODELS,
    }


@router.get("/ollama/pull")
async def pull_ollama_model(model: str, base_url: str = "http://localhost:11434"):
    async def _stream():
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST",
                    f"{base_url.rstrip('/')}/api/pull",
                    json={"name": model},
                ) as resp:
                    async for line in resp.aiter_lines():
                        if line:
                            yield f"data: {line}\n\n"
        except Exception as e:
            yield f'data: {{"status":"error","error":{json.dumps(str(e))}}}\n\n'
        yield 'data: {"status":"done"}\n\n'

    return StreamingResponse(_stream(), media_type="text/event-stream")
