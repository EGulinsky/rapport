"""L3 Integration — _do_icloud_cal() in sync_icloud.py end-to-end.

Mockt an der Netzwerkgrenze (caldav.DAVClient, siehe
tests/integration/conftest.py::fake_caldav). Events werden dabei über ECHTES
vobject-Parsing eines .ics-Strings erzeugt (nicht per Hand-Stub) — nur so
deckt ein Test die reale Falle auf, str() direkt auf ein vobject-ContentLine-
Objekt anzuwenden (liefert '<SUMMARY{}Text>' statt 'Text'; siehe vobj_str()
in sync_common.py und die Regression unten).

Anders als beim Google-Calendar-Sync gibt es hier kein Kontakt-Matching,
sondern Keyword- (JOB_KEYWORDS) bzw. Firmenname-Textmatching auf Titel+
Beschreibung.
"""
import asyncio
import sys
import time
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app import models
from app.ai.provider import AINotConfigured, AIRateLimited
from app.routers.sync_icloud import _do_icloud_cal
from tests.factories import application_factory, seed_floor
from tests.integration.conftest import FakeCaldavCalendar, FakeCaldavEvent, icloud_calendar_event

pytestmark = pytest.mark.integration


class TestDoIcloudCalNichtVerbunden:
    async def test_negativ_keine_icloud_konfiguration_liefert_klaren_fehler(self, db_session):
        result = await _do_icloud_cal(1)
        assert result["errors"] == ["Keine iCloud-Credentials gespeichert."]
        assert result["created"] == 0


