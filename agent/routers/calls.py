from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from agent.providers.base import CallsProvider

router = APIRouter(prefix="/calls", tags=["calls"])


def get_calls_provider() -> CallsProvider:  # overridden in main.py
    raise NotImplementedError


@router.get("")
def list_calls(
    since_days: int = Query(default=90),
    source: str = Query(default="all"),
    provider: CallsProvider = Depends(get_calls_provider),
):
    return provider.list_calls(since_days, source)
