"""L3 Integration — _sync_gmail_for_app()/_sync_gcal_for_app() in sync_targeted.py.

Anders als der globale Sync (_do_gmail()/_do_gcal(), siehe test_gmail_sync.py /
test_google_calendar_sync.py) matcht der gezielte Sync nicht über Kontakte,
sondern über die E-Mail-Domain(s) der jeweiligen Firma (_company_domains_for_app).
Das ist die zentrale, bisher ungetestete Logik dieser beiden Funktionen — die
Klassifikation selbst (process_item / _classify_deterministic) ist bereits über
die globalen Sync-Tests abgedeckt.

Gmail nutzt hier — anders als _do_gmail() — keinen Batch-Request, sondern ruft
jede Nachricht direkt per messages().get(...).execute() ab. Der bestehende
fake_gmail (Batch-Fixture) passt daher nicht; dieses Modul bringt eine eigene,
schlankere Gmail-Fake mit.
"""
from __future__ import annotations

import base64
from datetime import date, datetime, timedelta, timezone

import pytest

from app import models
from app.routers.sync_targeted import _sync_gcal_for_app, _sync_gmail_for_app
from tests.factories import application_factory, company_profile_factory, contact_factory, event_factory

pytestmark = pytest.mark.integration


def _now_rfc2822() -> str:
    return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")


def _gmail_full_message(msg_id: str, sender: str, subject: str, body_text: str, date_str: str) -> dict:
    encoded = base64.urlsafe_b64encode(body_text.encode()).decode().rstrip("=")
    return {
        "id": msg_id,
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": sender},
                {"name": "Subject", "value": subject},
                {"name": "Date", "value": date_str},
            ],
            "body": {"data": encoded},
        },
    }


class _FakeGmailDirectExec:
    def __init__(self, data: dict) -> None:
        self._data = data

    def execute(self) -> dict:
        return self._data


class _FakeGmailDirectService:
    """Deckt die Direktabholung ohne Batch ab: list(...).execute() +
    get(...).execute() je Nachricht — genau der Aufrufpfad von
    _sync_gmail_for_app(), im Unterschied zu _do_gmail()'s Batch-Abholung."""

    def __init__(self, list_pages: list[dict], messages_full: dict[str, dict] | None = None,
                 list_error: Exception | None = None) -> None:
        self._list_pages = list(list_pages)
        self._messages_full = messages_full or {}
        self._list_error = list_error
        self.list_calls: list[dict] = []

    def users(self) -> "_FakeGmailDirectService":
        return self

    def messages(self) -> "_FakeGmailDirectService":
        return self

    def list(self, **kwargs) -> "_FakeGmailDirectService":
        self.list_calls.append(kwargs)
        return self

    def execute(self) -> dict:
        if self._list_error:
            raise self._list_error
        return self._list_pages.pop(0) if self._list_pages else {"messages": []}

    def get(self, userId, id, format=None) -> _FakeGmailDirectExec:
        return _FakeGmailDirectExec(self._messages_full[id])


@pytest.fixture()
def fake_gmail_direct(monkeypatch):
    holder: dict[str, _FakeGmailDirectService] = {}

    def _fake_build(serviceName, version, credentials=None, cache_discovery=True):
        assert serviceName == "gmail", f"Nur Gmail gemockt, nicht {serviceName!r}"
        return holder["service"]

    def set_service(list_pages, messages_full=None, list_error=None) -> _FakeGmailDirectService:
        service = _FakeGmailDirectService(list_pages, messages_full, list_error)
        holder["service"] = service
        return service

    monkeypatch.setattr("googleapiclient.discovery.build", _fake_build)
    return set_service


def _cal_event(event_id: str, summary: str, organizer_email: str, days_from_now: int = 0) -> dict:
    dt = datetime.now(timezone.utc) + timedelta(days=days_from_now)
    return {
        "id": event_id,
        "summary": summary,
        "description": "",
        "location": "",
        "start": {"dateTime": dt.isoformat()},
        "organizer": {"email": organizer_email, "displayName": "Recruiterin"},
        "attendees": [],
    }


