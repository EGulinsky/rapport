"""L3 Integration — die fünf `_*_live_candidates()`-Helfer in sync_targeted.py
(Pool 3 von `list_candidates()`: Live-Volltextsuche gegen jede verbundene
externe Quelle, statt nur bereits synchronisierte/pending Items zu durchsuchen).

Jede Funktion patcht dieselbe Netzwerkgrenze wie die zugehörigen Sync-Funktionen
(googleapiclient.discovery.build, imaplib.IMAP4_SSL, caldav.DAVClient), ruft
aber andere, eigene API-Methoden auf (direkte q=-Suche bzw. SUBJECT/FROM-IMAP-
Suche statt Domain-Filterung) — daher eigene, schlankere Fakes statt der
bestehenden Sync-Fixtures.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.routers.sync_targeted import (
    _gcal_live_candidates,
    _gmail_live_candidates,
    _icloud_cal_live_candidates,
    _icloud_mail_live_candidates,
    _icloud_notes_live_candidates,
)
from tests.integration.conftest import icloud_email

pytestmark = pytest.mark.integration


# ── Gmail ────────────────────────────────────────────────────────────────────

class _FakeGmailLiveExec:
    def __init__(self, data: dict) -> None:
        self._data = data

    def execute(self) -> dict:
        return self._data


class _FakeGmailLiveService:
    def __init__(self, list_result: dict, metas: dict[str, dict] | None = None,
                 list_error: Exception | None = None) -> None:
        self._list_result = list_result
        self._metas = metas or {}
        self._list_error = list_error
        self.list_calls: list[dict] = []

    def users(self):
        return self

    def messages(self):
        return self

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        return self

    def execute(self):
        if self._list_error:
            raise self._list_error
        return self._list_result

    def get(self, userId, id, format=None, metadataHeaders=None):
        return _FakeGmailLiveExec(self._metas[id])


@pytest.fixture()
def fake_gmail_live(monkeypatch):
    holder: dict = {}

    def _fake_build(serviceName, version, credentials=None, cache_discovery=True):
        assert serviceName == "gmail"
        return holder["service"]

    def set_service(list_result, metas=None, list_error=None) -> _FakeGmailLiveService:
        service = _FakeGmailLiveService(list_result, metas, list_error)
        holder["service"] = service
        return service

    monkeypatch.setattr("googleapiclient.discovery.build", _fake_build)
    return set_service


def _gmail_meta(sender: str, subject: str, date_str: str) -> dict:
    return {"payload": {"headers": [
        {"name": "From", "value": sender},
        {"name": "Subject", "value": subject},
        {"name": "Date", "value": date_str},
    ]}}


class TestGmailLiveCandidates:
    def test_positiv_treffer_wird_als_kandidat_geliefert(self, db_session, google_sync, fake_gmail_live):
        service = fake_gmail_live(
            {"messages": [{"id": "msg-1"}]},
            metas={"msg-1": _gmail_meta("recruiterin@contoso.de", "Einladung", "Fri, 10 Jul 2026 10:00:00 +0000")},
        )

        out = _gmail_live_candidates("Contoso", 1, set(), db_session)

        assert len(out) == 1
        assert out[0]["source"] == "gmail"
        assert out[0]["external_id"] == "msg-1"
        assert out[0]["titel"] == "Einladung"
        assert service.list_calls[0]["q"] == "Contoso"

    def test_negativ_google_nicht_verbunden_liefert_leere_liste(self, db_session):
        assert _gmail_live_candidates("Contoso", 1, set(), db_session) == []

    def test_negativ_bereits_verknuepftes_event_wird_ausgefiltert(self, db_session, google_sync, fake_gmail_live):
        from tests.factories import application_factory, event_factory

        app = application_factory(db_session)
        event_factory(db_session, app, source="gmail", external_id="msg-1")
        db_session.commit()
        fake_gmail_live({"messages": [{"id": "msg-1"}]})

        out = _gmail_live_candidates("Contoso", app.id, set(), db_session)

        assert out == []

    def test_negativ_bereits_gesehene_id_wird_dedupliziert(self, db_session, google_sync, fake_gmail_live):
        fake_gmail_live(
            {"messages": [{"id": "msg-1"}]},
            metas={"msg-1": _gmail_meta("x@contoso.de", "Betreff", "")},
        )
        seen = {"gmail:msg-1"}

        out = _gmail_live_candidates("Contoso", 1, seen, db_session)

        assert out == []


# ── Google Calendar ──────────────────────────────────────────────────────────

class _FakeGcalLiveExec:
    def __init__(self, data: dict) -> None:
        self._data = data

    def execute(self) -> dict:
        return self._data


class _FakeGcalLiveService:
    def __init__(self, cal_list: dict, events_by_cal: dict[str, dict] | None = None,
                 events_errors: dict[str, Exception] | None = None) -> None:
        self._cal_list = cal_list
        self._events_by_cal = events_by_cal or {}
        self._events_errors = events_errors or {}
        self.events_calls: list[dict] = []

    def calendarList(self):
        return self

    def events(self):
        return self

    def list(self, **kwargs):
        if "calendarId" in kwargs:
            self.events_calls.append(kwargs)
            cal_id = kwargs["calendarId"]
            if cal_id in self._events_errors:
                return _FakeGcalLiveExecError(self._events_errors[cal_id])
            return _FakeGcalLiveExec(self._events_by_cal.get(cal_id, {"items": []}))
        return _FakeGcalLiveExec(self._cal_list)


class _FakeGcalLiveExecError:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def execute(self):
        raise self._error


@pytest.fixture()
def fake_gcal_live(monkeypatch):
    holder: dict = {}

    def _fake_build(serviceName, version, credentials=None, cache_discovery=True):
        assert serviceName == "calendar"
        return holder["service"]

    def set_service(cal_list, events_by_cal=None, events_errors=None) -> _FakeGcalLiveService:
        service = _FakeGcalLiveService(cal_list, events_by_cal, events_errors)
        holder["service"] = service
        return service

    monkeypatch.setattr("googleapiclient.discovery.build", _fake_build)
    return set_service


class TestGcalLiveCandidates:
    def test_positiv_treffer_wird_als_kandidat_geliefert(self, db_session, google_sync, fake_gcal_live):
        dt = datetime.now(timezone.utc)
        fake_gcal_live(
            {"items": [{"id": "primary", "summary": "Mein Kalender"}]},
            events_by_cal={"primary": {"items": [
                {"id": "evt-1", "summary": "Interview Contoso", "start": {"dateTime": dt.isoformat()}, "description": "Gespräch"},
            ]}},
        )

        out = _gcal_live_candidates("Contoso", 1, set(), db_session)

        assert len(out) == 1
        assert out[0]["source"] == "gcal"
        assert out[0]["external_id"] == "evt-1"
        assert out[0]["titel"] == "Interview Contoso"

    def test_negativ_google_nicht_verbunden_liefert_leere_liste(self, db_session):
        assert _gcal_live_candidates("Contoso", 1, set(), db_session) == []

    def test_negativ_calendarlist_fehler_liefert_leere_liste(self, db_session, google_sync, monkeypatch):
        def _fake_build(serviceName, version, credentials=None, cache_discovery=True):
            class _Boom:
                def calendarList(self):
                    return self

                def list(self):
                    return self

                def execute(self):
                    raise RuntimeError("500")
            return _Boom()

        monkeypatch.setattr("googleapiclient.discovery.build", _fake_build)

        assert _gcal_live_candidates("Contoso", 1, set(), db_session) == []

    def test_negativ_einzelner_kalender_fehler_wird_uebersprungen(self, db_session, google_sync, fake_gcal_live):
        # Kalender "kaputt" wirft beim events().list() — die Funktion überspringt
        # ihn still und liefert weiterhin die Treffer aus dem funktionierenden
        # zweiten Kalender.
        dt = datetime.now(timezone.utc)
        fake_gcal_live(
            {"items": [
                {"id": "kaputt", "summary": "Kaputt"},
                {"id": "primary", "summary": "Mein Kalender"},
            ]},
            events_by_cal={"primary": {"items": [
                {"id": "evt-1", "summary": "Interview Contoso", "start": {"dateTime": dt.isoformat()}, "description": ""},
            ]}},
            events_errors={"kaputt": RuntimeError("403")},
        )

        out = _gcal_live_candidates("Contoso", 1, set(), db_session)

        assert len(out) == 1
        assert out[0]["external_id"] == "evt-1"


# ── iCloud Mail ──────────────────────────────────────────────────────────────

class TestIcloudMailLiveCandidates:
    def test_positiv_treffer_wird_als_kandidat_geliefert(self, db_session, icloud_sync, fake_icloud_imap):
        msg_id, msg = icloud_email(
            "1", "Recruiterin <recruiterin@contoso.de>", "Einladung zum Interview",
            "Text", "Fri, 10 Jul 2026 10:00:00 +0000",
        )
        conn = fake_icloud_imap(["1"], {msg_id: msg})

        out = _icloud_mail_live_candidates("Contoso", 1, set(), db_session)

        assert len(out) == 1
        assert out[0]["source"] == "icloud_mail"
        assert out[0]["external_id"] == "1"
        assert any('SUBJECT "Contoso"' in c for c in conn.search_calls)
        assert any('FROM "Contoso"' in c for c in conn.search_calls)

    def test_negativ_icloud_nicht_verbunden_liefert_leere_liste(self, db_session):
        assert _icloud_mail_live_candidates("Contoso", 1, set(), db_session) == []

    def test_negativ_bereits_verknuepftes_event_wird_ausgefiltert(self, db_session, icloud_sync, fake_icloud_imap):
        from tests.factories import application_factory, event_factory

        app = application_factory(db_session)
        event_factory(db_session, app, source="icloud_mail", external_id="1")
        db_session.commit()
        msg_id, msg = icloud_email("1", "x@contoso.de", "Betreff", "Text", "Fri, 10 Jul 2026 10:00:00 +0000")
        fake_icloud_imap(["1"], {msg_id: msg})

        out = _icloud_mail_live_candidates("Contoso", app.id, set(), db_session)

        assert out == []

    def test_negativ_imap_fehler_liefert_leere_liste(self, db_session, icloud_sync, monkeypatch):
        def _raise(host, port):
            raise ConnectionError("kaputt")

        monkeypatch.setattr("imaplib.IMAP4_SSL", _raise)

        assert _icloud_mail_live_candidates("Contoso", 1, set(), db_session) == []


# ── iCloud Calendar ───────────────────────────────────────────────────────────

class _FakeIcalEvent:
    """Test-Double für ein caldav-Event, wie es `_icloud_cal_live_candidates()`
    konsumiert — anders als der reguläre Sync (`.vobject_instance.vevent`)
    nutzt diese Funktion `.icalendar_component` (die `icalendar`-Bibliothek,
    ebenfalls eine caldav-Abhängigkeit, statt `vobject`)."""

    def __init__(self, ics_text: str) -> None:
        import icalendar
        cal = icalendar.Calendar.from_ical(ics_text)
        self.icalendar_component = next(iter(cal.walk("VEVENT")))


def _ical_event(uid: str, summary: str, dt: datetime, description: str = "") -> _FakeIcalEvent:
    ics = (
        "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//Test//EN\nBEGIN:VEVENT\n"
        f"UID:{uid}\nDTSTART:{dt.strftime('%Y%m%dT%H%M%SZ')}\nSUMMARY:{summary}\n"
        f"DESCRIPTION:{description}\nEND:VEVENT\nEND:VCALENDAR\n"
    )
    return _FakeIcalEvent(ics)


class TestIcloudCalLiveCandidates:
    def test_positiv_treffer_wird_als_kandidat_geliefert(self, db_session, icloud_sync, fake_caldav):
        from tests.integration.conftest import FakeCaldavCalendar

        ev = _ical_event("evt-1", "Interview Contoso", datetime.now(timezone.utc), description="Gespräch")
        fake_caldav([FakeCaldavCalendar("Kalender", events=[ev])])

        out = _icloud_cal_live_candidates("Contoso", 1, set(), db_session)

        assert len(out) == 1
        assert out[0]["source"] == "icloud_cal"
        assert out[0]["external_id"] == "evt-1"
        assert out[0]["titel"] == "Interview Contoso"

    def test_negativ_ohne_textmatch_liefert_leere_liste(self, db_session, icloud_sync, fake_caldav):
        from tests.integration.conftest import FakeCaldavCalendar

        ev = _ical_event("evt-2", "Zahnarzttermin", datetime.now(timezone.utc))
        fake_caldav([FakeCaldavCalendar("Kalender", events=[ev])])

        assert _icloud_cal_live_candidates("Contoso", 1, set(), db_session) == []

    def test_negativ_icloud_nicht_verbunden_liefert_leere_liste(self, db_session):
        assert _icloud_cal_live_candidates("Contoso", 1, set(), db_session) == []

    def test_negativ_caldav_fehler_liefert_leere_liste(self, db_session, icloud_sync, fake_caldav):
        fake_caldav(error=RuntimeError("401"))

        assert _icloud_cal_live_candidates("Contoso", 1, set(), db_session) == []

    def test_negativ_kaputtes_event_wird_still_uebersprungen(self, db_session, icloud_sync, fake_caldav):
        from tests.integration.conftest import FakeCaldavCalendar

        class _Broken:
            @property
            def icalendar_component(self):
                raise AttributeError("kaputt")

        fake_caldav([FakeCaldavCalendar("Kalender", events=[_Broken()])])

        assert _icloud_cal_live_candidates("Contoso", 1, set(), db_session) == []


# ── iCloud Notizen ────────────────────────────────────────────────────────────

class _FakeNotesService:
    def __init__(self, notes: list[dict]) -> None:
        self._notes = notes

    def get_notes(self) -> list[dict]:
        return self._notes


class _FakePyicloudApi:
    def __init__(self, notes: list[dict]) -> None:
        self.notes = _FakeNotesService(notes)


class TestIcloudNotesLiveCandidates:
    def test_positiv_treffer_wird_als_kandidat_geliefert(self, db_session, monkeypatch):
        from app import models
        from app.ai.provider import encrypt_api_key

        cfg = models.ICloudSync(
            apple_id="test@example.com", app_password_enc=encrypt_api_key("app-pw"),
            web_password_enc=encrypt_api_key("web-pw"), user_id=1,
        )
        db_session.add(cfg)
        db_session.commit()

        notes = [{"title": "Contoso Vorbereitung", "body": "Fragen für Contoso", "id": "note-1"}]
        monkeypatch.setattr(
            "app.routers.sync_icloud._get_pyicloud_api",
            lambda cfg_arg, force_new=False: _FakePyicloudApi(notes),
        )

        out = _icloud_notes_live_candidates("Contoso", 1, set(), db_session)

        assert len(out) == 1
        assert out[0]["source"] == "icloud_notes"
        assert out[0]["external_id"] == "note-1"
        assert out[0]["titel"] == "Contoso Vorbereitung"

    def test_negativ_ohne_web_passwort_liefert_leere_liste(self, db_session):
        from app import models
        from app.ai.provider import encrypt_api_key

        db_session.add(models.ICloudSync(
            apple_id="test@example.com", app_password_enc=encrypt_api_key("app-pw"), user_id=1,
        ))
        db_session.commit()

        assert _icloud_notes_live_candidates("Contoso", 1, set(), db_session) == []

    def test_negativ_icloud_nicht_verbunden_liefert_leere_liste(self, db_session):
        assert _icloud_notes_live_candidates("Contoso", 1, set(), db_session) == []

    def test_negativ_pyicloud_fehler_liefert_leere_liste(self, db_session, monkeypatch):
        from app import models
        from app.ai.provider import encrypt_api_key

        cfg = models.ICloudSync(
            apple_id="test@example.com", app_password_enc=encrypt_api_key("app-pw"),
            web_password_enc=encrypt_api_key("web-pw"), user_id=1,
        )
        db_session.add(cfg)
        db_session.commit()

        def _raise(cfg_arg, force_new=False):
            raise RuntimeError("Login fehlgeschlagen")

        monkeypatch.setattr("app.routers.sync_icloud._get_pyicloud_api", _raise)

        assert _icloud_notes_live_candidates("Contoso", 1, set(), db_session) == []
