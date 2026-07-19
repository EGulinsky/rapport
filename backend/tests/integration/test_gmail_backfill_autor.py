"""L3 Integration — backfill_gmail_autor() in sync_google.py.

Mocks at the network boundary (googleapiclient.discovery.build, via the
same fake_gmail/gmail_message fixtures test_gmail_sync.py uses), not the
sync logic itself. Only the metadata-only batch fetch is exercised here
(no .list() call, no full-body fetch) since the backfill already knows
which message IDs to re-fetch from Event.external_id.
"""
from datetime import date

import pytest

from app import models
from app.routers.sync_google import backfill_gmail_autor
from tests.factories import application_factory, contact_factory

pytestmark = pytest.mark.integration


def _gmail_event(db, app, external_id, autor=None, source="gmail"):
    event = models.Event(
        application_id=app.id, typ="mail", datum=date(2026, 6, 1),
        titel="Betreff", source=source, external_id=external_id, autor=autor,
        user_id=app.user_id,
    )
    db.add(event)
    db.flush()
    return event


class TestBackfillGmailAutorNichtVerbunden:
    def test_negativ_keine_google_konfiguration_liefert_klaren_fehler(self, db_session):
        result = backfill_gmail_autor(db_session, user_id=1)

        assert result == {"updated": 0, "errors": ["Nicht mit Google verbunden."]}


class TestBackfillGmailAutorKeineBetroffenenEvents:
    def test_negativ_kein_api_aufruf_wenn_nichts_zu_tun_ist(self, db_session, google_sync):
        # Bewusst kein fake_gmail-Fixture -- würde ein echter API-Call
        # versucht, schlägt der Test mit einem Verbindungsfehler fehl statt
        # nur mit einer falschen Assertion, macht die Absicht hier explizit.
        result = backfill_gmail_autor(db_session, user_id=1)

        assert result == {"updated": 0, "errors": []}


class TestBackfillGmailAutorPositiv:
    def test_positiv_autor_wird_aus_from_header_nachtraeglich_gesetzt(
        self, db_session, google_sync, fake_gmail
    ):
        app = application_factory(db_session, firma="Qorix")
        db_session.commit()
        event = _gmail_event(db_session, app, "msg-old-1")

        meta = {"id": "msg-old-1", "payload": {"headers": [
            {"name": "From", "value": "Philipp Knöpfle <philipp.knoepfle@qorix.ai>"},
        ]}}
        fake_gmail([], metadata={"msg-old-1": meta})

        result = backfill_gmail_autor(db_session, user_id=1)

        assert result["errors"] == []
        assert result["updated"] == 1
        db_session.refresh(event)
        assert event.autor == "Philipp Knöpfle <philipp.knoepfle@qorix.ai>"

    def test_positiv_erstellt_kontakt_aus_backfilltem_absender(
        self, db_session, google_sync, fake_gmail
    ):
        app = application_factory(db_session, firma="Qorix")
        db_session.commit()
        _gmail_event(db_session, app, "msg-old-2")

        meta = {"id": "msg-old-2", "payload": {"headers": [
            {"name": "From", "value": "Neue Person <neu@qorix.ai>"},
        ]}}
        fake_gmail([], metadata={"msg-old-2": meta})

        backfill_gmail_autor(db_session, user_id=1)

        contact = db_session.query(models.Contact).filter_by(email="neu@qorix.ai").one()
        assert app in contact.applications

    def test_positiv_verlinkt_bestehenden_kontakt_ueber_email(
        self, db_session, google_sync, fake_gmail
    ):
        app = application_factory(db_session, firma="Qorix")
        contact = contact_factory(db_session, name="Knöpfle", email="philipp.knoepfle@qorix.ai", firma="Qorix")
        db_session.commit()
        _gmail_event(db_session, app, "msg-old-3")

        meta = {"id": "msg-old-3", "payload": {"headers": [
            {"name": "From", "value": "Philipp Knöpfle <philipp.knoepfle@qorix.ai>"},
        ]}}
        fake_gmail([], metadata={"msg-old-3": meta})

        backfill_gmail_autor(db_session, user_id=1)

        db_session.refresh(contact)
        assert app in contact.applications

    def test_negativ_bereits_gesetztes_autor_bleibt_unveraendert(
        self, db_session, google_sync, fake_gmail
    ):
        app = application_factory(db_session)
        db_session.commit()
        event = _gmail_event(db_session, app, "msg-already-set", autor="Old <old@example.com>")

        # Kein Metadata-Eintrag für diese msg_id -- wird ohnehin nicht angefragt,
        # da schon autor gesetzt ist und die Query sie ausschließt.
        fake_gmail([], metadata={})

        result = backfill_gmail_autor(db_session, user_id=1)

        assert result == {"updated": 0, "errors": []}
        db_session.refresh(event)
        assert event.autor == "Old <old@example.com>"

    def test_negativ_icloud_mail_events_werden_nicht_angefasst(
        self, db_session, google_sync, fake_gmail
    ):
        app = application_factory(db_session)
        db_session.commit()
        event = _gmail_event(db_session, app, "msg-icloud", source="icloud_mail")

        fake_gmail([], metadata={})

        result = backfill_gmail_autor(db_session, user_id=1)

        assert result == {"updated": 0, "errors": []}
        db_session.refresh(event)
        assert event.autor is None

    def test_corner_case_zweiter_lauf_findet_nichts_mehr(
        self, db_session, google_sync, fake_gmail
    ):
        app = application_factory(db_session, firma="Qorix")
        db_session.commit()
        _gmail_event(db_session, app, "msg-old-4")

        meta = {"id": "msg-old-4", "payload": {"headers": [
            {"name": "From", "value": "Person <person@qorix.ai>"},
        ]}}
        service = fake_gmail([], metadata={"msg-old-4": meta})
        backfill_gmail_autor(db_session, user_id=1)

        service2 = fake_gmail([], metadata={})
        result = backfill_gmail_autor(db_session, user_id=1)

        assert result == {"updated": 0, "errors": []}
        assert service is not service2  # sanity: second call really used a fresh fixture instance

    def test_negativ_message_ohne_from_header_wird_uebersprungen(
        self, db_session, google_sync, fake_gmail
    ):
        app = application_factory(db_session)
        db_session.commit()
        event = _gmail_event(db_session, app, "msg-no-from")

        meta = {"id": "msg-no-from", "payload": {"headers": []}}
        fake_gmail([], metadata={"msg-no-from": meta})

        result = backfill_gmail_autor(db_session, user_id=1)

        assert result == {"updated": 0, "errors": []}
        db_session.refresh(event)
        assert event.autor is None
