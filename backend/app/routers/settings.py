import json
from typing import Optional

import httpx
import litellm
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.ai.provider import encrypt_api_key, decrypt_api_key, AINotConfigured, _disable_gemini_thinking, _acompletion
from app.ai.tasks import test_connection
from app.auth.dependencies import get_current_user
from app.logger import get_logger

router = APIRouter(prefix="/api/settings", tags=["settings"])
log = get_logger("settings", source="ai_models")


def _provider_key_row(db: Session, provider: str) -> Optional[models.AiProviderKey]:
    return db.query(models.AiProviderKey).filter(models.AiProviderKey.provider == provider).first()


def _configured_providers(db: Session) -> list[str]:
    rows = db.query(models.AiProviderKey.provider).filter(models.AiProviderKey.api_key_enc.isnot(None)).all()
    return [r[0] for r in rows]


def _to_read(cfg: models.AiSettings, db: Session) -> schemas.AiSettingsRead:
    row = _provider_key_row(db, cfg.provider)
    return schemas.AiSettingsRead(
        provider=cfg.provider,
        model=cfg.model,
        has_key=bool(row and row.api_key_enc),
        base_url=cfg.base_url,
        enabled=cfg.enabled,
        configured_providers=_configured_providers(db),
    )


@router.get("/ai", response_model=schemas.AiSettingsRead)
def get_ai_settings(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    cfg = db.query(models.AiSettings).first()
    if not cfg:
        return schemas.AiSettingsRead(
            provider="groq",
            model="groq/llama-3.3-70b-versatile",
            has_key=False,
            base_url=None,
            enabled=False,
            configured_providers=_configured_providers(db),
        )
    return _to_read(cfg, db)


@router.post("/ai", response_model=schemas.AiSettingsRead)
def save_ai_settings(
    payload: schemas.AiSettingsWrite,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    cfg = db.query(models.AiSettings).first()
    if not cfg:
        cfg = models.AiSettings(user_id=current_user.id)
        db.add(cfg)

    cfg.provider = payload.provider
    cfg.model    = payload.model
    cfg.base_url = payload.base_url or None
    cfg.enabled  = payload.enabled

    # The key lives in its own per-provider row (AiProviderKey), independent
    # of which provider is active here — so switching providers back and
    # forth never loses or misapplies a key that was already saved for it.
    if payload.api_key and payload.api_key.strip():
        row = _provider_key_row(db, payload.provider)
        if not row:
            row = models.AiProviderKey(user_id=current_user.id, provider=payload.provider)
            db.add(row)
        row.api_key_enc = encrypt_api_key(payload.api_key.strip())

    db.commit()
    db.refresh(cfg)
    return _to_read(cfg, db)


@router.delete("/ai/key", response_model=schemas.AiSettingsRead)
def clear_api_key(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Clears the key for the currently active provider only — other
    providers' saved keys are untouched."""
    cfg = db.query(models.AiSettings).first()
    if not cfg:
        raise HTTPException(404, "Keine Einstellungen vorhanden")
    row = _provider_key_row(db, cfg.provider)
    if row:
        db.delete(row)
    db.commit()
    db.refresh(cfg)
    return _to_read(cfg, db)


@router.get("/agent", response_model=schemas.AgentSettingsRead)
def get_agent_settings(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    cfg = db.query(models.AgentSettings).first()
    return schemas.AgentSettingsRead(url=cfg.url if cfg else None, has_token=bool(cfg and cfg.token_enc))


@router.post("/agent", response_model=schemas.AgentSettingsRead)
async def save_agent_settings(
    payload: schemas.AgentSettingsWrite,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    cfg = db.query(models.AgentSettings).first()
    if not cfg:
        cfg = models.AgentSettings(user_id=current_user.id)
        db.add(cfg)

    cfg.url = payload.url.strip() if payload.url and payload.url.strip() else None
    if payload.token and payload.token.strip():
        cfg.token_enc = encrypt_api_key(payload.token.strip())
    else:
        cfg.token_enc = None

    db.commit()
    db.refresh(cfg)

    if cfg.token_enc:
        from app.agent_client import agent_patch
        try:
            await agent_patch(db, "/config", json={"ui_language": current_user.ui_language}, timeout=5)
        except Exception:
            pass  # agent may not be reachable yet — pairing itself must not fail because of this

    return schemas.AgentSettingsRead(url=cfg.url, has_token=bool(cfg.token_enc))


@router.delete("/agent/token", response_model=schemas.AgentSettingsRead)
def clear_agent_token(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    cfg = db.query(models.AgentSettings).first()
    if cfg:
        cfg.token_enc = None
        db.commit()
        return schemas.AgentSettingsRead(url=cfg.url, has_token=False)
    return schemas.AgentSettingsRead(url=None, has_token=False)


@router.get("/agent/health", response_model=schemas.AgentHealth)
async def get_agent_health(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    from app.agent_client import agent_health
    data = await agent_health(db)
    return schemas.AgentHealth(**data)


@router.get("/logo")
def get_logo_settings(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    cfg = db.query(models.LogoSettings).first()
    return {"api_key": cfg.api_key if cfg else None}


@router.post("/logo")
def save_logo_settings(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    cfg = db.query(models.LogoSettings).first()
    if not cfg:
        cfg = models.LogoSettings(user_id=current_user.id)
        db.add(cfg)
    cfg.api_key = payload.get("api_key") or None
    db.commit()
    return {"api_key": cfg.api_key}


@router.get("/sync")
def get_sync_settings(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    cfg = db.query(models.SyncSettings).first()
    if not cfg:
        cfg = models.SyncSettings(user_id=current_user.id)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return {
        "google_enabled": cfg.google_enabled,
        "gmail_enabled": cfg.gmail_enabled,
        "gcal_enabled": cfg.gcal_enabled,
        "google_contacts_enabled": cfg.google_contacts_enabled,
        "icloud_enabled": cfg.icloud_enabled,
        "icloud_mail_enabled": cfg.icloud_mail_enabled,
        "icloud_cal_enabled": cfg.icloud_cal_enabled,
        "icloud_notes_enabled": cfg.icloud_notes_enabled,
        "icloud_reminders_enabled": cfg.icloud_reminders_enabled,
        "icloud_contacts_enabled": cfg.icloud_contacts_enabled,
        "icloud_calls_enabled": cfg.icloud_calls_enabled,
        "linkedin_enabled": cfg.linkedin_enabled,
        "linkedin_job_tracker_enabled": cfg.linkedin_job_tracker_enabled,
        "linkedin_messages_enabled": cfg.linkedin_messages_enabled,
        "files_enabled": cfg.files_enabled,
        "audit_log_level": cfg.audit_log_level or "normal",
    }


@router.post("/sync")
def save_sync_settings(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    cfg = db.query(models.SyncSettings).first()
    if not cfg:
        cfg = models.SyncSettings(user_id=current_user.id)
        db.add(cfg)
    for key, val in payload.items():
        if hasattr(cfg, key) and isinstance(val, bool):
            setattr(cfg, key, val)
    if "audit_log_level" in payload and payload["audit_log_level"] in ("off", "normal", "verbose"):
        cfg.audit_log_level = payload["audit_log_level"]
    db.commit()
    db.refresh(cfg)
    return get_sync_settings(db, current_user)


@router.get("/files")
def get_files_config(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    cfg = db.query(models.FilesConfig).first()
    if not cfg:
        cfg = models.FilesConfig(enabled=False, user_id=current_user.id)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return {
        "folder_path": cfg.folder_path,
        "enabled": cfg.enabled,
        "last_sync": cfg.last_sync.isoformat() if cfg.last_sync else None,
    }


@router.post("/files")
def save_files_config(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    cfg = db.query(models.FilesConfig).first()
    if not cfg:
        cfg = models.FilesConfig(user_id=current_user.id)
        db.add(cfg)
    if "folder_path" in payload:
        fp = (payload["folder_path"] or "").strip().strip("'\"") or None
        cfg.folder_path = fp
    if "enabled" in payload and isinstance(payload["enabled"], bool):
        cfg.enabled = payload["enabled"]
    db.commit()
    db.refresh(cfg)
    return get_files_config(db, current_user)


def _resolve_api_key(db: Session, provider: str, explicit_key: Optional[str]) -> Optional[str]:
    """Use the explicit (not-yet-saved) key if given, else the key stored
    for this specific provider in AiProviderKey — a provider-scoped table,
    so this can never resolve to a different provider's key."""
    if explicit_key and explicit_key.strip():
        return explicit_key.strip()
    row = _provider_key_row(db, provider)
    if row and row.api_key_enc:
        return decrypt_api_key(row.api_key_enc)
    return None


@router.post("/ai/test")
async def test_ai(
    payload: Optional[schemas.AiSettingsWrite] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # If form values are passed, test against them directly (without saving)
    if payload:
        try:
            api_key = _resolve_api_key(db, payload.provider, payload.api_key)

            kwargs: dict = {
                "model": payload.model,
                "messages": [{"role": "user", "content": 'Antworte mit dem JSON {"ok": true}'}],
                "max_tokens": 32,
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
            }
            _disable_gemini_thinking(kwargs)
            if api_key:
                kwargs["api_key"] = api_key
            if payload.base_url and payload.base_url.strip():
                kwargs["api_base"] = payload.base_url.strip()

            response = await _acompletion(kwargs)
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


_MODEL_LIST_TIMEOUT = httpx.Timeout(30.0)


async def _fetch_groq_models(api_key: str) -> list[schemas.AiModelInfo]:
    async with httpx.AsyncClient(timeout=_MODEL_LIST_TIMEOUT) as client:
        r = await client.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        r.raise_for_status()
        data = r.json()
    out = []
    for m in data.get("data", []):
        mid = m.get("id", "")
        # Groq also serves audio (whisper) models under the same endpoint —
        # not usable for our chat-completion use case.
        if not mid or "whisper" in mid:
            continue
        out.append(schemas.AiModelInfo(model=f"groq/{mid}", label=mid, context_window=m.get("context_window")))
    return sorted(out, key=lambda m: m.label)


async def _fetch_anthropic_models(api_key: str) -> list[schemas.AiModelInfo]:
    async with httpx.AsyncClient(timeout=_MODEL_LIST_TIMEOUT) as client:
        r = await client.get(
            "https://api.anthropic.com/v1/models",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
        )
        r.raise_for_status()
        data = r.json()
    out = [
        schemas.AiModelInfo(model=f"anthropic/{m['id']}", label=m.get("display_name") or m["id"])
        for m in data.get("data", [])
        if m.get("id")
    ]
    return sorted(out, key=lambda m: m.label)


async def _fetch_openai_models(api_key: str) -> list[schemas.AiModelInfo]:
    async with httpx.AsyncClient(timeout=_MODEL_LIST_TIMEOUT) as client:
        r = await client.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        r.raise_for_status()
        data = r.json()
    out = []
    for m in data.get("data", []):
        mid = m.get("id", "")
        # The account-wide /models list also includes embeddings, whisper,
        # tts, dall-e, and moderation models — none usable for chat completion.
        if not (mid.startswith(("gpt-", "o1", "o3", "o4", "chatgpt"))):
            continue
        out.append(schemas.AiModelInfo(model=mid, label=mid))
    return sorted(out, key=lambda m: m.label)


async def _fetch_gemini_models(api_key: str) -> list[schemas.AiModelInfo]:
    # v1beta/models paginates (default page size 50) — without following
    # nextPageToken, models beyond the first page (often the newest ones)
    # silently never show up. The AI-Studio-issued keys this app expects are
    # only reliably authenticated via the documented ?key= query parameter
    # (the curl example in Google's own docs); the x-goog-api-key header
    # this used previously got a bare 400 from the real API the moment any
    # other query parameter (e.g. pageSize) was present alongside it.
    out = []
    page_token: str | None = None
    async with httpx.AsyncClient(timeout=_MODEL_LIST_TIMEOUT) as client:
        for _ in range(10):
            params = {"key": api_key, "pageSize": 200}
            if page_token:
                params["pageToken"] = page_token
            r = await client.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params=params,
            )
            r.raise_for_status()
            data = r.json()
            for m in data.get("models", []):
                if "generateContent" not in m.get("supportedGenerationMethods", []):
                    continue
                name = m.get("name", "").removeprefix("models/")
                if not name:
                    continue
                out.append(schemas.AiModelInfo(
                    model=f"gemini/{name}",
                    label=m.get("displayName") or name,
                    description=m.get("description"),
                    context_window=m.get("inputTokenLimit"),
                    max_output_tokens=m.get("outputTokenLimit"),
                ))
            page_token = data.get("nextPageToken")
            if not page_token:
                break
    return sorted(out, key=lambda m: m.label)


_MODEL_FETCHERS = {
    "groq": _fetch_groq_models,
    "anthropic": _fetch_anthropic_models,
    "openai": _fetch_openai_models,
    "gemini": _fetch_gemini_models,
}


@router.post("/ai/models")
async def list_ai_models(
    payload: schemas.AiModelsRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Live model list for the given provider, using the not-yet-saved form
    key if present, else the stored key for that same provider. Never raises
    for "not configured yet"/"unreachable" — mirrors the pre-existing
    always-200 convention (matches how the removed Ollama-models endpoint
    behaved), since this is called opportunistically while the user is still
    filling in the form and a hard error would be noisy UX; the frontend
    falls back to its curated suggestion list whenever reachable is false.
    """
    fetcher = _MODEL_FETCHERS.get(payload.provider)
    if fetcher is None:
        return {"reachable": False, "models": [], "error": f"Unknown provider: {payload.provider}"}

    api_key = _resolve_api_key(db, payload.provider, payload.api_key)
    if not api_key:
        return {"reachable": False, "models": [], "error": "No API key configured"}

    try:
        model_list = await fetcher(api_key)
        return {"reachable": True, "models": model_list, "error": None}
    except Exception as e:
        body = getattr(getattr(e, "response", None), "text", None)
        log.warning(f"live model list failed for provider={payload.provider}: {e!r} body={body!r}")
        msg = str(e)
        if len(msg) > 300:
            msg = msg[:300] + "…"
        return {"reachable": False, "models": [], "error": msg}
