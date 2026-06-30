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

    content: str = response.choices[0].message.content or ""

    log.info(
        "AI response | model={model}\n{content}",
        model=cfg.model,
        content=content,
    )

    if json_mode:
        return json.loads(content)
    return content
