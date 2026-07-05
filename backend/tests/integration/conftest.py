"""Geteilte Fixtures für L3-Integrationstests.

Mocking-Grenze ist bewusst `litellm.acompletion` selbst (nicht die eigenen
`app.ai.*`-Funktionen) — das testet die komplette eigene Logik in
`app/ai/provider.py::complete()` (JSON-Parsing, leere-Antwort-Erkennung,
Fehler-Mapping auf AINotConfigured/AIRateLimited/AIBadRequest) end-to-end,
ohne echte Netzwerkaufrufe an Groq/Anthropic/OpenAI/Ollama.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import litellm
import pytest

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "ai_responses"


def load_fixture(name: str) -> str:
    """Rohtext einer Fixture-Datei — genau der String, den litellm als
    `response.choices[0].message.content` liefern würde."""
    return (FIXTURES_DIR / name).read_text()


class FakeAIProvider:
    """Test-Double für `litellm.acompletion`. Antworten/Fehler werden vorab
    in eine Queue gelegt und pro Aufruf nacheinander konsumiert — so lassen
    sich auch Mehrfach-Aufrufe (z.B. Batch-Fallback) exakt steuern.
    Alle `kwargs` jedes Aufrufs werden für Assertions aufgezeichnet."""

    def __init__(self) -> None:
        self._queue: list[tuple[str, object]] = []
        self.calls: list[dict] = []

    def queue_content(self, content: str) -> "FakeAIProvider":
        self._queue.append(("content", content))
        return self

    def queue_error(self, exc: Exception) -> "FakeAIProvider":
        self._queue.append(("error", exc))
        return self

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if not self._queue:
            raise AssertionError("FakeAIProvider: keine weitere Antwort in der Queue konfiguriert")
        kind, value = self._queue.pop(0)
        if kind == "error":
            raise value
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=value))])


@pytest.fixture()
def fake_ai_provider(monkeypatch) -> FakeAIProvider:
    fake = FakeAIProvider()
    monkeypatch.setattr(litellm, "acompletion", fake)
    return fake


@pytest.fixture()
def ai_settings(db_session):
    """Aktivierter AI-Provider ohne echten Key — die Fake-Antwort kommt vor
    jeder Authentifizierung ins Spiel, da `litellm.acompletion` selbst gepatcht ist."""
    from app import models

    cfg = models.AiSettings(provider="groq", model="groq/llama-3.3-70b-versatile", enabled=True)
    db_session.add(cfg)
    db_session.flush()
    return cfg
