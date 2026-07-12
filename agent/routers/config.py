from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from agent.config import AgentConfig

router = APIRouter(prefix="/config", tags=["config"])


def get_agent_config() -> AgentConfig:  # overridden in main.py
    raise NotImplementedError


class ConfigPatch(BaseModel):
    ui_language: str


@router.patch("")
def patch_config(body: ConfigPatch, config: AgentConfig = Depends(get_agent_config)):
    """Backend pushes the user's ui_language here whenever the agent token is
    saved/re-verified in Settings -> Agent. rumps builds the menu once at
    startup, so this only takes effect after the agent is next restarted."""
    config.ui_language = body.ui_language
    config.save()
    return {"ui_language": config.ui_language}
