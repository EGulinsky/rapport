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
        user_id=1,
    )
    db_session.add(cfg)
    db_session.commit()
    return cfg


class FakeCalendarBatchRequest:
    """Test-Double für googleapiclient's BatchHttpRequest, für
    backfill_gcal_autor()'s batched `events().get()`-Aufrufe -- derselbe
    Mechanismus wie FakeGmailBatchRequest, nur ohne Metadata-/Full-Unterscheidung
    (get_events liefert direkt das vollständige Event-Dict pro eventId)."""

    def __init__(self, callback, get_events: dict[str, dict],
                 errors: dict[str, Exception] | None = None) -> None:
        self._callback = callback
        self._get_events = get_events
        self._errors = errors or {}
        self._added: list[str] = []

    def add(self, request, request_id=None) -> None:
        self._added.append(request_id)

    def execute(self) -> None:
        for request_id in self._added:
            if request_id in self._errors:
                self._callback(request_id, None, self._errors[request_id])
                continue
            self._callback(request_id, self._get_events.get(request_id), None)


class FakeCalendarService:
    """Test-Double für den von `googleapiclient.discovery.build('calendar', ...)`
    zurückgegebenen Service — deckt `events().list(**kwargs).execute()` (normaler
    Sync) sowie die gebatchte `events().get()` (backfill_gcal_autor()) ab."""

    def __init__(self, events: list[dict], get_events: dict[str, dict] | None = None,
                 batch_errors: dict[str, Exception] | None = None) -> None:
        self._events = events
        self._get_events = get_events or {}
        self._batch_errors = batch_errors or {}
        self.list_calls: list[dict] = []

    def events(self) -> "FakeCalendarService":
        return self

    def list(self, **kwargs) -> "FakeCalendarService":
        self.list_calls.append(kwargs)
        return self

    def get(self, calendarId=None, eventId=None):
        return SimpleNamespace(_event_id=eventId)

    def execute(self) -> dict:
        return {"items": self._events}

    def new_batch_http_request(self, callback) -> FakeCalendarBatchRequest:
        return FakeCalendarBatchRequest(callback, self._get_events, self._batch_errors)


@pytest.fixture()
def fake_google_calendar(monkeypatch):
    """Liefert eine Factory `set_events(events, get_events=None, batch_errors=None)
    -> FakeCalendarService`. Muss vor dem Aufruf von `_do_gcal()` mit den
    gewünschten Kalender-Events befüllt werden. `get_events` (eventId -> Event-
    Dict) ist für backfill_gcal_autor()'s gebatchte `events().get()`-Aufrufe."""
    holder: dict[str, FakeCalendarService] = {}

    def _fake_build(serviceName, version, credentials=None, cache_discovery=True):
        assert serviceName == "calendar", f"Nur Calendar gemockt, nicht {serviceName!r}"
        return holder["service"]

    def set_events(events: list[dict], get_events: dict[str, dict] | None = None,
                   batch_errors: dict[str, Exception] | None = None) -> FakeCalendarService:
        service = FakeCalendarService(events, get_events, batch_errors)
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


@pytest.fixture()
def icloud_sync(db_session):
    """ICloudSync-Konfig mit verschlüsseltem App-Passwort — `_imap_connect()`
    ruft `decrypt_api_key()` darauf auf, das Ergebnis wird an die (gemockte)
    IMAP-Verbindung als Passwort übergeben, aber vom Fake nie geprüft."""
    from app import models
    from app.ai.provider import encrypt_api_key

    cfg = models.ICloudSync(
        apple_id="test@example.com",
        icloud_email="test@icloud.com",
        app_password_enc=encrypt_api_key("test-app-password"),
        user_id=1,
    )
    db_session.add(cfg)
    db_session.commit()
    return cfg


class FakeImapConnection:
    """Test-Double für `imaplib.IMAP4_SSL`. Deckt genau die hier genutzte
    Methodenkette ab: `login()`, `select()`, `search(None, criteria)`,
    `fetch(msg_id_bytes, spec)` (zweiphasig: erst RFC822.HEADER, dann bei
    Bedarf die volle Nachricht via BODY.PEEK[] — see _imap_fetch_full_bytes()
    in sync_icloud.py for why not the RFC822 macro) und `logout()`."""

    def __init__(self, search_response: bytes, messages: dict[bytes, dict[str, bytes]]) -> None:
        self._search_response = search_response
        self._messages = messages
        self.search_calls: list[str] = []
        self.fetch_calls: list[tuple[bytes, str]] = []

    def login(self, user, password):
        return ("OK", [b"Logged in"])

    def select(self, mailbox):
        return ("OK", [b"1"])

    def search(self, charset, criteria):
        self.search_calls.append(criteria)
        return ("OK", [self._search_response])

    def fetch(self, msg_id_bytes, spec):
        self.fetch_calls.append((msg_id_bytes, spec))
        data = self._messages[msg_id_bytes]
        key = "header" if "HEADER" in spec else "full"
        return ("OK", [(b"", data[key])])

    def logout(self):
        return ("BYE", [b"Logging out"])


