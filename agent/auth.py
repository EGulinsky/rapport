"""Bearer-token auth for every agent endpoint except /health.

The agent binds on an interface reachable from Docker's host gateway (pure
127.0.0.1-only binding would break that reachability), so the token is the
actual security boundary — replaces the previous zero-auth bridges."""
from __future__ import annotations

import hmac

from fastapi import Header, HTTPException

from agent.config import AgentConfig


def require_token(cfg: AgentConfig):
    def _check(authorization: str | None = Header(default=None)) -> None:
        expected = f"Bearer {cfg.token}"
        if not authorization or not hmac.compare_digest(authorization, expected):
            raise HTTPException(status_code=401, detail="Ungültiger oder fehlender Token")
    return _check