class TestSyncGmailForApp:
    async def test_positiv_treffer_von_firmendomain_wird_angelegt(self, db_session, google_sync, fake_gmail_direct):
        profile = company_profile_factory(db_session, website="https://www.contoso.de/")
        app = application_factory(
            db_session, firma="Contoso AG", company_profile_id=profile.id,
            datum_bewerbung=date.today() - timedelta(days=30),
        )
        db_session.commit()

        msg = _gmail_full_message(
            "msg-1", "Recruiterin <recruiterin@contoso.de>", "Einladung zum Interview",
            "Wir würden Sie gerne zu einem Interview einladen.", _now_rfc2822(),
        )
        service = fake_gmail_direct([{"messages": [{"id": "msg-1"}]}], messages_full={"msg-1": msg})

        created, total, errors = await _sync_gmail_for_app(app, {"id": app.id, "firma": app.firma, "rolle": None, "is_headhunter": False}, [], db_session)

        assert errors == []
        assert created == 1
        assert total == 1
        assert "contoso.de" in service.list_calls[0]["q"]
        event = db_session.query(models.Event).filter_by(source="gmail", external_id="msg-1").one()
        assert event.application_id == app.id

    async def test_negativ_ohne_firmendomain_und_ohne_suchbegriffe_wird_uebersprungen(self, db_session, google_sync, fake_gmail_direct):
        # rolle="" (not the factory's random fake.job() default) so there's
        # truly nothing to search for — see the positive counterpart below,
        # which confirms company-name/role text alone (no domain) now DOES
        # trigger a search.
        app = application_factory(db_session, firma="Contoso AG", company_profile_id=None, rolle="")
        db_session.commit()
        service = fake_gmail_direct([])

        created, total, errors = await _sync_gmail_for_app(app, {"id": app.id, "firma": app.firma}, [], db_session)

        assert (created, total, errors) == (0, 0, [])
        assert service.list_calls == []  # gar keine Anfrage — Abbruch vor dem API-Call

    async def test_positiv_ohne_domain_aber_mit_suchbegriffen_wird_trotzdem_gesucht(self, db_session, google_sync, fake_gmail_direct):
        # terms simulates what _search_terms() produces: the role as ONE
        # whole phrase, not split into words — see the #230 false-positive
        # incident documented in _search_terms()'s docstring. A word-split
        # "Backend"/"Engineer" would each be far too generic to search alone.
        app = application_factory(db_session, firma="Contoso AG", company_profile_id=None, rolle="Backend Engineer")
        db_session.commit()
        service = fake_gmail_direct([])

        created, total, errors = await _sync_gmail_for_app(
            app, {"id": app.id, "firma": app.firma}, ["Contoso AG", "Contoso", "Backend Engineer"], db_session,
        )

        assert (created, total, errors) == (0, 0, [])
        assert len(service.list_calls) == 1
        query = service.list_calls[0]["q"]
        assert '"Contoso AG"' in query
        assert '"Contoso"' in query
        assert '"Backend Engineer"' in query
        assert '"Backend"' not in query
        assert '"Engineer"' not in query

    async def test_negativ_zu_viele_treffer_bricht_lauf_ohne_speichern_ab(self, db_session, google_sync, fake_gmail_direct):
        # Circuit breaker for the #230 incident class of bug: even if the
        # search terms turn out too generic and the query over-fetches, a
        # single run must not flood the timeline — it aborts and creates
        # nothing rather than silently ingesting everything.
        from app.routers.sync_targeted import _MAX_TARGETED_MAIL_MATCHES

        profile = company_profile_factory(db_session, website="https://www.contoso.de/")
        app = application_factory(
            db_session, firma="Contoso AG", company_profile_id=profile.id,
            datum_bewerbung=date.today() - timedelta(days=30),
        )
        db_session.commit()

        n = _MAX_TARGETED_MAIL_MATCHES + 1
        list_pages = [{"messages": [{"id": f"msg-{i}"} for i in range(n)]}]
        messages_full = {
            f"msg-{i}": _gmail_full_message(
                f"msg-{i}", "Recruiterin <recruiterin@contoso.de>", f"Interview {i}",
                "Wir würden Sie gerne zu einem Interview einladen.", _now_rfc2822(),
            )
            for i in range(n)
        }
        fake_gmail_direct(list_pages, messages_full=messages_full)

        created, total, errors = await _sync_gmail_for_app(
            app, {"id": app.id, "firma": app.firma, "rolle": None, "is_headhunter": False}, [], db_session,
        )

        assert created == 0
        assert len(errors) == 1
        assert str(_MAX_TARGETED_MAIL_MATCHES) in errors[0]
        assert db_session.query(models.Event).filter_by(source="gmail").count() == 0

    async def test_negativ_ungeprueftes_treffer_wird_bei_fehlendem_begriff_uebersprungen(
        self, db_session, google_sync, fake_gmail_direct
    ):
        # Defense-in-depth: even if the query somehow returns a message that
        # doesn't actually contain any real term/domain (query looseness,
        # provider quirk), it must not be blindly attributed to this
        # application just because hint_apps is hardcoded to it — see the
        # re-verification step in _sync_gmail_for_app.
        profile = company_profile_factory(db_session, website="https://www.contoso.de/")
        app = application_factory(
            db_session, firma="Contoso AG", company_profile_id=profile.id,
            datum_bewerbung=date.today() - timedelta(days=30),
        )
        db_session.commit()

        msg = _gmail_full_message(
            "msg-unrelated", "Newsletter <news@irgendwas-anderes.de>", "Wochenrückblick",
            "Diese Woche bei uns: nichts mit Contoso zu tun.", _now_rfc2822(),
        )
        fake_gmail_direct([{"messages": [{"id": "msg-unrelated"}]}], messages_full={"msg-unrelated": msg})

        created, total, errors = await _sync_gmail_for_app(
            app, {"id": app.id, "firma": app.firma, "rolle": None, "is_headhunter": False}, [], db_session,
        )

        assert errors == []
        assert created == 0
        assert db_session.query(models.Event).filter_by(source="gmail", external_id="msg-unrelated").first() is None

    async def test_negativ_google_nicht_verbunden_liefert_leeres_ergebnis(self, db_session):
        app = application_factory(db_session, firma="Contoso AG")
        db_session.commit()

        created, total, errors = await _sync_gmail_for_app(app, {"id": app.id, "firma": app.firma}, [], db_session)

        assert (created, total, errors) == (0, 0, [])

    async def test_negativ_gmail_api_fehler_bei_list_liefert_sauberen_fehler(self, db_session, google_sync, fake_gmail_direct):
        profile = company_profile_factory(db_session, website="https://www.contoso.de/")
        app = application_factory(db_session, firma="Contoso AG", company_profile_id=profile.id)
        db_session.commit()
        fake_gmail_direct([], list_error=RuntimeError("500 Internal Server Error"))

        created, total, errors = await _sync_gmail_for_app(app, {"id": app.id, "firma": app.firma}, [], db_session)

        assert created == 0
        assert any("Gmail API" in e for e in errors)

    async def test_negativ_mail_von_fremder_domain_erscheint_nicht_im_query(self, db_session, google_sync, fake_gmail_direct):
        # Contact-Domain wird zusätzlich zur Profil-Domain in die Query aufgenommen —
        # eine Domain, die zu keinem der beiden gehört, taucht nicht in q auf.
        profile = company_profile_factory(db_session, website="https://www.contoso.de/")
        app = application_factory(db_session, firma="Contoso AG", company_profile_id=profile.id)
        contact = contact_factory(db_session, email="recruiterin@contoso-agentur.de")
        app.contacts.append(contact)
        db_session.commit()

        service = fake_gmail_direct([{"messages": []}])
        await _sync_gmail_for_app(app, {"id": app.id, "firma": app.firma}, [], db_session)

        q = service.list_calls[0]["q"]
        assert "contoso.de" in q
        assert "contoso-agentur.de" in q
        assert "irgendwas.de" not in q


