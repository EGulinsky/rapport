"""
Vendor-agnostic AI provider via LiteLLM.
API key is encrypted with Fernet; key file lives next to the SQLite DB.
"""
import json
import os
import pathlib

import litellm
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from app.logger import get_logger

litellm.suppress_debug_info = True

log = get_logger("ai")

_DATA_DIR = pathlib.Path(
    os.getenv("DATABASE_URL", "sqlite:///./data/jobtracker.db")
    .replace("sqlite:///", "")
    .replace("sqlite://", "")
).parent


def _fernet() -> Fernet:
    key_file = _DATA_DIR / "fernet.key"
    if key_file.exists():
        return Fernet(key_file.read_bytes().strip())
    key = Fernet.generate_key()
    key_file.write_bytes(key)
    return Fernet(key)


def encrypt_api_key(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_api_key(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


class AINotConfigured(Exception):
    pass

class AIRateLimited(Exception):
    pass

class AIBadRequest(Exception):
    pass


async def complete(
    db: Session,
    messages: list[dict],
    json_mode: bool = True,
    max_tokens: int = 1024,
) -> dict | str:
    from app.models import AiSettings

    cfg = db.query(AiSettings).first()
    if not cfg or not cfg.enabled:
        raise AINotConfigured("Kein AI-Anbieter konfiguriert oder deaktiviert.")

    kwargs: dict = {
        "model": cfg.model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.1,
    }
    if cfg.api_key_enc:
        kwargs["api_key"] = decrypt_api_key(cfg.api_key_enc)
    if cfg.base_url:
        kwargs["api_base"] = cfg.base_url
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    log.info(
        "AI request | model={model} max_tokens={max_tokens}\n{messages}",
        model=cfg.model,
        max_tokens=max_tokens,
        messages=json.dumps(messages, ensure_ascii=False, indent=2),
    )

    try:
        response = await litellm.acompletion(**kwargs)
    except litellm.RateLimitError as e:
        log.warning("AI rate limited: {}", e)
        raise AIRateLimited(str(e))
    except litellm.BadRequestError as e:
        msg = str(e)
        log.warning("AI bad request: {}", msg)
        if "json_validate_failed" in msg or "Failed to validate JSON" in msg:
            raise AIBadRequest(
                f"Modell '{cfg.model}' unterstützt keinen JSON-Modus oder hat ungültiges JSON geliefert. "
                "Versuche ein anderes Modell (z.B. llama-3.3-70b-versatile)."
            )
        if "model" in msg.lower() and ("not found" in msg.lower() or "does not exist" in msg.lower()):
            raise AIBadRequest(f"Modell '{cfg.model}' nicht gefunden beim Anbieter.")
        raise AIBadRequest(f"Ungültige Anfrage: {msg[:200]}")
    except litellm.AuthenticationError as e:
        log.warning("AI auth error: {}", e)
        raise AIBadRequest("API-Key ungültig oder abgelaufen.")

    content: str = response.choices[0].message.content or ""

    if not content.strip():
        log.warning("AI returned empty content for model={}", cfg.model)
        raise AIBadRequest(
            f"Modell '{cfg.model}' hat leere Antwort geliefert — "
            "möglicherweise nicht verfügbar oder kein JSON-Modus unterstützt."
        )

    log.info(
        "AI response | model={model}\n{content}",
        model=cfg.model,
        content=content,
    )

    if json_mode:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            log.warning("AI response not valid JSON: {}", content[:200])
            raise AIBadRequest(
                f"Modell '{cfg.model}' hat kein gültiges JSON geliefert. "
                "Versuche ein anderes Modell."
            )
    return content
