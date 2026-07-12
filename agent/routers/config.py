from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel

from agent.config import AgentConfig

router = APIRouter(prefix="/config", tags=["config"])


def get_agent_config() -> AgentConfig:  # overridden in main.py
    raise NotImplementedError


def get_restart_trigger() -> Callable[[], None]:  # overridden in main.py's create_app()
    raise NotImplementedError


class ConfigPatch(BaseModel):
    ui_language: str


@router.patch("")
def patch_config(
    body: ConfigPatch,
    background_tasks: BackgroundTasks,
    config: AgentConfig = Depends(get_agent_config),
    restart_agent: Callable[[], None] = Depends(get_restart_trigger),
):
    """Backend pushes the user's ui_language here whenever it changes (token
    save/re-verify in Settings -> Agent, or a language switch in Settings ->
    Account). rumps builds the menu once at startup, so a config push alone
    never becomes visible — schedule an actual restart (as a background task,
    running only after this response is sent) whenever the language actually
    changed."""
    changed = body.ui_language != config.ui_language
    config.ui_language = body.ui_language
    config.save()
    if changed:
        background_tasks.add_task(restart_agent)
    return {"ui_language": config.ui_language}