class TestSyncGcalForApp:
    async def test_positiv_termin_von_firmendomain_wird_angelegt(self, db_session, google_sync, fake_google_calendar):
        profile = company_profile_factory(db_session, website="https://www.contoso.de/")
        app = application_factory(db_session, firma="Contoso AG", company_profile_id=profile.id)
        db_session.commit()
        fake_google_calendar([_cal_event("evt-1", "Interview Runde 1", "recruiterin@contoso.de")])

        created, total, errors = await _sync_gcal_for_app(
            app, {"id": app.id, "firma": app.firma, "is_headhunter": False}, [], db_session,
        )

        assert errors == []
        assert created == 1
        assert total == 1
        db_session.flush()
        # Regression: external_id fehlte hier ursprünglich (im Unterschied zu allen anderen
        # Event-erzeugenden Pfaden in dieser Datei) — ohne es können list_candidates()/
        # manual_assign() dieses Event nicht per external_id wiederfinden/dedupen.
        event = db_session.query(models.Event).filter_by(source="gcal", external_id="evt-1").one()
        assert event.application_id == app.id

    async def test_negativ_termin_vor_fruehestem_ereignis_wird_ausgefiltert(
        self, db_session, google_sync, fake_google_calendar
    ):
        # Regression test for the #230 incident (2026-07-16), revised the
        # same day: the floor is now the earliest DATED EVENT already in
        # the application's timeline, not datum_bewerbung (which can be
        # later than when real preparation communication actually started,
        # and previously — before this whole date-floor mechanism existed —
        # was simply left unset, so nothing was ever filtered at all). An
        # existing event establishes the floor; a calendar event well
        # before it must still be excluded.
        profile = company_profile_factory(db_session, website="https://www.contoso.de/")
        app = application_factory(db_session, firma="Contoso AG", company_profile_id=profile.id)
        event_factory(db_session, app, datum=date.today() - timedelta(days=10), source="icloud_mail")
        db_session.commit()
        fake_google_calendar([
            _cal_event("evt-old", "Altes Gespräch", "recruiterin@contoso.de", days_from_now=-60),
        ])

        created, total, errors = await _sync_gcal_for_app(
            app, {"id": app.id, "firma": app.firma, "is_headhunter": False}, [], db_session,
        )

        assert errors == []
        assert created == 0
        assert db_session.query(models.Event).filter_by(source="gcal", external_id="evt-old").first() is None

    async def test_positiv_termin_vor_datum_bewerbung_aber_nach_fruehestem_ereignis_wird_akzeptiert(
        self, db_session, google_sync, fake_google_calendar
    ):
        # The concrete scenario the 2026-07-16 revision was requested for:
        # preparation communication (here, an earlier mail event) predating
        # the formal application date must not block a calendar event from
        # that same earlier period.
        profile = company_profile_factory(db_session, website="https://www.contoso.de/")
        app = application_factory(
            db_session, firma="Contoso AG", company_profile_id=profile.id,
            datum_bewerbung=date.today() - timedelta(days=5),
        )
        event_factory(db_session, app, datum=date.today() - timedelta(days=40), source="icloud_mail")
        db_session.commit()
        fake_google_calendar([
            _cal_event("evt-prep", "Vorbereitungsgespräch", "recruiterin@contoso.de", days_from_now=-35),
        ])

        created, total, errors = await _sync_gcal_for_app(
            app, {"id": app.id, "firma": app.firma, "is_headhunter": False}, [], db_session,
        )

        assert errors == []
        assert created == 1
        assert db_session.query(models.Event).filter_by(source="gcal", external_id="evt-prep").first() is not None

    async def test_negativ_domain_snapshot_in_app_dict_hat_vorrang_vor_live_kontakten(
        self, db_session, google_sync, fake_google_calendar
    ):
        # Regression test for the #230 followup incident: a sibling source
        # (e.g. mail, running concurrently in the same _do_sync() gather)
        # can add a contact to app.contacts moments before this function
        # computes its own domain list — without app_dict["_domain_snapshot"]
        # (computed once in _do_sync(), before any source runs), that
        # brand-new, unverified contact's domain would get treated as
        # trustworthy. Here the live contact's domain ("sideeffect.example")
        # is NOT in the snapshot (empty list, as _do_sync() would compute
        # before any contact existed) — a calendar event from that domain
        # must not match.
        app = application_factory(db_session, firma="Contoso AG", company_profile_id=None)
        contact = contact_factory(db_session, email="recruiterin@sideeffect.example")
        app.contacts.append(contact)
        db_session.commit()
        fake_google_calendar([_cal_event("evt-snapshot", "Interview", "recruiterin@sideeffect.example")])

        created, total, errors = await _sync_gcal_for_app(
            app, {"id": app.id, "firma": app.firma, "is_headhunter": False, "_domain_snapshot": []}, [], db_session,
        )

        assert errors == []
        assert created == 0
        assert db_session.query(models.Event).filter_by(source="gcal", external_id="evt-snapshot").first() is None

    async def test_negativ_termin_von_fremder_domain_wird_ausgefiltert(self, db_session, google_sync, fake_google_calendar):
        profile = company_profile_factory(db_session, website="https://www.contoso.de/")
        app = application_factory(db_session, firma="Contoso AG", company_profile_id=profile.id)
        db_session.commit()
        fake_google_calendar([_cal_event("evt-2", "Zahnarzttermin", "praxis@unbekannt.de")])

        created, total, errors = await _sync_gcal_for_app(
            app, {"id": app.id, "firma": app.firma, "is_headhunter": False}, [], db_session,
        )

        assert (created, total, errors) == (0, 0, [])
        assert db_session.query(models.Event).filter_by(source="gcal", external_id="evt-2").first() is None

    async def test_negativ_ohne_firmendomain_wird_uebersprungen(self, db_session, google_sync, fake_google_calendar):
        app = application_factory(db_session, firma="Contoso AG", company_profile_id=None)
        db_session.commit()
        service = fake_google_calendar([_cal_event("evt-3", "Irrelevant", "x@y.de")])

        created, total, errors = await _sync_gcal_for_app(
            app, {"id": app.id, "firma": app.firma, "is_headhunter": False}, [], db_session,
        )

        assert (created, total, errors) == (0, 0, [])
        assert service.list_calls == []

    async def test_negativ_headhunter_bewerbung_nutzt_ziel_und_hh_domain(self, db_session, google_sync, fake_google_calendar):
        target = company_profile_factory(db_session, website="https://www.contoso.de/")
        hh = company_profile_factory(db_session, website="https://www.headhunter-gmbh.de/")
        app = application_factory(
            db_session, firma="Headhunter GmbH", is_headhunter=True,
            company_profile_id=hh.id, target_company_profile_id=target.id,
        )
        db_session.commit()
        fake_google_calendar([_cal_event("evt-4", "Interview", "recruiterin@headhunter-gmbh.de")])

        created, total, errors = await _sync_gcal_for_app(
            app, {"id": app.id, "firma": app.firma, "is_headhunter": True}, [], db_session,
        )

        assert created == 1
