"""Shared HTTP client for talking to the host-side Rapport Agent —
replaces the four duplicated httpx-boilerplate call sites that used to talk
to files_bridge/notes_bridge/calls_bridge directly (backup.py, sync_files.py,
sync_icloud.py, sync_targeted.py).
"""
from __future__ import annotations

import os
from typing import Any, Optional

import httpx
from sqlalchemy.orm import Session

from app import models
from app.ai.provider import decrypt_api_key

DEFAULT_AGENT_URL = os.getenv("AGENT_URL", "http://host.docker.internal:9996")


def _get_cfg(db: Session) -> Optional[models.AgentSettings]:
    return db.query(models.AgentSettings).first()


def get_agent_url(db: Session) -> str:
    cfg = _get_cfg(db)
    if cfg and cfg.url:
        return cfg.url.rstrip("/")
    return DEFAULT_AGENT_URL.rstrip("/")


def get_agent_token(db: Session) -> Optional[str]:
    cfg = _get_cfg(db)
    if not cfg or not cfg.token_enc:
        return None
    try:
        return decrypt_api_key(cfg.token_enc)
    except Exception:
        return None


def _auth_headers(db: Session) -> dict[str, str]:
    token = get_agent_token(db)
    return {"Authorization": f"Bearer {token}"} if token else {}


async def agent_get(db: Session, path: str, params: dict[str, Any] | None = None, timeout: float = 30) -> httpx.Response:
    url = f"{get_agent_url(db)}{path}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        return await client.get(url, params=params, headers=_auth_headers(db))


async def agent_post(db: Session, path: str, json: dict[str, Any] | None = None, timeout: float = 30) -> httpx.Response:
    url = f"{get_agent_url(db)}{path}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        return await client.post(url, json=json, headers=_auth_headers(db))


async def agent_health(db: Session) -> dict[str, Any]:
    """Unauthenticated by design (mirrors agent's own /health) — must work
    even before a token is configured, so the user can see the agent exists
    before pairing it."""
    url = f"{get_agent_url(db)}/health"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            return {"reachable": False, "error": f"HTTP {resp.status_code}"}
        data = resp.json()
        return {
            "reachable": True,
            "version": data.get("version"),
            "platform": data.get("platform"),
            "modules": data.get("modules", {}),
        }
    except Exception as e:
        return {"reachable": False, "error": str(e)[:200]}
