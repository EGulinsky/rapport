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

class AIToolsUnsupported(AIBadRequest):
    """Configured model/provider doesn't support function/tool calling."""
    pass


def _disable_gemini_thinking(kwargs: dict) -> None:
    """Gemini's "2.5" model family (Flash, Flash-Lite, Pro) has hidden
    "thinking"/reasoning tokens enabled by default, which count against
    max_tokens -- for the JSON-mode structured-extraction calls this app
    makes (match score, chat tool-calls, the settings connection test), a
    thinking pass can consume the entire max_tokens budget before any answer
    tokens are emitted, truncating the JSON response mid-string (observed as
    a bare json.JSONDecodeError "Unterminated string..."). Flash-Lite doesn't
    think by default and was unaffected, which is why only some Gemini models
    triggered this. These tasks have no need for visible reasoning, so
    disable thinking outright wherever the model supports the knob --
    `get_supported_openai_params` only returns `reasoning_effort` for the
    "2.5"+ family, so older non-thinking Gemini models (1.5, 2.0) are
    correctly left untouched (passing the param there raises
    litellm.UnsupportedParamsError instead of being silently ignored)."""
    model = kwargs.get("model", "")
    if not model.startswith("gemini/"):
        return
    if "reasoning_effort" in (litellm.get_supported_openai_params(model=model) or []):
        kwargs["reasoning_effort"] = "none"


def _build_request_kwargs(db: Session, messages: list[dict], max_tokens: int):
    """Shared by complete() and complete_with_tools(): loads the active
    AiSettings row, resolves+decrypts the matching AiProviderKey, and
    assembles the base litellm kwargs. Raises AINotConfigured if there's no
    active/enabled config. Returns (kwargs, cfg) — cfg is needed by callers
    for error messages and tool-support checks."""
    from app.models import AiSettings, AiProviderKey

    cfg = db.query(AiSettings).first()
    if not cfg or not cfg.enabled:
        raise AINotConfigured("Kein AI-Anbieter konfiguriert oder deaktiviert.")

    kwargs: dict = {
        "model": cfg.model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.1,
    }
    _disable_gemini_thinking(kwargs)
    key_row = db.query(AiProviderKey).filter(AiProviderKey.provider == cfg.provider).first()
    if key_row and key_row.api_key_enc:
        kwargs["api_key"] = decrypt_api_key(key_row.api_key_enc)
    if cfg.base_url:
        kwargs["api_base"] = cfg.base_url
    return kwargs, cfg


async def complete(
    db: Session,
    messages: list[dict],
    json_mode: bool = True,
    max_tokens: int = 1024,
) -> dict | str:
    kwargs, cfg = _build_request_kwargs(db, messages, max_tokens)
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


async def complete_with_tools(
    db: Session,
    messages: list[dict],
    tools: list[dict],
    max_tokens: int = 1024,
    tool_choice: str = "auto",
):
    """Like complete(), but supports tool/function calling — returns the raw
    litellm response *message* object (has .content and .tool_calls), not a
    parsed dict|str, since the caller (the chat agent loop) needs to branch
    on whether the model asked to call a tool or produced a final answer."""
    kwargs, cfg = _build_request_kwargs(db, messages, max_tokens)

    if tools:
        try:
            supported = litellm.supports_function_calling(model=cfg.model)
        except Exception:
            supported = True  # unknown/custom model (e.g. self-hosted base_url) — don't block, rely on the reactive check below
        if not supported:
            raise AIToolsUnsupported(f"Modell '{cfg.model}' unterstützt kein Tool-Calling.")
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice

    log.info(
        "AI chat request | model={model} max_tokens={max_tokens}\n{messages}",
        model=cfg.model,
        max_tokens=max_tokens,
        messages=json.dumps(messages, ensure_ascii=False, indent=2, default=str),
    )

    try:
        response = await litellm.acompletion(**kwargs)
    except litellm.RateLimitError as e:
        log.warning("AI rate limited: {}", e)
        raise AIRateLimited(str(e))
    except litellm.BadRequestError as e:
        msg = str(e)
        log.warning("AI bad request: {}", msg)
        if any(s in msg.lower() for s in ("tool", "function calling", "does not support tools")):
            raise AIToolsUnsupported(f"Modell '{cfg.model}' unterstützt kein Tool-Calling.")
        raise AIBadRequest(f"Ungültige Anfrage: {msg[:200]}")
    except litellm.AuthenticationError as e:
        log.warning("AI auth error: {}", e)
        raise AIBadRequest("API-Key ungültig oder abgelaufen.")

    message = response.choices[0].message
    log.info(
        "AI chat response | model={model} tool_calls={tool_calls}\n{content}",
        model=cfg.model,
        tool_calls=len(message.tool_calls) if message.tool_calls else 0,
        content=message.content or "",
    )
    return message
