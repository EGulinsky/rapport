"""L2 API -- POST /api/sync/linkedin/messages/import and GET .../status.

Replaces the removed live inbox scraper (_scrape_messages(), removed v4.5.5):
the user uploads their official LinkedIn data-export messages.csv instead.
Builds real CSV bytes (no hand-mocks) matching LinkedIn's actual export
columns, uploaded via the client fixture -- same style as
tests/api/test_import_excel_api.py.
"""
import csv
import io
from datetime import date, datetime, timedelta

import pytest

from app import models
from tests.factories import application_factory, contact_factory, seed_floor

pytestmark = pytest.mark.api

_COLUMNS = [
    "CONVERSATION ID", "CONVERSATION TITLE", "FROM", "SENDER PROFILE URL",
    "TO", "RECIPIENT PROFILE URLS", "DATE", "SUBJECT", "CONTENT", "FOLDER", "ATTACHMENTS",
]

SELF_NAME = "Max Mustermann"


def _build_csv(rows: list[dict], columns: list[str] | None = None) -> bytes:
    columns = columns or _COLUMNS
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns)
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return buf.getvalue().encode("utf-8")


def _message_row(conv_id, frm, to, date, content, folder="INBOX", other_url="https://www.linkedin.com/in/other-person"):
    # SELF_NAME must appear most often across FROM/TO for self-name auto-detection.
    return {
        "CONVERSATION ID": conv_id,
        "CONVERSATION TITLE": "",
        "FROM": frm,
        "SENDER PROFILE URL": "https://www.linkedin.com/in/max-mustermann" if frm == SELF_NAME else other_url,
        "TO": to,
        "RECIPIENT PROFILE URLS": other_url if frm == SELF_NAME else "https://www.linkedin.com/in/max-mustermann",
        "DATE": date,
        "SUBJECT": "",
        "CONTENT": content,
        "FOLDER": folder,
        "ATTACHMENTS": "",
    }


def _filler_rows() -> list[dict]:
    """Two disjoint conversations that only ever mention SELF_NAME, to
    unambiguously establish it as the most-frequent name across the whole
    file for self-name auto-detection. Needed because a real export has
    thousands of rows (SELF_NAME dominates trivially); these minimal test
    fixtures would otherwise tie SELF_NAME's count against the one other
    participant being tested, making self-name detection a coin flip."""
    return [
        _message_row("filler-1", SELF_NAME, "Filler Contact One", "2020-01-01 00:00:00 UTC", "filler",
                      other_url="https://www.linkedin.com/in/filler-one"),
        _message_row("filler-2", "Filler Contact Two", SELF_NAME, "2020-01-01 00:00:00 UTC", "filler",
                      other_url="https://www.linkedin.com/in/filler-two"),
    ]


def _upload(client, content: bytes, filename="messages.csv"):
    return client.post(
        "/api/sync/linkedin/messages/import",
        files={"file": (filename, content, "text/csv")},
    )


class TestImportMessagesValidation:
    def test_negativ_falsche_dateiendung_wird_abgelehnt(self, client):
        resp = _upload(client, b"anything", filename="messages.txt")
        assert resp.status_code == 400

    def test_negativ_falsche_spalten_werden_abgelehnt(self, client):
        # e.g. Connections.csv uploaded by mistake
        content = _build_csv(
            [{"First Name": "Anna", "Last Name": "Schmidt"}],
            columns=["First Name", "Last Name"],
        )
        resp = _upload(client, content)
        assert resp.status_code == 422


