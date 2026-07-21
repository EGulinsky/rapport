"""Rapport Agent — single background service replacing files_bridge.py,
notes_bridge.py and calls_bridge.py. See agent/README.md for architecture.

Run directly:  python3 -m agent.main
"""
from __future__ import annotations

from typing import Callable

from fastapi import Depends, FastAPI

from agent.auth import require_token
from agent.config import AgentConfig, platform_name
from agent.providers.base import CallsProvider, FilesProvider, NotesProvider
from agent.routers import backup, calls, config as config_router, files, notes
from agent.version import __version__


def create_app(
    config: AgentConfig,
    files_provider: FilesProvider,
    notes_provider: NotesProvider,
    calls_provider: CallsProvider,
    restart_agent: Callable[[], None] | None = None,
) -> FastAPI:
    """Builds the FastAPI app from already-constructed dependencies — kept
    free of module-level side effects (no config file I/O, no subprocess
    calls at import time) so tests can inject fakes cheaply. `restart_agent`
    defaults to a no-op (safe for tests); production entry points
    (menubar.py, run() below) pass agent.config.restart_process so a
    ui_language push actually takes visible effect."""
    app = FastAPI(title="Rapport Agent", version=__version__)

    auth = require_token(config)
    app.include_router(files.router, dependencies=[Depends(auth)])
    app.include_router(backup.router, dependencies=[Depends(auth)])
    app.include_router(notes.router, dependencies=[Depends(auth)])
    app.include_router(calls.router, dependencies=[Depends(auth)])
    app.include_router(config_router.router, dependencies=[Depends(auth)])

    app.dependency_overrides[files.get_files_provider] = lambda: files_provider
    app.dependency_overrides[notes.get_notes_provider] = lambda: notes_provider
    app.dependency_overrides[calls.get_calls_provider] = lambda: calls_provider
    app.dependency_overrides[config_router.get_agent_config] = lambda: config
    app.dependency_overrides[config_router.get_restart_trigger] = lambda: (restart_agent or (lambda: None))

    @app.get("/health")
    def health():
        """Unauthenticated on purpose (mirrors the old bridges' /health) — the
        rapport backend's startup check needs to detect the agent before it
        has a token configured. Reports per-module status so the frontend can
        show the same granular Files/Notes/Calls breakdown as today."""
        modules = {}
        for name, provider in (("files", files_provider), ("notes", notes_provider), ("calls", calls_provider)):
            try:
                info = provider.health() if hasattr(provider, "health") else {"ok": True}
                if hasattr(provider, "platform_limited") and provider.platform_limited:
                    info["platform_limited"] = True
                modules[name] = info
            except Exception as e:
                modules[name] = {"ok": False, "error": str(e)}

        return {
            "status": "ok",
            "version": __version__,
            "platform": platform_name(),
            "modules": modules,
        }

    return app


def run():
    """Run the agent directly (without system tray). Useful for development."""
    import uvicorn

    from agent.config import restart_process
    from agent.providers import factory

    config = AgentConfig.load_or_create()
    app = create_app(
        config,
        files_provider=factory.make_files_provider(),
        notes_provider=factory.make_notes_provider(),
        calls_provider=factory.make_calls_provider(),
        restart_agent=restart_process,
    )
    uvicorn.run(app, host="0.0.0.0", port=config.port)


if __name__ == "__main__":
    run()