class TestDoIcloudCalNeueTermine:
    async def test_positiv_termin_mit_jobkeyword_wird_als_gespraech_angelegt(self, db_session, icloud_sync, fake_caldav):
        # find_hint_apps() matcht rein über den Firmennamen im Text (kein Kontakt-
        # Matching bei icloud_cal) — das Job-Keyword allein bestimmt nur, ob der
        # has_keyword/has_firm-Skip-Check passiert wird, nicht die App-Zuordnung.
        app = application_factory(db_session, firma="Contoso AG")
        seed_floor(db_session, app)
        db_session.commit()
        ev = icloud_calendar_event("evt-1", "Interview Runde 1 bei Contoso AG", datetime.now(timezone.utc))
        fake_caldav([FakeCaldavCalendar("Kalender", events=[ev])])

        result = await _do_icloud_cal(1)

        assert result["errors"] == []
        assert result["created"] == 1
        event = db_session.query(models.Event).filter_by(source="icloud_cal", external_id="evt-1").one()
        assert event.typ == "gespräch"
        # Regression: vorher landete hier '<SUMMARY{}Interview Runde 1 bei Contoso AG>'
        # (Bug in vobj_str()-Vorgänger-Code, str() direkt auf das ContentLine-Objekt).
        assert event.titel == "Interview Runde 1 bei Contoso AG"
        assert "<SUMMARY" not in event.titel

    async def test_negativ_termin_ohne_keyword_oder_firmenmatch_wird_uebersprungen(self, db_session, icloud_sync, fake_caldav):
        application_factory(db_session)
        db_session.commit()
        ev = icloud_calendar_event("evt-2", "Zahnarzttermin", datetime.now(timezone.utc))
        fake_caldav([FakeCaldavCalendar("Kalender", events=[ev])])

        result = await _do_icloud_cal(1)

        assert result["created"] == 0
        assert result["skipped"] == 1
        assert db_session.query(models.Event).filter_by(source="icloud_cal", external_id="evt-2").first() is None

    async def test_positiv_termin_mit_firmenname_wird_erkannt(self, db_session, icloud_sync, fake_caldav):
        app = application_factory(db_session, firma="Contoso AG")
        seed_floor(db_session, app)
        db_session.commit()
        ev = icloud_calendar_event("evt-3", "Meeting bei Contoso AG", datetime.now(timezone.utc))
        fake_caldav([FakeCaldavCalendar("Kalender", events=[ev])])

        result = await _do_icloud_cal(1)

        assert result["created"] == 1

    async def test_negativ_kalender_fehler_bei_date_search_wird_gesammelt_kein_abbruch(self, db_session, icloud_sync, fake_caldav):
        app = application_factory(db_session, firma="Contoso AG")
        seed_floor(db_session, app)
        db_session.commit()
        good_ev = icloud_calendar_event("evt-ok", "Interview bei Contoso AG", datetime.now(timezone.utc))
        broken_cal = FakeCaldavCalendar("Kaputt", date_search_error=RuntimeError("500 Server Error"))
        good_cal = FakeCaldavCalendar("Gut", events=[good_ev])
        fake_caldav([broken_cal, good_cal])

        result = await _do_icloud_cal(1)

        assert result["created"] == 1
        assert any("Kaputt" in e for e in result["errors"])

    async def test_negativ_caldav_verbindungsfehler_liefert_sauberen_fehler(self, db_session, icloud_sync, fake_caldav):
        fake_caldav(error=RuntimeError("401 Unauthorized"))

        result = await _do_icloud_cal(1)

        assert result["created"] == 0
        assert any("CalDAV-Fehler" in e for e in result["errors"])

    async def test_negativ_caldav_bibliothek_fehlt_liefert_klaren_fehler(self, db_session, icloud_sync, monkeypatch):
        monkeypatch.setitem(sys.modules, "caldav", None)

        result = await _do_icloud_cal(1)

        assert result["created"] == 0
        assert result["errors"] == ["caldav-Bibliothek nicht installiert."]

    async def test_positiv_ganztaegiger_termin_mit_reinem_datumswert_wird_verarbeitet(
        self, db_session, icloud_sync, fake_caldav
    ):
        # DTSTART;VALUE=DATE (ohne Uhrzeit) liefert ein `datetime.date`-Objekt
        # statt `datetime.datetime` — eigener Zweig in der dtstart-Typprüfung.
        app = application_factory(db_session, firma="Contoso AG")
        seed_floor(db_session, app)
        db_session.commit()
        allday = date.today()
        ics = (
            "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//Test//EN\nBEGIN:VEVENT\n"
            f"UID:evt-allday\nDTSTART;VALUE=DATE:{allday.strftime('%Y%m%d')}\nSUMMARY:Ganztag Interview bei Contoso AG\n"
            "END:VEVENT\nEND:VCALENDAR\n"
        )
        ev = FakeCaldavEvent(ics, "https://caldav.icloud.com/evt-allday.ics")
        fake_caldav([FakeCaldavCalendar("Kalender", events=[ev])])

        result = await _do_icloud_cal(1)

        assert result["errors"] == []
        assert result["created"] == 1
        event = db_session.query(models.Event).filter_by(source="icloud_cal", external_id="evt-allday").one()
        assert event.datum == allday

    async def test_negativ_ai_not_configured_beendet_sync_sauber(self, db_session, icloud_sync, fake_caldav, monkeypatch):
        application_factory(db_session, firma="Contoso AG", datum_bewerbung=date.today() - timedelta(days=30))
        db_session.commit()
        ev = icloud_calendar_event("evt-ai-1", "Interview bei Contoso AG", datetime.now(timezone.utc))
        fake_caldav([FakeCaldavCalendar("Kalender", events=[ev])])
        monkeypatch.setattr(
            "app.routers.sync_icloud.process_item",
            AsyncMock(side_effect=AINotConfigured("kein Provider konfiguriert")),
        )

        result = await _do_icloud_cal(1)

        assert result["created"] == 0
        assert any("kein Provider konfiguriert" in e for e in result["errors"])

    async def test_negativ_ai_rate_limited_beendet_sync_sauber(self, db_session, icloud_sync, fake_caldav, monkeypatch):
        application_factory(db_session, firma="Contoso AG", datum_bewerbung=date.today() - timedelta(days=30))
        db_session.commit()
        ev = icloud_calendar_event("evt-ai-2", "Interview bei Contoso AG", datetime.now(timezone.utc))
        fake_caldav([FakeCaldavCalendar("Kalender", events=[ev])])
        monkeypatch.setattr(
            "app.routers.sync_icloud.process_item",
            AsyncMock(side_effect=AIRateLimited("Tageslimit erreicht")),
        )

        result = await _do_icloud_cal(1)

        assert result["created"] == 0
        assert any("AI-Tageslimit" in e for e in result["errors"])

    async def test_negativ_unerwarteter_fehler_ausserhalb_der_termin_schleife_wird_gesammelt(
        self, db_session, icloud_sync, fake_caldav, monkeypatch
    ):
        fake_caldav([FakeCaldavCalendar("Kalender")])
        monkeypatch.setattr(
            "app.routers.sync_icloud.build_firm_index",
            lambda db: (_ for _ in ()).throw(RuntimeError("firm-index-boom")),
        )

        result = await _do_icloud_cal(1)

        assert result["created"] == 0
        assert any("firm-index-boom" in e for e in result["errors"])

    async def test_negativ_kaputtes_event_ohne_vevent_wird_still_uebersprungen(
        self, db_session, icloud_sync, fake_caldav
    ):
        app = application_factory(db_session, firma="Contoso AG")
        seed_floor(db_session, app)
        db_session.commit()

        class _BrokenEvent:
            url = "https://caldav.icloud.com/broken.ics"
            vobject_instance = object()  # kein .vevent-Attribut -> AttributeError

        good_ev = icloud_calendar_event("evt-good", "Interview bei Contoso AG", datetime.now(timezone.utc))
        fake_caldav([FakeCaldavCalendar("Kalender", events=[_BrokenEvent(), good_ev])])

        result = await _do_icloud_cal(1)

        assert result["created"] == 1
        assert result["errors"] == []

    async def test_negativ_event_ohne_dtstart_wird_uebersprungen(
        self, db_session, icloud_sync, fake_caldav
    ):
        # No DTSTART means no date_hint at all — "if there is absolutely no
        # date available, do not sync timed events at all" (2026-07-16):
        # excluded even with a floor present, since the item itself has
        # nothing to compare against.
        app = application_factory(db_session, firma="Contoso AG")
        seed_floor(db_session, app)
        db_session.commit()
        ics = (
            "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//Test//EN\nBEGIN:VEVENT\n"
            "UID:evt-no-dtstart\nSUMMARY:Interview bei Contoso AG\n"
            "END:VEVENT\nEND:VCALENDAR\n"
        )
        ev = FakeCaldavEvent(ics, "https://caldav.icloud.com/evt-no-dtstart.ics")
        fake_caldav([FakeCaldavCalendar("Kalender", events=[ev])])

        result = await _do_icloud_cal(1)

        assert result["errors"] == []
        assert result["created"] == 0
        assert db_session.query(models.Event).filter_by(source="icloud_cal", external_id="evt-no-dtstart").first() is None

    async def test_negativ_unerwarteter_fehler_bei_process_item_stoppt_nicht_den_gesamten_sync(
        self, db_session, icloud_sync, fake_caldav, monkeypatch
    ):
        application_factory(db_session, firma="Contoso AG", datum_bewerbung=date.today() - timedelta(days=30))
        db_session.commit()
        ev = icloud_calendar_event("evt-ai-3", "Interview bei Contoso AG", datetime.now(timezone.utc))
        fake_caldav([FakeCaldavCalendar("Kalender", events=[ev])])
        monkeypatch.setattr(
            "app.routers.sync_icloud.process_item",
            AsyncMock(side_effect=RuntimeError("process-item-boom")),
        )

        result = await _do_icloud_cal(1)

        assert result["created"] == 0
        assert any("process-item-boom" in e for e in result["errors"])