def icloud_email(msg_id: str, sender: str, subject: str, body_text: str, date_str: str) -> tuple[bytes, dict[str, bytes]]:
    """Baut (msg_id_bytes, {"header":..., "full":...}) für eine IMAP-Testnachricht."""
    from email.message import EmailMessage

    full_msg = EmailMessage()
    full_msg["From"] = sender
    full_msg["Subject"] = subject
    full_msg["Date"] = date_str
    full_msg.set_content(body_text)

    header_msg = EmailMessage()
    header_msg["From"] = sender
    header_msg["Subject"] = subject
    header_msg["Date"] = date_str

    return msg_id.encode(), {"header": bytes(header_msg), "full": bytes(full_msg)}


@pytest.fixture()
def fake_icloud_imap(monkeypatch):
    """Liefert eine Factory `set_messages(msg_ids: list[str], messages: dict) ->
    FakeImapConnection`. `messages` bildet die msg_id_bytes aus `icloud_email()`
    auf ihr (header, full)-Paar ab."""
    holder: dict[str, FakeImapConnection] = {}

    def _fake_imap_ssl(host, port):
        return holder["conn"]

    def set_messages(msg_ids: list[str], messages: dict[bytes, dict[str, bytes]] | None = None) -> FakeImapConnection:
        search_response = " ".join(msg_ids).encode()
        conn = FakeImapConnection(search_response, messages or {})
        holder["conn"] = conn
        return conn

    monkeypatch.setattr("imaplib.IMAP4_SSL", _fake_imap_ssl)
    return set_messages


class FakeCaldavEvent:
    """Test-Double für ein caldav-`Event`/`Todo`-Objekt. `.vobject_instance` ist
    ECHT über `vobject.readOne()` geparst (kein Hand-Stub) — nur so wird eine
    reale Falle wie das versehentliche `str()` auf ein vobject-ContentLine-Objekt
    (liefert '<SUMMARY{}Text>' statt 'Text') im Test überhaupt sichtbar."""

    def __init__(self, ics_text: str, url: str) -> None:
        import vobject
        self.vobject_instance = vobject.readOne(ics_text)
        self.url = url


def icloud_calendar_event(uid: str, summary: str, start_dt, organizer_email: str = "",
                          description: str = "", location: str = "", attendee_emails: list[str] | None = None) -> FakeCaldavEvent:
    organizer_line = f"ORGANIZER;CN=Organizer:mailto:{organizer_email}\n" if organizer_email else ""
    attendee_lines = "".join(f"ATTENDEE;CN=Guest:mailto:{e}\n" for e in (attendee_emails or []))
    ics = (
        "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//Test//EN\nBEGIN:VEVENT\n"
        f"UID:{uid}\nDTSTART:{start_dt.strftime('%Y%m%dT%H%M%SZ')}\nSUMMARY:{summary}\n"
        f"DESCRIPTION:{description}\nLOCATION:{location}\n{organizer_line}{attendee_lines}"
        "END:VEVENT\nEND:VCALENDAR\n"
    )
    return FakeCaldavEvent(ics, f"https://caldav.icloud.com/{uid}.ics")


def icloud_reminder(uid: str, summary: str, description: str = "", due_dt=None) -> FakeCaldavEvent:
    due_line = f"DUE:{due_dt.strftime('%Y%m%dT%H%M%SZ')}\n" if due_dt else ""
    ics = (
        "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//Test//EN\nBEGIN:VTODO\n"
        f"UID:{uid}\nSUMMARY:{summary}\nDESCRIPTION:{description}\n{due_line}"
        "END:VTODO\nEND:VCALENDAR\n"
    )
    return FakeCaldavEvent(ics, f"https://caldav.icloud.com/{uid}.ics")


class FakeCaldavCalendar:
    def __init__(self, name: str, events: list[FakeCaldavEvent] | None = None,
                 todos: list[FakeCaldavEvent] | None = None,
                 date_search_error: Exception | None = None) -> None:
        self.name = name
        self._events = events or []
        self._todos = todos or []
        self._date_search_error = date_search_error

    def date_search(self, start=None, end=None, expand=True):
        if self._date_search_error:
            raise self._date_search_error
        return self._events

    def todos(self):
        return self._todos


class FakeCaldavPrincipal:
    def __init__(self, calendars: list[FakeCaldavCalendar]) -> None:
        self._calendars = calendars

    def calendars(self):
        return self._calendars


class FakeCaldavClient:
    def __init__(self, calendars: list[FakeCaldavCalendar] | None = None, error: Exception | None = None) -> None:
        self._calendars = calendars or []
        self._error = error

    def principal(self):
        if self._error:
            raise self._error
        return FakeCaldavPrincipal(self._calendars)


@pytest.fixture()
def fake_caldav(monkeypatch):
    """Liefert eine Factory `set_calendars(calendars, error=None) -> FakeCaldavClient`.
    Patcht `caldav.DAVClient` direkt (Netzwerkgrenze) — dieselbe Grenze wird
    sowohl vom globalen iCloud-Kalender-/Erinnerungen-Sync (sync_icloud.py)
    als auch vom gezielten Einzelbewerbungs-Sync (sync_targeted.py) genutzt."""
    holder: dict[str, FakeCaldavClient] = {}

    def _fake_dav_client(url, username=None, password=None):
        return holder["client"]

    def set_calendars(calendars: list[FakeCaldavCalendar] | None = None, error: Exception | None = None) -> FakeCaldavClient:
        client = FakeCaldavClient(calendars, error)
        holder["client"] = client
        return client

    monkeypatch.setattr("caldav.DAVClient", _fake_dav_client)
    return set_calendars
