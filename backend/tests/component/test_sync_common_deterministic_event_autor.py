"""L1 Component -- _save_deterministic_event() in sync_common.py: Event.autor
population for mail events (gmail/icloud_mail).

The Event.autor column ("sender for mail events") already existed in the
schema, but only the unused AI-confidence path (save_classified_event())
ever wrote to it -- the actual production path (process_item() ->
_classify_deterministic() -> _save_deterministic_event()) silently left it
NULL for every mail event ever synced. Fixed so ContactModal's "Mails" tab
(matching mail events back to a contact by sender address) has something to
match against going forward.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

from app import models
from app.routers.sync_common import _save_deterministic_event
from tests.factories import application_factory, event_factory

pytestmark = pytest.mark.component

_RECENT = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc) - timedelta(days=1)


def _seed_floor(db_session, app, days_ago=60):
    event_factory(db_session, app, datum=date.today() - timedelta(days=days_ago), source="gcal")


def _det(app_id, titel="Rückmeldung", typ="notiz"):
    return {"app_id": app_id, "typ": typ, "titel": titel, "notiz": None, "reason": "test"}


class TestSaveDeterministicEventAutor:
    def test_positiv_autor_wird_aus_von_zeile_gesetzt(self, db_session):
        app = application_factory(db_session)
        _seed_floor(db_session, app)
        db_session.commit()

        raw_text = "Von: Anna Recruiterin <anna@contoso.example>\nBetreff: Ihre Bewerbung\n\nHallo,\n..."
        created = _save_deterministic_event(
            db_session, "gmail", "msg-1", _det(app.id), raw_text, date_hint=_RECENT, user_id=None,
        )

        assert created is True
        event = db_session.query(models.Event).filter_by(application_id=app.id, source="gmail").first()
        assert event.autor == "Anna Recruiterin <anna@contoso.example>"

    def test_positiv_autor_wird_aus_from_zeile_gesetzt(self, db_session):
        app = application_factory(db_session)
        _seed_floor(db_session, app)
        db_session.commit()

        raw_text = "From: Ben Recruiter <ben@contoso.example>\nSubject: Your application\n\nHi,\n..."
        _save_deterministic_event(
            db_session, "icloud_mail", "msg-2", _det(app.id), raw_text, date_hint=_RECENT, user_id=None,
        )

        event = db_session.query(models.Event).filter_by(application_id=app.id, source="icloud_mail").first()
        assert event.autor == "Ben Recruiter <ben@contoso.example>"

    def test_negativ_kein_autor_ohne_von_from_zeile(self, db_session):
        app = application_factory(db_session)
        _seed_floor(db_session, app)
        db_session.commit()

        raw_text = "Betreff: Kein Absender im Text\n\nHallo,\n..."
        _save_deterministic_event(
            db_session, "gmail", "msg-3", _det(app.id), raw_text, date_hint=_RECENT, user_id=None,
        )

        event = db_session.query(models.Event).filter_by(application_id=app.id, source="gmail").first()
        assert event.autor is None

    def test_negativ_autor_bleibt_leer_fuer_nicht_mail_quellen(self, db_session):
        # Calendar/notes/calls etc. never had sender headers to begin with --
        # must not pick up an accidental "Von:"/"From:" match from unrelated text.
        app = application_factory(db_session)
        _seed_floor(db_session, app)
        db_session.commit()

        raw_text = "Von: Sollte ignoriert werden\nTitel: Vorstellungsgespräch"
        _save_deterministic_event(
            db_session, "gcal", "evt-1", _det(app.id, typ="gespräch"), raw_text, date_hint=_RECENT, user_id=None,
        )

        event = db_session.query(models.Event).filter_by(application_id=app.id, source="gcal").first()
        assert event.autor is None

    def test_positiv_kontakt_wird_weiterhin_aus_absender_angelegt(self, db_session):
        # Regression guard: the auto-create-contact-from-sender side effect
        # (previously driven by its own re-parse of raw_text) must keep working
        # now that it's driven by the already-extracted `autor` variable instead.
        app = application_factory(db_session, firma="Contoso AG")
        _seed_floor(db_session, app)
        db_session.commit()

        raw_text = "Von: Carla Fuchs <carla@contoso-ag.example>\nBetreff: Terminvorschlag\n\nHallo,\n..."
        _save_deterministic_event(
            db_session, "gmail", "msg-4", _det(app.id), raw_text, date_hint=_RECENT, user_id=None,
        )

        contact = db_session.query(models.Contact).filter_by(email="carla@contoso-ag.example").first()
        assert contact is not None
        assert contact.name == "Carla Fuchs"
        assert contact.vorname == "Carla"


class TestSaveDeterministicEventDatumZeit:
    """Event.datum stays date-only (unchanged); datum_zeit carries the full
    timestamp when the sync source had one, so same-day events can still be
    told apart chronologically (see ARCHITECTURE.md's timeline-sort note)."""

    def test_positiv_datum_zeit_wird_aus_date_hint_gesetzt(self, db_session):
        app = application_factory(db_session)
        _seed_floor(db_session, app)
        db_session.commit()

        hint = datetime(2026, 7, 18, 14, 32, 0, tzinfo=timezone.utc)
        raw_text = "Von: Anna Recruiterin <anna@contoso.example>\nBetreff: Ihre Bewerbung\n\nHallo,\n..."
        _save_deterministic_event(
            db_session, "gmail", "msg-5", _det(app.id), raw_text, date_hint=hint, user_id=None,
        )

        event = db_session.query(models.Event).filter_by(application_id=app.id, source="gmail").first()
        assert event.datum == date(2026, 7, 18)
        assert event.datum_zeit == datetime(2026, 7, 18, 14, 32, 0)

    def test_positiv_datum_zeit_gilt_auch_fuer_kalendertermine(self, db_session):
        # _save_deterministic_event is the shared choke point for gmail,
        # icloud_mail, gcal, icloud_cal, icloud_notes, icloud_todo -- confirm
        # a non-mail source gets datum_zeit too.
        app = application_factory(db_session)
        _seed_floor(db_session, app)
        db_session.commit()

        hint = datetime(2026, 7, 18, 9, 0, 0, tzinfo=timezone.utc)
        _save_deterministic_event(
            db_session, "gcal", "evt-2", _det(app.id, titel="Vorstellungsgespräch", typ="gespräch"),
            "Titel: Vorstellungsgespräch", date_hint=hint, user_id=None,
        )

        event = db_session.query(models.Event).filter_by(application_id=app.id, external_id="evt-2").first()
        assert event.datum_zeit == datetime(2026, 7, 18, 9, 0, 0)

    def test_negativ_kein_date_hint_kein_datum_zeit(self, db_session):
        app = application_factory(db_session)
        _seed_floor(db_session, app, days_ago=0)
        db_session.commit()

        _save_deterministic_event(
            db_session, "icloud_notes", "note-1", _det(app.id, typ="notiz"), "irrelevant", date_hint=None, user_id=None,
        )

        event = db_session.query(models.Event).filter_by(application_id=app.id, source="icloud_notes").first()
        # No date at all -> _predates_bewerbung() skips it entirely (existing
        # behavior, unrelated to this fix); nothing gets created.
        assert event is None

    def test_positiv_gleicher_tag_sortiert_ueber_datum_zeit_korrekt(self, db_session):
        # Reproduces the reported bug: two events on the same calendar day
        # (same Event.datum) must still come out in real chronological order
        # once datum_zeit is used as the sort key, not insertion order.
        app = application_factory(db_session)
        _seed_floor(db_session, app)
        db_session.commit()

        morning = datetime(2026, 7, 18, 8, 0, 0, tzinfo=timezone.utc)
        evening = datetime(2026, 7, 18, 18, 0, 0, tzinfo=timezone.utc)
        # Deliberately save the evening one first -- if same-day ordering
        # relied on insertion order, this would come out "newest" wrongly.
        _save_deterministic_event(
            db_session, "gmail", "msg-evening", _det(app.id, titel="Abendmail"), "From: a@x.example", date_hint=evening, user_id=None,
        )
        _save_deterministic_event(
            db_session, "gmail", "msg-morning", _det(app.id, titel="Morgenmail"), "From: b@x.example", date_hint=morning, user_id=None,
        )

        events = db_session.query(models.Event).filter_by(application_id=app.id, source="gmail").all()
        assert len(events) == 2
        newest_first = sorted(events, key=lambda e: e.datum_zeit, reverse=True)
        assert newest_first[0].titel == "Abendmail"
        assert newest_first[1].titel == "Morgenmail"
