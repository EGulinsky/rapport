"""L3 Integration — _do_icloud_reminders() in sync_icloud.py end-to-end.

Mockt an derselben Netzwerkgrenze wie test_icloud_calendar_sync.py
(caldav.DAVClient), nutzt aber VTODO statt VEVENT. Anders als beim
Kalender-Sync gibt es hier keinen Keyword-Fallback — nur Firmenname-Match
auf Titel+Beschreibung entscheidet, ob eine Erinnerung übernommen wird.
"""
import sys
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app import models
from app.ai.provider import AINotConfigured, AIRateLimited
from app.routers.sync_icloud import _do_icloud_reminders
from tests.factories import application_factory, seed_floor
from tests.integration.conftest import FakeCaldavCalendar, FakeCaldavEvent, icloud_reminder

pytestmark = pytest.mark.integration


class TestDoIcloudRemindersNichtVerbunden:
    async def test_negativ_keine_icloud_konfiguration_liefert_klaren_fehler(self, db_session):
        result = await _do_icloud_reminders(1)
        assert result["errors"] == ["Keine iCloud-Credentials gespeichert."]
        assert result["created"] == 0


class TestDoIcloudRemindersNeueErinnerungen:
    async def test_positiv_erinnerung_mit_firmenname_wird_angelegt(self, db_session, icloud_sync, fake_caldav):
        app = application_factory(db_session, firma="Contoso AG")
        seed_floor(db_session, app)
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

    async def test_negativ_caldav_bibliothek_fehlt_liefert_klaren_fehler(self, db_session, icloud_sync, monkeypatch):
        monkeypatch.setitem(sys.modules, "caldav", None)

        result = await _do_icloud_reminders(1)

        assert result["created"] == 0
        assert result["errors"] == ["caldav-Bibliothek nicht installiert."]

    async def test_negativ_einzelner_kalender_fehler_bei_todos_wird_still_uebersprungen(
        self, db_session, icloud_sync, fake_caldav
    ):
        # todos() fehlt auf VTODO-Ebene ein Fehler-Sammelmechanismus wie beim
        # Kalender-Sync (date_search) — ein einzelner kaputter Kalender wird
        # stillschweigend übersprungen, statt den gesamten Sync abzubrechen.
        app = application_factory(db_session, firma="Contoso AG")
        seed_floor(db_session, app)
        db_session.commit()
        good_todo = icloud_reminder("todo-ok", "Unterlagen für Contoso AG vorbereiten", due_dt=datetime.now(timezone.utc))
        broken_cal = FakeCaldavCalendar("Kaputt")

        def _raise_todos():
            raise RuntimeError("500 Server Error")

        broken_cal.todos = _raise_todos
        good_cal = FakeCaldavCalendar("Gut", todos=[good_todo])
        fake_caldav([broken_cal, good_cal])

        result = await _do_icloud_reminders(1)

        assert result["created"] == 1
        assert result["errors"] == []

    async def test_positiv_erinnerung_mit_reinem_datumswert_wird_verarbeitet(self, db_session, icloud_sync, fake_caldav):
        # DUE;VALUE=DATE (ohne Uhrzeit) liefert ein `datetime.date`-Objekt statt
        # `datetime.datetime` — eigener Zweig in der due-Typprüfung.
        app = application_factory(db_session, firma="Contoso AG")
        seed_floor(db_session, app)
        db_session.commit()
        due = date.today() + timedelta(days=2)
        ics = (
            "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//Test//EN\nBEGIN:VTODO\n"
            f"UID:todo-allday\nSUMMARY:Unterlagen für Contoso AG vorbereiten\nDUE;VALUE=DATE:{due.strftime('%Y%m%d')}\n"
            "END:VTODO\nEND:VCALENDAR\n"
        )
        todo = FakeCaldavEvent(ics, "https://caldav.icloud.com/todo-allday.ics")
        fake_caldav([FakeCaldavCalendar("Erinnerungen", todos=[todo])])

        result = await _do_icloud_reminders(1)

        assert result["errors"] == []
        assert result["created"] == 1

    async def test_negativ_ai_not_configured_beendet_sync_sauber(self, db_session, icloud_sync, fake_caldav, monkeypatch):
        application_factory(db_session, firma="Contoso AG", datum_bewerbung=date.today() - timedelta(days=30))
        db_session.commit()
        todo = icloud_reminder("todo-ai-1", "Unterlagen für Contoso AG vorbereiten")
        fake_caldav([FakeCaldavCalendar("Erinnerungen", todos=[todo])])
        monkeypatch.setattr(
            "app.routers.sync_icloud.process_item",
            AsyncMock(side_effect=AINotConfigured("kein Provider konfiguriert")),
        )

        result = await _do_icloud_reminders(1)

        assert result["created"] == 0
        assert any("kein Provider konfiguriert" in e for e in result["errors"])

    async def test_negativ_ai_rate_limited_beendet_sync_sauber(self, db_session, icloud_sync, fake_caldav, monkeypatch):
        application_factory(db_session, firma="Contoso AG", datum_bewerbung=date.today() - timedelta(days=30))
        db_session.commit()
        todo = icloud_reminder("todo-ai-2", "Unterlagen für Contoso AG vorbereiten")
        fake_caldav([FakeCaldavCalendar("Erinnerungen", todos=[todo])])
        monkeypatch.setattr(
            "app.routers.sync_icloud.process_item",
            AsyncMock(side_effect=AIRateLimited("Tageslimit erreicht")),
        )

        result = await _do_icloud_reminders(1)

        assert result["created"] == 0
        assert any("AI-Tageslimit" in e for e in result["errors"])

    async def test_negativ_unerwarteter_fehler_ausserhalb_der_erinnerungs_schleife_wird_gesammelt(
        self, db_session, icloud_sync, fake_caldav, monkeypatch
    ):
        fake_caldav([FakeCaldavCalendar("Erinnerungen")])
        monkeypatch.setattr(
            "app.routers.sync_icloud.build_firm_index",
            lambda db: (_ for _ in ()).throw(RuntimeError("firm-index-boom")),
        )

        result = await _do_icloud_reminders(1)

        assert result["created"] == 0
        assert any("firm-index-boom" in e for e in result["errors"])

    async def test_negativ_kaputte_erinnerung_ohne_vtodo_wird_still_uebersprungen(
        self, db_session, icloud_sync, fake_caldav
    ):
        app = application_factory(db_session, firma="Contoso AG")
        seed_floor(db_session, app)
        db_session.commit()

        class _BrokenTodo:
            url = "https://caldav.icloud.com/broken.ics"
            vobject_instance = object()  # kein .vtodo-Attribut -> AttributeError

        good_todo = icloud_reminder("todo-good", "Unterlagen für Contoso AG vorbereiten", due_dt=datetime.now(timezone.utc))
        fake_caldav([FakeCaldavCalendar("Erinnerungen", todos=[_BrokenTodo(), good_todo])])

        result = await _do_icloud_reminders(1)

        assert result["created"] == 1
        assert result["errors"] == []

    async def test_negativ_unerwarteter_fehler_bei_process_item_stoppt_nicht_den_gesamten_sync(
        self, db_session, icloud_sync, fake_caldav, monkeypatch
    ):
        application_factory(db_session, firma="Contoso AG", datum_bewerbung=date.today() - timedelta(days=30))
        db_session.commit()
        todo = icloud_reminder("todo-ai-3", "Unterlagen für Contoso AG vorbereiten")
        fake_caldav([FakeCaldavCalendar("Erinnerungen", todos=[todo])])
        monkeypatch.setattr(
            "app.routers.sync_icloud.process_item",
            AsyncMock(side_effect=RuntimeError("process-item-boom")),
        )

        result = await _do_icloud_reminders(1)

        assert result["created"] == 0
        assert any("process-item-boom" in e for e in result["errors"])