class TestDoIcloudCalAenderungserkennungUndVerwaisteTermine:
    async def test_positiv_geaenderter_titel_wird_bei_bereits_synctem_termin_aktualisiert(
        self, db_session, icloud_sync, fake_caldav
    ):
        app = application_factory(db_session, datum_bewerbung=date.today() - timedelta(days=30))
        existing = models.Event(
            application_id=app.id, typ="gespräch", titel="Altes Thema",
            datum=date.today(), source="icloud_cal", external_id="evt-4", user_id=1,
        )
        db_session.add(existing)
        db_session.add(models.SyncedItem(source="icloud_cal", external_id="evt-4", user_id=1))
        db_session.commit()

        ev = icloud_calendar_event("evt-4", "Neues Thema (Interview verschoben)", datetime.now(timezone.utc))
        fake_caldav([FakeCaldavCalendar("Kalender", events=[ev])])

        result = await _do_icloud_cal(1)

        assert result["skipped"] == 1
        db_session.refresh(existing)
        assert existing.titel == "Neues Thema (Interview verschoben)"

    async def test_positiv_verwaister_termin_ausserhalb_des_aktuellen_kalenders_wird_geloescht(
        self, db_session, icloud_sync, fake_caldav
    ):
        app = application_factory(db_session, datum_bewerbung=date.today() - timedelta(days=30))
        orphan = models.Event(
            application_id=app.id, typ="gespräch", titel="Abgesagtes Interview",
            datum=date.today(), source="icloud_cal", external_id="evt-orphan", user_id=1,
        )
        db_session.add(orphan)
        db_session.add(models.SyncedItem(source="icloud_cal", external_id="evt-orphan", user_id=1))
        db_session.commit()

        # Aktueller Kalenderabruf enthält "evt-orphan" nicht mehr — uid_set ist
        # trotzdem nicht leer, da ein anderer Termin zurückkommt.
        ev = icloud_calendar_event("evt-1", "Interview Runde 1", datetime.now(timezone.utc))
        fake_caldav([FakeCaldavCalendar("Kalender", events=[ev])])

        await _do_icloud_cal(1)

        assert db_session.query(models.Event).filter_by(external_id="evt-orphan").first() is None
        assert db_session.query(models.SyncedItem).filter_by(source="icloud_cal", external_id="evt-orphan").first() is None