class TestImportMessagesMatching:
    def test_positiv_bestehender_kontakt_bekommt_ein_event(self, client, db_session):
        app = application_factory(db_session, firma="Contoso")
        contact = contact_factory(db_session, name="Anna Recruiterin", vorname=None)
        app.contacts.append(contact)
        seed_floor(db_session, app, days_ago=30)
        db_session.commit()

        content = _build_csv([
            *_filler_rows(),
            _message_row("conv-1", SELF_NAME, "Anna Recruiterin", "2026-07-16 17:36:22 UTC", "Hi, following up"),
            _message_row("conv-1", "Anna Recruiterin", SELF_NAME, "2026-07-17 09:00:00 UTC", "Thanks for reaching out"),
        ])

        resp = _upload(client, content)

        assert resp.status_code == 200
        body = resp.json()
        assert body["conversations_imported"] == 3  # conv-1 + 2 filler
        assert body["events_created"] == 1

        event = db_session.query(models.Event).filter_by(application_id=app.id, source="linkedin_msg").first()
        assert event is not None
        assert event.external_id == "conv-1"
        assert event.typ == "mail"
        assert "Anna Recruiterin" in event.titel
        assert event.notiz == "Thanks for reaching out\n(2 Nachrichten)"
        # Event.datum stays date-only; datum_zeit carries the full timestamp
        # of the conversation's latest message, for same-day sort ordering.
        assert event.datum == date(2026, 7, 17)
        assert event.datum_zeit == datetime(2026, 7, 17, 9, 0, 0)

        conv = db_session.query(models.LinkedInMessage).filter_by(conversation_id="conv-1").first()
        assert conv is not None
        assert conv.message_count == 2

    def test_positiv_ohne_passenden_kontakt_wird_gespeichert_aber_kein_event(self, client, db_session):
        content = _build_csv([
            *_filler_rows(),
            _message_row("conv-2", "Unknown Recruiter", SELF_NAME, "2026-07-16 12:00:00 UTC", "Hello there"),
        ])

        resp = _upload(client, content)

        assert resp.status_code == 200
        assert resp.json()["events_created"] == 0
        assert db_session.query(models.LinkedInMessage).filter_by(conversation_id="conv-2").first() is not None
        assert db_session.query(models.Event).filter_by(source="linkedin_msg").count() == 0

    def test_positiv_umlaut_in_unterschiedlicher_unicode_form_matcht_trotzdem(self, client, db_session):
        import unicodedata
        app = application_factory(db_session, firma="Contoso")
        # Contact stored with the NFD (decomposed) form of the umlaut.
        nfd_name = unicodedata.normalize("NFD", "Jörgen Müller")
        contact = contact_factory(db_session, name=nfd_name, vorname=None)
        app.contacts.append(contact)
        seed_floor(db_session, app, days_ago=30)
        db_session.commit()

        # CSV row uses the NFC (precomposed) form -- must still match.
        nfc_name = unicodedata.normalize("NFC", "Jörgen Müller")
        content = _build_csv([
            *_filler_rows(),
            _message_row("conv-3", nfc_name, SELF_NAME, "2026-07-16 12:00:00 UTC", "Guten Tag"),
        ])

        resp = _upload(client, content)

        assert resp.status_code == 200
        assert resp.json()["events_created"] == 1

    def test_positiv_reupload_aktualisiert_ohne_events_zu_duplizieren(self, client, db_session):
        app = application_factory(db_session, firma="Contoso")
        contact = contact_factory(db_session, name="Anna Recruiterin", vorname=None)
        app.contacts.append(contact)
        seed_floor(db_session, app, days_ago=30)
        db_session.commit()

        content1 = _build_csv([
            *_filler_rows(),
            _message_row("conv-4", SELF_NAME, "Anna Recruiterin", "2026-07-16 12:00:00 UTC", "First message"),
        ])
        resp1 = _upload(client, content1)
        assert resp1.status_code == 200
        assert resp1.json()["conversations_imported"] == 3  # conv-4 + 2 filler
        assert resp1.json()["events_created"] == 1

        # Re-upload: same conversation continued with a newer message.
        content2 = _build_csv([
            *_filler_rows(),
            _message_row("conv-4", SELF_NAME, "Anna Recruiterin", "2026-07-16 12:00:00 UTC", "First message"),
            _message_row("conv-4", "Anna Recruiterin", SELF_NAME, "2026-07-18 08:00:00 UTC", "A reply, much later"),
        ])
        resp2 = _upload(client, content2)

        assert resp2.status_code == 200
        assert resp2.json()["conversations_updated"] == 3  # conv-4 + 2 filler, all already exist
        assert resp2.json()["conversations_imported"] == 0
        assert resp2.json()["events_created"] == 0  # event already exists, no duplicate
        assert db_session.query(models.Event).filter_by(source="linkedin_msg", external_id="conv-4").count() == 1

        conv = db_session.query(models.LinkedInMessage).filter_by(conversation_id="conv-4").first()
        assert conv.message_count == 2


