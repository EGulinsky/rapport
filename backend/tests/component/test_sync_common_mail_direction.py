"""L1 Component -- _save_deterministic_event()/save_classified_event() in
sync_common.py: Event.mail_direction ("sent"/"received") and Event.autor
holding the *other party* (recipient for sent mail, sender for received
mail) rather than always the sender -- previously sent mail the account
owner wrote themselves showed their own name in the timeline instead of who
they actually wrote to. Also covers the deterministic path now storing the
full mail body in notiz (previously only icloud_notes did)."""
from datetime import date, datetime, timedelta, timezone

import pytest

from app import models
from app.routers.sync_common import _classify_deterministic, _save_deterministic_event, save_classified_event
from tests.factories import application_factory, event_factory

pytestmark = pytest.mark.component

_RECENT = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc) - timedelta(days=1)


def _seed_floor(db_session, app, days_ago=60):
    event_factory(db_session, app, datum=date.today() - timedelta(days=days_ago), source="gcal")


def _det(app_id, titel="Rückmeldung", typ="notiz", notiz=None):
    return {"app_id": app_id, "typ": typ, "titel": titel, "notiz": notiz, "reason": "test"}


def _seed_owner_gmail(db_session, email="me@gmail.com"):
    db_session.add(models.GoogleSync(
        client_id="x", client_secret_enc="x", gmail_email=email,
    ))
    db_session.commit()


class TestSaveDeterministicEventMailDirection:
    def test_positiv_empfangene_mail_hat_direction_received_und_autor_ist_absender(self, db_session):
        app = application_factory(db_session)
        _seed_floor(db_session, app)
        db_session.commit()

        raw_text = "Von: Anna Recruiterin <anna@contoso.example>\nAn: me@gmail.com\nBetreff: Ihre Bewerbung\n\nHallo,\n..."
        _save_deterministic_event(
            db_session, "gmail", "msg-1", _det(app.id), raw_text, date_hint=_RECENT, user_id=None,
        )

        event = db_session.query(models.Event).filter_by(application_id=app.id, source="gmail").first()
        assert event.mail_direction == "received"
        assert event.autor == "Anna Recruiterin <anna@contoso.example>"

    def test_positiv_gesendete_mail_hat_direction_sent_und_autor_ist_empfaenger(self, db_session):
        app = application_factory(db_session)
        _seed_floor(db_session, app)
        _seed_owner_gmail(db_session)

        raw_text = "Von: me@gmail.com\nAn: Anna Recruiterin <anna@contoso.example>\nBetreff: Rückfrage\n\nHallo,\n..."
        _save_deterministic_event(
            db_session, "gmail", "msg-2", _det(app.id), raw_text, date_hint=_RECENT, user_id=None,
        )

        event = db_session.query(models.Event).filter_by(application_id=app.id, source="gmail").first()
        assert event.mail_direction == "sent"
        assert event.autor == "Anna Recruiterin <anna@contoso.example>"

    def test_positiv_kontakt_wird_bei_gesendeter_mail_aus_empfaenger_angelegt(self, db_session):
        app = application_factory(db_session, firma="Contoso AG")
        _seed_floor(db_session, app)
        _seed_owner_gmail(db_session)

        raw_text = "Von: me@gmail.com\nAn: Dana Recruiter <dana@contoso-ag.example>\nBetreff: Rückfrage\n\nHallo,\n..."
        _save_deterministic_event(
            db_session, "gmail", "msg-3", _det(app.id), raw_text, date_hint=_RECENT, user_id=None,
        )

        contact = db_session.query(models.Contact).filter_by(email="dana@contoso-ag.example").first()
        assert contact is not None
        assert contact.vorname == "Dana"

    def test_positiv_mehrere_empfaenger_zeigt_liste_aber_kontakt_nur_aus_erstem(self, db_session):
        app = application_factory(db_session, firma="Contoso AG")
        _seed_floor(db_session, app)
        _seed_owner_gmail(db_session)

        raw_text = (
            "Von: me@gmail.com\n"
            "An: Erika Erste <erika@contoso-ag.example>, Zweiter Empfaenger <zweiter@contoso-ag.example>\n"
            "Betreff: Rückfrage\n\nHallo,\n..."
        )
        _save_deterministic_event(
            db_session, "gmail", "msg-4", _det(app.id), raw_text, date_hint=_RECENT, user_id=None,
        )

        event = db_session.query(models.Event).filter_by(application_id=app.id, source="gmail").first()
        assert "Erika Erste" in event.autor and "Zweiter Empfaenger" in event.autor
        contacts = db_session.query(models.Contact).filter(
            models.Contact.email.in_(["erika@contoso-ag.example", "zweiter@contoso-ag.example"])
        ).all()
        assert {c.email for c in contacts} == {"erika@contoso-ag.example"}

    def test_negativ_kalenderereignisse_haben_kein_mail_direction(self, db_session):
        app = application_factory(db_session)
        _seed_floor(db_session, app)
        db_session.commit()

        raw_text = "Titel: Interview\nTeilnehmer: Anna Recruiterin <anna@contoso.example>\nBeschreibung: "
        _save_deterministic_event(
            db_session, "gcal", "evt-1", _det(app.id, typ="gespräch"), raw_text, date_hint=_RECENT, user_id=None,
        )

        event = db_session.query(models.Event).filter_by(external_id="evt-1").one()
        assert event.mail_direction is None

    def test_positiv_voller_mailtext_wird_in_notiz_gespeichert(self, db_session):
        # Previously _classify_deterministic() left notiz=None for gmail/
        # icloud_mail (only icloud_notes populated a body preview) -- the
        # timeline can't show "the full content, collapsed by default" if
        # there's nothing stored to show. Exercised through the actual
        # classifier (not a hand-built det dict), since that's where the
        # notiz value _save_deterministic_event() persists comes from.
        app = application_factory(db_session)
        _seed_floor(db_session, app)
        db_session.commit()

        raw_text = (
            "Von: Anna Recruiterin <anna@contoso.example>\nAn: me@gmail.com\n"
            "Betreff: Ihre Bewerbung\n\nHallo Herr Gulinsky,\n\ndies ist der vollständige Mailinhalt."
        )
        det = _classify_deterministic("gmail", raw_text, _RECENT, [{"id": app.id}])
        assert det is not None
        _save_deterministic_event(
            db_session, "gmail", "msg-5", det, raw_text, date_hint=_RECENT, user_id=None,
        )

        event = db_session.query(models.Event).filter_by(application_id=app.id, source="gmail").first()
        assert event.notiz is not None
        assert "vollständige Mailinhalt" in event.notiz


