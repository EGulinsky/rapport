"""Geteilte Fixtures für L3-Integrationstests.

Mocking-Grenze ist bewusst `litellm.acompletion` selbst (nicht die eigenen
`app.ai.*`-Funktionen) — das testet die komplette eigene Logik in
`app/ai/provider.py::complete()` (JSON-Parsing, leere-Antwort-Erkennung,
Fehler-Mapping auf AINotConfigured/AIRateLimited/AIBadRequest) end-to-end,
ohne echte Netzwerkaufrufe an Groq/Anthropic/OpenAI/Ollama.

WICHTIG (live gefundene Falle): `_do_gcal()`/`_do_gmail()` etc. öffnen intern
eine EIGENE `SessionLocal()` statt die Test-`db_session` zu nutzen. Setup-Daten
über `db_session` MÜSSEN vor dem Aufruf committet werden (`db_session.commit()`),
sonst hält die eigene Session der Sync-Funktion an SQLite's `busy_timeout`
(60s, siehe `app/database.py`) fest — der Test läuft dann durch, aber erst nach
einer Minute. Kein `db.flush()`-Ersatz möglich, da Flush keine Locks freigibt."""
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


@pytest.fixture()
def google_sync(db_session):
    """GoogleSync-Konfig mit gültigem, nicht abgelaufenem Access-Token — damit
    `_refresh_if_needed()` keinen echten OAuth-Refresh-Call auslöst (der sonst
    zusätzlich gemockt werden müsste). `_do_gcal()`/`_do_gmail()` öffnen intern
    eine eigene SessionLocal() — Setup-Daten müssen daher committet sein."""
    from datetime import datetime, timedelta, timezone

    from app import models
    from app.ai.provider import encrypt_api_key

    cfg = models.GoogleSync(
        client_id="test-client-id",
        client_secret_enc=encrypt_api_key("test-secret"),
        access_token_enc=encrypt_api_key("test-access-token"),
        refresh_token_enc=encrypt_api_key("test-refresh-token"),
        token_expiry=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(cfg)
    db_session.commit()
    return cfg


class FakeCalendarService:
    """Test-Double für den von `googleapiclient.discovery.build('calendar', ...)`
    zurückgegebenen Service — deckt nur die hier tatsächlich genutzte Methodenkette
    `events().list(**kwargs).execute()` ab."""

    def __init__(self, events: list[dict]) -> None:
        self._events = events
        self.list_calls: list[dict] = []

    def events(self) -> "FakeCalendarService":
        return self

    def list(self, **kwargs) -> "FakeCalendarService":
        self.list_calls.append(kwargs)
        return self

    def execute(self) -> dict:
        return {"items": self._events}


@pytest.fixture()
def fake_google_calendar(monkeypatch):
    """Liefert eine Factory `set_events(events) -> FakeCalendarService`. Muss vor
    dem Aufruf von `_do_gcal()` mit den gewünschten Kalender-Events befüllt werden."""
    holder: dict[str, FakeCalendarService] = {}

    def _fake_build(serviceName, version, credentials=None, cache_discovery=True):
        assert serviceName == "calendar", f"Nur Calendar gemockt, nicht {serviceName!r}"
        return holder["service"]

    def set_events(events: list[dict]) -> FakeCalendarService:
        service = FakeCalendarService(events)
        holder["service"] = service
        return service

    monkeypatch.setattr("googleapiclient.discovery.build", _fake_build)
    return set_events


class FakeGmailBatchRequest:
    """Test-Double für googleapiclient's BatchHttpRequest. `_do_gmail()` sammelt
    über `.add(request, request_id=...)` mehrere `.get()`-Aufrufe und ruft dann
    `.execute()` — hier wird der Callback synchron mit (request_id, response,
    exception) je gesammeltem Request aufgerufen, wie die echte Batch-API es tut.
    Metadata- und Full-Body-Batches laufen über denselben Mechanismus, unterschieden
    nur durch das `format`-Argument des jeweiligen `.get()`-Aufrufs."""

    def __init__(self, callback, metadata: dict[str, dict], full: dict[str, dict],
                 errors: dict[str, Exception] | None = None) -> None:
        self._callback = callback
        self._metadata = metadata
        self._full = full
        self._errors = errors or {}
        self._added: list[tuple[str, str]] = []

    def add(self, request, request_id=None) -> None:
        fmt = getattr(request, "_format", "full")
        self._added.append((request_id, fmt))

    def execute(self) -> None:
        for request_id, fmt in self._added:
            if request_id in self._errors:
                self._callback(request_id, None, self._errors[request_id])
                continue
            source = self._metadata if fmt == "metadata" else self._full
            self._callback(request_id, source.get(request_id), None)


class FakeGmailService:
    """Test-Double für `googleapiclient.discovery.build('gmail', ...)`. Deckt
    `users().messages().list(**kwargs).execute()` (inkl. Pagination über
    `list_pages`, eine Antwort pro aufeinanderfolgendem Aufruf) sowie die
    zweiphasige Batch-Abholung (Metadata dann Volltext) ab."""

    def __init__(self, list_pages: list[dict], metadata: dict[str, dict] | None = None,
                 full: dict[str, dict] | None = None, batch_errors: dict[str, Exception] | None = None) -> None:
        self._list_pages = list(list_pages)
        self._metadata = metadata or {}
        self._full = full or {}
        self._batch_errors = batch_errors or {}
        self.list_calls: list[dict] = []

    def users(self) -> "FakeGmailService":
        return self

    def messages(self) -> "FakeGmailService":
        return self

    def list(self, **kwargs) -> "FakeGmailService":
        self.list_calls.append(kwargs)
        return self

    def get(self, userId, id, format=None, metadataHeaders=None):
        return SimpleNamespace(_msg_id=id, _format=format)

    def execute(self) -> dict:
        return self._list_pages.pop(0) if self._list_pages else {"messages": []}

    def new_batch_http_request(self, callback) -> FakeGmailBatchRequest:
        return FakeGmailBatchRequest(callback, self._metadata, self._full, self._batch_errors)


def gmail_message(msg_id: str, sender: str, subject: str, body_text: str, date_str: str) -> tuple[dict, dict]:
    """Baut ein (metadata, full)-Antwortpaar für eine Gmail-Nachricht — die
    beiden Formen, die `_do_gmail()` für dieselbe msg_id nacheinander abruft."""
    import base64

    metadata = {
        "id": msg_id,
        "payload": {"headers": [
            {"name": "From", "value": sender},
            {"name": "To", "value": ""},
            {"name": "Cc", "value": ""},
            {"name": "Subject", "value": subject},
            {"name": "Date", "value": date_str},
        ]},
    }
    encoded = base64.urlsafe_b64encode(body_text.encode()).decode().rstrip("=")
    full = {
        "id": msg_id,
        "payload": {"mimeType": "text/plain", "body": {"data": encoded}},
    }
    return metadata, full


@pytest.fixture()
def fake_gmail(monkeypatch):
    """Liefert eine Factory `set_service(list_pages, metadata=None, full=None,
    batch_errors=None) -> FakeGmailService`. `gmail_message()` baut die
    metadata/full-Paare für einzelne Nachrichten."""
    holder: dict[str, FakeGmailService] = {}

    def _fake_build(serviceName, version, credentials=None, cache_discovery=True):
        assert serviceName == "gmail", f"Nur Gmail gemockt, nicht {serviceName!r}"
        return holder["service"]

    def set_service(list_pages, metadata=None, full=None, batch_errors=None) -> FakeGmailService:
        service = FakeGmailService(list_pages, metadata, full, batch_errors)
        holder["service"] = service
        return service

    monkeypatch.setattr("googleapiclient.discovery.build", _fake_build)
    return set_service
