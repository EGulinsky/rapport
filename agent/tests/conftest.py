"""Shared fixtures for agent tests — fake providers, a fixed test token, and
a TestClient wired via create_app() (no real subprocess/file-system side
effects unless a test explicitly opts in via tmp_path)."""
from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent.config import AgentConfig
from agent.main import create_app
from agent.providers.base import CallsProvider, FilesProvider, NotesProvider

TEST_TOKEN = "test-token-12345"


class FakeFilesProvider(FilesProvider):
    def __init__(self):
        self.picked_folder: str | None = "/fake/picked/folder"
        self.picked_file: str | None = "/fake/picked/file.zip"
        self.opened_paths: list[str] = []

    def pick_folder(self, prompt: str) -> str | None:
        return self.picked_folder

    def pick_file(self, prompt: str, extensions: list[str]) -> str | None:
        return self.picked_file

    def open_path(self, path: str) -> None:
        self.opened_paths.append(path)


class FakeNotesProvider(NotesProvider):
    def __init__(self, notes: list[dict[str, Any]] | None = None, healthy: bool = True):
        self._notes = notes if notes is not None else [{"id": "1", "name": "Test", "body": "hi", "date": ""}]
        self._healthy = healthy

    def list_notes(self) -> list[dict[str, Any]]:
        if not self._healthy:
            raise RuntimeError("Notes app nicht erreichbar")
        return self._notes

    def health(self) -> dict[str, Any]:
        return {"ok": self._healthy}


class FakeCallsProvider(CallsProvider):
    def __init__(self, calls: list[dict[str, Any]] | None = None, healthy: bool = True):
        self._calls = calls if calls is not None else []
        self._healthy = healthy

    def list_calls(self, since_days: int, source: str = "all") -> list[dict[str, Any]]:
        return self._calls

    def health(self) -> dict[str, Any]:
        return {"ok": self._healthy, "phone_accessible": self._healthy, "whatsapp_accessible": self._healthy}


@pytest.fixture
def fake_files_provider():
    return FakeFilesProvider()


@pytest.fixture
def fake_notes_provider():
    return FakeNotesProvider()


@pytest.fixture
def fake_calls_provider():
    return FakeCallsProvider()


@pytest.fixture
def test_config():
    return AgentConfig(token=TEST_TOKEN, port=9996)


@pytest.fixture
def client(test_config, fake_files_provider, fake_notes_provider, fake_calls_provider):
    app = create_app(test_config, fake_files_provider, fake_notes_provider, fake_calls_provider)
    return TestClient(app)


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {TEST_TOKEN}"}