class TestRetroactiveAttach:
    def test_positiv_neuer_kontakt_bekommt_bestehende_nachrichten_zugewiesen(self, client, db_session):
        app = application_factory(db_session, firma="Contoso")
        seed_floor(db_session, app, days_ago=30)
        db_session.commit()

        # Import first -- no matching contact yet.
        content = _build_csv([
            *_filler_rows(),
            _message_row("conv-5", "Ben Recruiter", SELF_NAME, "2026-07-16 12:00:00 UTC", "Interested?"),
        ])
        resp = _upload(client, content)
        assert resp.status_code == 200
        assert resp.json()["events_created"] == 0

        # Now create+link a matching contact via the application's Contacts tab.
        resp2 = client.post(f"/api/applications/{app.id}/contacts", json={"name": "Ben Recruiter"})
        assert resp2.status_code == 201

        event = db_session.query(models.Event).filter_by(application_id=app.id, source="linkedin_msg").first()
        assert event is not None
        assert event.external_id == "conv-5"


class TestMessagesStatus:
    def test_positiv_status_spiegelt_import_wider(self, client, db_session):
        resp0 = client.get("/api/sync/linkedin/messages/status")
        assert resp0.status_code == 200
        assert resp0.json()["conversation_count"] == 0
        assert resp0.json()["last_imported_at"] is None

        content = _build_csv([
            *_filler_rows(),
            _message_row("conv-6", "Someone", SELF_NAME, "2026-07-16 12:00:00 UTC", "Hi"),
        ])
        _upload(client, content)

        resp1 = client.get("/api/sync/linkedin/messages/status")
        assert resp1.status_code == 200
        assert resp1.json()["conversation_count"] == 3  # conv-6 + 2 filler
        assert resp1.json()["last_imported_at"] is not None


def _fmt(d: date) -> str:
    return f"{d.isoformat()} 12:00:00 UTC"


class TestDateFloor:
    """Message events must respect the same effective_bewerbung_floor() rule
    as mail/calendar/call sync (sync_common.py): no anchor event yet -> no
    timed sync at all; a message dated before the earliest existing dated
    event on the application must not be attached either."""

    def test_negativ_ohne_jeden_bestehenden_termin_kein_event(self, client, db_session):
        # Brand-new application, zero dated events yet -- no floor to anchor to.
        app = application_factory(db_session, firma="Contoso")
        contact = contact_factory(db_session, name="Anna Recruiterin", vorname=None)
        app.contacts.append(contact)
        db_session.commit()

        content = _build_csv([
            *_filler_rows(),
            _message_row("conv-floor-1", SELF_NAME, "Anna Recruiterin", _fmt(date.today()), "Hallo"),
        ])
        resp = _upload(client, content)

        assert resp.status_code == 200
        assert resp.json()["events_created"] == 0
        assert db_session.query(models.Event).filter_by(source="linkedin_msg").count() == 0

    def test_negativ_nachricht_vor_dem_floor_wird_nicht_angehaengt(self, client, db_session):
        app = application_factory(db_session, firma="Contoso")
        contact = contact_factory(db_session, name="Anna Recruiterin", vorname=None)
        app.contacts.append(contact)
        seed_floor(db_session, app, days_ago=30)  # floor = today - 30 days
        db_session.commit()

        too_old = date.today() - timedelta(days=60)
        content = _build_csv([
            *_filler_rows(),
            _message_row("conv-floor-2", SELF_NAME, "Anna Recruiterin", _fmt(too_old), "Vor der Bewerbung"),
        ])
        resp = _upload(client, content)

        assert resp.status_code == 200
        assert resp.json()["events_created"] == 0
        assert db_session.query(models.Event).filter_by(source="linkedin_msg", external_id="conv-floor-2").count() == 0

    def test_positiv_nachricht_nach_dem_floor_wird_angehaengt(self, client, db_session):
        app = application_factory(db_session, firma="Contoso")
        contact = contact_factory(db_session, name="Anna Recruiterin", vorname=None)
        app.contacts.append(contact)
        seed_floor(db_session, app, days_ago=30)  # floor = today - 30 days
        db_session.commit()

        recent = date.today() - timedelta(days=5)
        content = _build_csv([
            *_filler_rows(),
            _message_row("conv-floor-3", SELF_NAME, "Anna Recruiterin", _fmt(recent), "Nach der Bewerbung"),
        ])
        resp = _upload(client, content)

        assert resp.status_code == 200
        assert resp.json()["events_created"] == 1
        event = db_session.query(models.Event).filter_by(source="linkedin_msg", external_id="conv-floor-3").first()
        assert event is not None
        assert event.datum == recent


