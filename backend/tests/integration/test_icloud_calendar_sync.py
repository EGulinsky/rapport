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
from datetime import date, datetime, timedelta, timezone

import pytest

from app import models
from app.routers.sync_icloud import _do_icloud_cal
from tests.factories import application_factory
from tests.integration.conftest import FakeCaldavCalendar, icloud_calendar_event

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
        application_factory(db_session, firma="Contoso AG", datum_bewerbung=date.today() - timedelta(days=30))
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
        application_factory(db_session, firma="Contoso AG", datum_bewerbung=date.today() - timedelta(days=30))
        db_session.commit()
        ev = icloud_calendar_event("evt-3", "Meeting bei Contoso AG", datetime.now(timezone.utc))
        fake_caldav([FakeCaldavCalendar("Kalender", events=[ev])])

        result = await _do_icloud_cal(1)

        assert result["created"] == 1

    async def test_negativ_kalender_fehler_bei_date_search_wird_gesammelt_kein_abbruch(self, db_session, icloud_sync, fake_caldav):
        application_factory(db_session, firma="Contoso AG", datum_bewerbung=date.today() - timedelta(days=30))
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