class TestSaveClassifiedEventMailDirection:
    def _target_app(self, app):
        return {"id": app.id, "firma": app.firma, "is_headhunter": False}

    def test_positiv_gesendete_mail_hat_direction_sent_und_autor_ist_empfaenger(self, db_session):
        app = application_factory(db_session, firma="Contoso AG")
        _seed_floor(db_session, app)
        _seed_owner_gmail(db_session)

        result = {"relevant": True, "confidence": 0.9, "event_type": "note", "titel": "Rückfrage"}
        raw_text = "Von: me@gmail.com\nAn: Anna Recruiterin <anna@contoso.example>\nBetreff: Rückfrage\n\nInhalt"
        save_classified_event(
            db_session, "gmail", "msg-ai-1", result, raw_text, _RECENT, self._target_app(app), user_id=None,
        )

        event = db_session.query(models.Event).filter_by(application_id=app.id, source="gmail").first()
        assert event.mail_direction == "sent"
        assert event.autor == "Anna Recruiterin <anna@contoso.example>"

    def test_positiv_empfangene_mail_hat_direction_received(self, db_session):
        app = application_factory(db_session, firma="Contoso AG")
        _seed_floor(db_session, app)
        db_session.commit()

        result = {"relevant": True, "confidence": 0.9, "event_type": "note", "titel": "Interview"}
        raw_text = "Von: Jane Doe <jane@contoso.com>\nAn: me@gmail.com\nBetreff: Hallo\n\nInhalt"
        save_classified_event(
            db_session, "gmail", "msg-ai-2", result, raw_text, _RECENT, self._target_app(app), user_id=None,
        )

        event = db_session.query(models.Event).filter_by(application_id=app.id, source="gmail").first()
        assert event.mail_direction == "received"
        assert event.autor == "Jane Doe <jane@contoso.com>"