class TestUmlautTransliterationMatching:
    """Real-world case reported after shipping: a contact stored with a German
    umlaut wasn't matched against LinkedIn's own export, which spelled the
    same person using the ASCII digraph substitute for that umlaut instead.
    Covers both matching directions plus a mix of all four German
    umlaut/eszett substitutions."""

    def test_positiv_kontakt_mit_umlaut_matcht_csv_mit_ue(self, client, db_session):
        app = application_factory(db_session, firma="Contoso")
        contact = contact_factory(db_session, name="Hans-Peter Grünwald", vorname=None)
        app.contacts.append(contact)
        seed_floor(db_session, app, days_ago=30)
        db_session.commit()

        content = _build_csv([
            *_filler_rows(),
            _message_row("conv-umlaut-1", "Hans-Peter Gruenwald", SELF_NAME,
                          _fmt(date.today() - timedelta(days=1)), "Sehr geehrter Herr Gruenwald"),
        ])
        resp = _upload(client, content)

        assert resp.status_code == 200
        assert resp.json()["events_created"] == 1
        event = db_session.query(models.Event).filter_by(application_id=app.id, source="linkedin_msg").first()
        assert event is not None
        assert event.external_id == "conv-umlaut-1"

    def test_positiv_kontakt_mit_ue_matcht_csv_mit_umlaut(self, client, db_session):
        # Reverse direction: contact stored with the ASCII digraph, CSV has the umlaut.
        app = application_factory(db_session, firma="Contoso")
        contact = contact_factory(db_session, name="Hans-Peter Gruenwald", vorname=None)
        app.contacts.append(contact)
        seed_floor(db_session, app, days_ago=30)
        db_session.commit()

        content = _build_csv([
            *_filler_rows(),
            _message_row("conv-umlaut-2", "Hans-Peter Grünwald", SELF_NAME,
                          _fmt(date.today() - timedelta(days=1)), "Guten Tag"),
        ])
        resp = _upload(client, content)

        assert resp.status_code == 200
        assert resp.json()["events_created"] == 1

    def test_positiv_alle_vier_umlaut_varianten_in_einem_namen(self, client, db_session):
        app = application_factory(db_session, firma="Contoso")
        contact = contact_factory(db_session, name="Bärbel Preißler-Öztürk", vorname=None)
        app.contacts.append(contact)
        seed_floor(db_session, app, days_ago=30)
        db_session.commit()

        content = _build_csv([
            *_filler_rows(),
            _message_row("conv-umlaut-3", "Baerbel Preissler-Oeztuerk", SELF_NAME,
                          _fmt(date.today() - timedelta(days=1)), "Hallo"),
        ])
        resp = _upload(client, content)

        assert resp.status_code == 200
        assert resp.json()["events_created"] == 1

    def test_negativ_unterschiedliche_nachnamen_werden_nicht_verwechselt(self, client, db_session):
        # Sanity check: transliteration must not cause false-positive matches
        # between genuinely different people.
        app = application_factory(db_session, firma="Contoso")
        contact = contact_factory(db_session, name="Hans-Peter Grünwald", vorname=None)
        app.contacts.append(contact)
        seed_floor(db_session, app, days_ago=30)
        db_session.commit()

        content = _build_csv([
            *_filler_rows(),
            _message_row("conv-umlaut-4", "Hans-Peter Baumann", SELF_NAME,
                          _fmt(date.today() - timedelta(days=1)), "Hallo"),
        ])
        resp = _upload(client, content)

        assert resp.status_code == 200
        assert resp.json()["events_created"] == 0
