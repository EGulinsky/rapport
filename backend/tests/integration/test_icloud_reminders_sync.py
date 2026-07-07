"""L3 Integration — _do_icloud_reminders() in sync_icloud.py end-to-end.

Mockt an derselben Netzwerkgrenze wie test_icloud_calendar_sync.py
(caldav.DAVClient), nutzt aber VTODO statt VEVENT. Anders als beim
Kalender-Sync gibt es hier keinen Keyword-Fallback — nur Firmenname-Match
auf Titel+Beschreibung entscheidet, ob eine Erinnerung übernommen wird.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

from app import models
from app.routers.sync_icloud import _do_icloud_reminders
from tests.factories import application_factory
from tests.integration.conftest import FakeCaldavCalendar, icloud_reminder

pytestmark = pytest.mark.integration


class TestDoIcloudRemindersNichtVerbunden:
    async def test_negativ_keine_icloud_konfiguration_liefert_klaren_fehler(self, db_session):
        result = await _do_icloud_reminders(1)
        assert result["errors"] == ["Keine iCloud-Credentials gespeichert."]
        assert result["created"] == 0


class TestDoIcloudRemindersNeueErinnerungen:
    async def test_positiv_erinnerung_mit_firmenname_wird_angelegt(self, db_session, icloud_sync, fake_caldav):
        application_factory(db_session, firma="Contoso AG", datum_bewerbung=date.today() - timedelta(days=30))
        db_session.commit()
        todo = icloud_reminder("todo-1", "Unterlagen für Contoso AG vorbereiten", due_dt=datetime.now(timezone.utc) + timedelta(days=1))
        fake_caldav([FakeCaldavCalendar("Erinnerungen", todos=[todo])])

        result = await _do_icloud_reminders(1)

        assert result["errors"] == []
        assert result["created"] == 1
        event = db_session.query(models.Event).filter_by(source="icloud_todo", external_id="todo-1").one()
        # Regression: vorher landete hier '<SUMMARY{}...>' statt Klartext (Bug in
        # vobj_str()-Vorgänger-Code, str() direkt auf das ContentLine-Objekt).
        assert event.titel == "Unterlagen für Contoso AG vorbereiten"
        assert "<SUMMARY" not in event.titel

    async def test_negativ_erinnerung_ohne_firmenmatch_wird_uebersprungen(self, db_session, icloud_sync, fake_caldav):
        application_factory(db_session, firma="Contoso AG")
        db_session.commit()
        todo = icloud_reminder("todo-2", "Milch kaufen")
        fake_caldav([FakeCaldavCalendar("Erinnerungen", todos=[todo])])

        result = await _do_icloud_reminders(1)

        assert result["created"] == 0
        assert result["skipped"] == 1
        assert db_session.query(models.Event).filter_by(source="icloud_todo", external_id="todo-2").first() is None

    async def test_negativ_bereits_synctes_liefert_skip_ohne_erneute_verarbeitung(self, db_session, icloud_sync, fake_caldav):
        application_factory(db_session, firma="Contoso AG", datum_bewerbung=date.today() - timedelta(days=30))
        db_session.add(models.SyncedItem(source="icloud_todo", external_id="todo-3", user_id=1))
        db_session.commit()
        todo = icloud_reminder("todo-3", "Unterlagen für Contoso AG vorbereiten")
        fake_caldav([FakeCaldavCalendar("Erinnerungen", todos=[todo])])

        result = await _do_icloud_reminders(1)

        assert result["created"] == 0
        assert result["skipped"] == 1

    async def test_negativ_caldav_verbindungsfehler_liefert_sauberen_fehler(self, db_session, icloud_sync, fake_caldav):
        fake_caldav(error=RuntimeError("401 Unauthorized"))

        result = await _do_icloud_reminders(1)

        assert result["created"] == 0
        assert any("CalDAV-Fehler" in e for e in result["errors"])
