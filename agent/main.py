"""JobTracker Agent — single background service replacing files_bridge.py,
notes_bridge.py and calls_bridge.py. See agent/README.md for architecture.

Run directly:  python3 -m agent.main
"""
from __future__ import annotations

from fastapi import Depends, FastAPI

from agent.auth import require_token
from agent.config import AgentConfig, platform_name
from agent.providers.base import CallsProvider, FilesProvider, NotesProvider
from agent.routers import backup, calls, files, notes

__version__ = "0.1.0"


def create_app(
    config: AgentConfig,
    files_provider: FilesProvider,
    notes_provider: NotesProvider,
    calls_provider: CallsProvider,
) -> FastAPI:
    """Builds the FastAPI app from already-constructed dependencies — kept
    free of module-level side effects (no config file I/O, no subprocess
    calls at import time) so tests can inject fakes cheaply."""
    app = FastAPI(title="JobTracker Agent", version=__version__)

    auth = require_token(config)
    app.include_router(files.router, dependencies=[Depends(auth)])
    app.include_router(backup.router, dependencies=[Depends(auth)])
    app.include_router(notes.router, dependencies=[Depends(auth)])
    app.include_router(calls.router, dependencies=[Depends(auth)])

    app.dependency_overrides[files.get_files_provider] = lambda: files_provider
    app.dependency_overrides[notes.get_notes_provider] = lambda: notes_provider
    app.dependency_overrides[calls.get_calls_provider] = lambda: calls_provider

    @app.get("/health")
    def health():
        """Unauthenticated on purpose (mirrors the old bridges' /health) — the
        JobTracker backend's startup check needs to detect the agent before it
        has a token configured. Reports per-module status so the frontend can
        show the same granular Files/Notes/Calls breakdown as today."""
        modules = {}
        for name, provider in (("files", files_provider), ("notes", notes_provider), ("calls", calls_provider)):
            try:
                modules[name] = provider.health() if hasattr(provider, "health") else {"ok": True}
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
    import uvicorn

    from agent.providers import factory

    config = AgentConfig.load_or_create()
    app = create_app(
        config,
        files_provider=factory.make_files_provider(),
        notes_provider=factory.make_notes_provider(),
        calls_provider=factory.make_calls_provider(),
    )
    uvicorn.run(app, host="0.0.0.0", port=config.port)


if __name__ == "__main__":
    run()