class TestDoIcloudCalDoesNotBlockEventLoop:
    """Regression test for a real production incident (2026-07-14):
    _do_icloud_cal() used to call the synchronous caldav library directly
    inside an `async def`, which froze the WHOLE app's single event loop —
    not just this sync — for ~20 minutes when Apple's CalDAV server was
    slow to respond. Fixed by offloading the blocking calls to a thread via
    asyncio.to_thread() (see _caldav_calendars()/_caldav_collect_events()
    in sync_icloud.py).

    A normal mocked test can't catch this class of bug — the function
    returns the same RESULT whether or not the blocking call is offloaded,
    just at very different cost to the rest of the app while it runs. This
    test proves concurrency directly: a sibling coroutine's asyncio.sleep()
    must complete on schedule while the "slow" CalDAV call is in flight, not
    get delayed until it finishes."""

    async def test_positiv_langsamer_caldav_aufruf_blockiert_event_loop_nicht(
        self, db_session, icloud_sync, monkeypatch
    ):
        import caldav

        class _SlowPrincipal:
            def calendars(self):
                time.sleep(0.2)  # simulates a slow/hanging Apple CalDAV response
                return []

        class _SlowClient:
            def principal(self):
                return _SlowPrincipal()

        monkeypatch.setattr(caldav, "DAVClient", lambda url, username=None, password=None: _SlowClient())

        # Measured from BEFORE gather() starts, not from inside _heartbeat()
        # itself — if _heartbeat() timed its own start, that start would
        # already be delayed past the blocking call, making the elapsed
        # duration look fine regardless of whether the event loop was ever
        # actually blocked (this is exactly the mistake an earlier version
        # of this test made, and it passed even with the fix reverted).
        t0 = time.monotonic()

        async def _heartbeat() -> float:
            await asyncio.sleep(0.03)
            return time.monotonic() - t0

        _, heartbeat_elapsed = await asyncio.gather(_do_icloud_cal(1), _heartbeat())

        # If the blocking caldav call weren't offloaded to a thread, the event
        # loop couldn't even start _heartbeat()'s task until the 0.2s
        # synchronous call returned — heartbeat_elapsed would be ~0.2s instead
        # of ~0.03s. Generous margin against CI timing jitter either way.
        assert heartbeat_elapsed < 0.1
