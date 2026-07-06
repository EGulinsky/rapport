"""L3 Integration — _sync_icloud_cal_for_app()/_sync_icloud_reminders_for_app()
in sync_targeted.py. Nutzt dieselbe CalDAV-Fake wie test_icloud_calendar_sync.py/
test_icloud_reminders_sync.py. Kalender matcht über Organizer-/Attendee-Domain
(wie beim gezielten Google-Calendar-Sync), Erinnerungen über Firmenbegriffs-
Text-Matching (wie iCloud-Notizen).
"""
from datetime import datetime, timezone

import pytest

from app import models
from app.routers.sync_targeted import _sync_icloud_cal_for_app, _sync_icloud_reminders_for_app
from tests.factories import application_factory, company_profile_factory
from tests.integration.conftest import FakeCaldavCalendar, icloud_calendar_event, icloud_reminder

pytestmark = pytest.mark.integration


class TestSyncIcloudCalForApp:
    async def test_positiv_termin_von_firmendomain_wird_angelegt(self, db_session, icloud_sync, fake_caldav):
        profile = company_profile_factory(db_session, website="https://www.contoso.de/")
        app = application_factory(db_session, firma="Contoso AG", company_profile_id=profile.id)
        db_session.commit()
        ev = icloud_calendar_event(
            "evt-1", "Interview Runde 1", datetime.now(timezone.utc), organizer_email="recruiterin@contoso.de",
        )
        fake_caldav([FakeCaldavCalendar("Kalender", events=[ev])])

        created, total, errors = await _sync_icloud_cal_for_app(
            app, {"id": app.id, "firma": app.firma, "is_headhunter": False}, [], db_session,
        )

        assert errors == []
        assert created == 1
        db_session.flush()
        event = db_session.query(models.Event).filter_by(source="icloud_cal", external_id="evt-1").one()
        assert event.application_id == app.id
        # Regression: derselbe vobj_str()-Bugfix wie beim globalen Sync gilt auch hier.
        assert event.titel == "Interview Runde 1"

    async def test_negativ_termin_von_fremder_domain_wird_ausgefiltert(self, db_session, icloud_sync, fake_caldav):
        profile = company_profile_factory(db_session, website="https://www.contoso.de/")
        app = application_factory(db_session, firma="Contoso AG", company_profile_id=profile.id)
        db_session.commit()
        ev = icloud_calendar_event(
            "evt-2", "Zahnarzttermin", datetime.now(timezone.utc), organizer_email="praxis@unbekannt.de",
        )
        fake_caldav([FakeCaldavCalendar("Kalender", events=[ev])])

        created, total, errors = await _sync_icloud_cal_for_app(
            app, {"id": app.id, "firma": app.firma, "is_headhunter": False}, [], db_session,
        )

        assert (created, errors) == (0, [])
        assert db_session.query(models.Event).filter_by(source="icloud_cal", external_id="evt-2").first() is None

    async def test_negativ_ohne_firmendomain_wird_uebersprungen(self, db_session, icloud_sync, fake_caldav):
        app = application_factory(db_session, firma="Contoso AG", company_profile_id=None)
        db_session.commit()
        ev = icloud_calendar_event("evt-3", "Irrelevant", datetime.now(timezone.utc), organizer_email="x@y.de")
        fake_caldav([FakeCaldavCalendar("Kalender", events=[ev])])

        created, total, errors = await _sync_icloud_cal_for_app(
            app, {"id": app.id, "firma": app.firma, "is_headhunter": False}, [], db_session,
        )

        assert (created, total, errors) == (0, 0, [])

    async def test_negativ_icloud_nicht_verbunden_liefert_leeres_ergebnis(self, db_session):
        app = application_factory(db_session, firma="Contoso AG")
        db_session.commit()

        created, total, errors = await _sync_icloud_cal_for_app(
            app, {"id": app.id, "firma": app.firma, "is_headhunter": False}, [], db_session,
        )

        assert (created, total, errors) == (0, 0, [])

    async def test_negativ_caldav_fehler_liefert_sauberen_fehler(self, db_session, icloud_sync, fake_caldav):
        profile = company_profile_factory(db_session, website="https://www.contoso.de/")
        app = application_factory(db_session, firma="Contoso AG", company_profile_id=profile.id)
        db_session.commit()
        fake_caldav(error=RuntimeError("401 Unauthorized"))

        created, total, errors = await _sync_icloud_cal_for_app(
            app, {"id": app.id, "firma": app.firma, "is_headhunter": False}, [], db_session,
        )

        assert created == 0
        assert any("iCloud CalDAV" in e for e in errors)


class TestSyncIcloudRemindersForApp:
    async def test_positiv_erinnerung_mit_suchbegriff_wird_angelegt(self, db_session, icloud_sync, fake_caldav):
        app = application_factory(db_session, firma="Contoso AG")
        db_session.commit()
        todo = icloud_reminder("todo-1", "Unterlagen für Contoso AG vorbereiten")
        fake_caldav([FakeCaldavCalendar("Erinnerungen", todos=[todo])])

        created, total, errors = await _sync_icloud_reminders_for_app(
            app, {"id": app.id, "firma": app.firma}, ["Contoso AG", "Contoso"], db_session,
        )

        assert errors == []
        assert created == 1
        db_session.flush()
        ev = db_session.query(models.Event).filter_by(source="icloud_todo", external_id="todo-1").one()
        assert ev.application_id == app.id
        assert ev.titel == "Unterlagen für Contoso AG vorbereiten"

    async def test_negativ_erinnerung_ohne_suchbegriff_wird_nicht_beruecksichtigt(self, db_session, icloud_sync, fake_caldav):
        app = application_factory(db_session, firma="Contoso AG")
        db_session.commit()
        todo = icloud_reminder("todo-2", "Milch kaufen")
        fake_caldav([FakeCaldavCalendar("Erinnerungen", todos=[todo])])

        created, total, errors = await _sync_icloud_reminders_for_app(
            app, {"id": app.id, "firma": app.firma}, ["Contoso AG", "Contoso"], db_session,
        )

        assert (created, total, errors) == (0, 0, [])

    async def test_negativ_icloud_nicht_verbunden_liefert_leeres_ergebnis(self, db_session):
        app = application_factory(db_session, firma="Contoso AG")
        db_session.commit()

        created, total, errors = await _sync_icloud_reminders_for_app(
            app, {"id": app.id, "firma": app.firma}, ["Contoso AG"], db_session,
        )

        assert (created, total, errors) == (0, 0, [])
