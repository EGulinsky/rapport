"""L0/L1 -- live LinkedIn inbox scraper (_scrape_linkedin_messages(),
_upsert_linkedin_messages()) plus the resulting attach_linkedin_messages_for_contact()
matching/date-floor/umlaut behavior, and L2 GET /api/sync/linkedin/messages/status.

Replaces the CSV-import test file removed alongside POST
/api/sync/linkedin/messages/import (v4.7.14): messages are now scraped live
from the account's own LinkedIn inbox as part of the LinkedIn job sync
(_async_sync() in sync_linkedin.py), matched against known contacts/companies
by name (same two-pass strategy as the original pre-v4.5.5 live scraper).
attach_linkedin_messages_for_contact()'s matching/date-floor/umlaut logic is
unchanged from the CSV-import era -- only where LinkedInMessage rows come
from changed -- so those cases are covered here directly against the DB
rather than via file upload.
"""
import unicodedata
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app import models
from app.routers.sync_linkedin import (
    _scrape_linkedin_messages,
    _upsert_linkedin_messages,
    attach_linkedin_messages_for_contact,
)
from tests.factories import application_factory, contact_factory, seed_floor

pytestmark = pytest.mark.api


def _fake_messages_page(item_specs: list[tuple[str, str, str]], landed_url: str = "https://www.linkedin.com/messaging/"):
    """item_specs: list of (ember_id, sidebar_raw_text, thread_id_after_click)."""
    page = MagicMock()
    page.url = landed_url
    page.goto = AsyncMock()
    page.evaluate = AsyncMock()
    page.wait_for_url = AsyncMock()
    page.inner_text = AsyncMock(
        return_value="A detail-page line long enough to be picked up as the preview text for the conversation."
    )

    items = []
    for ember_id, raw_text, thread_id in item_specs:
        li = MagicMock()
        li.get_attribute = AsyncMock(return_value=ember_id)
        li.inner_text = AsyncMock(return_value=raw_text)

        async def _click(timeout=None, _page=page, _thread_id=thread_id):
            _page.url = f"https://www.linkedin.com/messaging/thread/{_thread_id}/"

        link = MagicMock()
        link.click = AsyncMock(side_effect=_click)
        link_locator = MagicMock()
        link_locator.first = link
        li.locator = MagicMock(return_value=link_locator)
        items.append(li)

    list_locator = MagicMock()
    list_locator.all = AsyncMock(return_value=items)
    page.locator = MagicMock(return_value=list_locator)
    return page


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    monkeypatch.setattr("app.routers.sync_linkedin.asyncio.sleep", AsyncMock())


class TestScrapeLinkedinMessages:
    async def test_negativ_ohne_bekannten_kontakt_oder_firma_kein_seitenaufruf(self, db_session):
        page = _fake_messages_page([])

        convs, errors = await _scrape_linkedin_messages(page, db_session, user_id=1)

        assert convs == []
        assert errors == []
        page.goto.assert_not_called()

    async def test_negativ_login_wall_gibt_leere_liste(self, db_session):
        app = application_factory(db_session, firma="Contoso")
        contact = contact_factory(db_session, name="Anna Recruiterin", vorname=None)
        app.contacts.append(contact)
        db_session.commit()

        page = _fake_messages_page([], landed_url="https://www.linkedin.com/checkpoint/login/")

        convs, errors = await _scrape_linkedin_messages(page, db_session, user_id=1)

        assert convs == []
        assert errors == []

    async def test_positiv_kontakt_treffer_oeffnet_konversation(self, db_session):
        app = application_factory(db_session, firma="Contoso")
        contact = contact_factory(db_session, name="Anna Recruiterin", vorname=None)
        app.contacts.append(contact)
        db_session.commit()

        raw_text = "Anna Recruiterin\nThanks for reaching out"
        page = _fake_messages_page([("ember123", raw_text, "abcThreadId")])

        convs, errors = await _scrape_linkedin_messages(page, db_session, user_id=1)

        assert errors == []
        assert len(convs) == 1
        conv = convs[0]
        assert conv["conversation_id"] == "abcThreadId"
        assert conv["participant_name"] == "Anna Recruiterin"
        assert conv["message_count"] == 1

    async def test_negativ_unbekannte_konversation_wird_nicht_geoeffnet(self, db_session):
        app = application_factory(db_session, firma="Contoso")
        contact = contact_factory(db_session, name="Anna Recruiterin", vorname=None)
        app.contacts.append(contact)
        db_session.commit()

        raw_text = "Someone Else Entirely\nNot related at all"
        page = _fake_messages_page([("ember456", raw_text, "shouldNotOpen")])

        convs, errors = await _scrape_linkedin_messages(page, db_session, user_id=1)

        assert convs == []
        assert errors == []

    async def test_positiv_firmen_treffer_ohne_kontakt_oeffnet_konversation(self, db_session):
        app = application_factory(db_session, firma="Contoso Solutions")
        seed_floor(db_session, app, days_ago=30)
        db_session.commit()

        raw_text = "Someone at Contoso Solutions\nAre you still interested?"
        page = _fake_messages_page([("ember789", raw_text, "companyThreadId")])

        convs, errors = await _scrape_linkedin_messages(page, db_session, user_id=1)

        assert errors == []
        assert len(convs) == 1
        assert convs[0]["conversation_id"] == "companyThreadId"
        # No contact name matched -- participant falls back to the sidebar's
        # own first line rather than a resolved contact display name.
        assert convs[0]["participant_name"] == "Someone at Contoso Solutions"


class TestUpsertLinkedinMessages:
    def test_positiv_neue_konversation_wird_angelegt(self, db_session):
        convs = [{
            "conversation_id": "conv-new", "participant_name": "Ben Recruiter",
            "participant_profile_url": None, "last_message_date": datetime(2026, 7, 1),
            "last_message_preview": "Hi there", "message_count": 2, "folder": None,
        }]

        imported, updated = _upsert_linkedin_messages(convs, db_session, user_id=1)
        db_session.flush()

        assert (imported, updated) == (1, 0)
        row = db_session.query(models.LinkedInMessage).filter_by(conversation_id="conv-new").first()
        assert row is not None
        assert row.participant_name == "Ben Recruiter"
        assert row.message_count == 2

    def test_positiv_bestehende_konversation_wird_aktualisiert(self, db_session):
        first = [{
            "conversation_id": "conv-upd", "participant_name": "Ben Recruiter",
            "participant_profile_url": None, "last_message_date": datetime(2026, 7, 1),
            "last_message_preview": "Hi there", "message_count": 1, "folder": None,
        }]
        _upsert_linkedin_messages(first, db_session, user_id=1)
        db_session.commit()

        second = [{
            "conversation_id": "conv-upd", "participant_name": "Ben Recruiter",
            "participant_profile_url": None, "last_message_date": datetime(2026, 7, 3),
            "last_message_preview": "Following up", "message_count": 2, "folder": None,
        }]
        imported, updated = _upsert_linkedin_messages(second, db_session, user_id=1)

        assert (imported, updated) == (0, 1)
        row = db_session.query(models.LinkedInMessage).filter_by(conversation_id="conv-upd").first()
        assert row.message_count == 2
        assert row.last_message_preview == "Following up"


def _make_message(db_session, conversation_id: str, participant_name: str, last_message_date: datetime) -> models.LinkedInMessage:
    from app.routers.sync_linkedin import _normalize_name
    msg = models.LinkedInMessage(
        user_id=1, conversation_id=conversation_id, participant_name=participant_name,
        participant_name_normalized=_normalize_name(participant_name),
        participant_profile_url="https://www.linkedin.com/in/other-person",
        last_message_date=last_message_date, last_message_preview="preview", message_count=1, folder=None,
    )
    db_session.add(msg)
    db_session.flush()
    return msg


class TestAttachMatching:
    def test_positiv_bestehender_kontakt_bekommt_ein_event(self, db_session):
        app = application_factory(db_session, firma="Contoso")
        contact = contact_factory(db_session, name="Anna Recruiterin", vorname=None)
        app.contacts.append(contact)
        seed_floor(db_session, app, days_ago=30)
        db_session.commit()

        _make_message(db_session, "conv-1", "Anna Recruiterin", datetime(2026, 7, 17, 9, 0, 0))
        db_session.commit()

        created = attach_linkedin_messages_for_contact(db_session, contact, user_id=1)

        assert created == 1
        event = db_session.query(models.Event).filter_by(application_id=app.id, source="linkedin_msg").first()
        assert event is not None
        assert event.external_id == "conv-1"
        assert event.typ == "mail"
        assert event.external_url == "https://www.linkedin.com/in/other-person"

    def test_positiv_reattach_erzeugt_kein_duplikat(self, db_session):
        app = application_factory(db_session, firma="Contoso")
        contact = contact_factory(db_session, name="Anna Recruiterin", vorname=None)
        app.contacts.append(contact)
        seed_floor(db_session, app, days_ago=30)
        db_session.commit()

        _make_message(db_session, "conv-2", "Anna Recruiterin", datetime(2026, 7, 17, 9, 0, 0))
        db_session.commit()

        attach_linkedin_messages_for_contact(db_session, contact, user_id=1)
        second_run_created = attach_linkedin_messages_for_contact(db_session, contact, user_id=1)

        assert second_run_created == 0
        assert db_session.query(models.Event).filter_by(source="linkedin_msg", external_id="conv-2").count() == 1

    def test_positiv_umlaut_in_unterschiedlicher_unicode_form_matcht_trotzdem(self, db_session):
        app = application_factory(db_session, firma="Contoso")
        nfd_name = unicodedata.normalize("NFD", "Jörgen Müller")
        contact = contact_factory(db_session, name=nfd_name, vorname=None)
        app.contacts.append(contact)
        seed_floor(db_session, app, days_ago=30)
        db_session.commit()

        nfc_name = unicodedata.normalize("NFC", "Jörgen Müller")
        _make_message(db_session, "conv-3", nfc_name, datetime(2026, 7, 16, 12, 0, 0))
        db_session.commit()

        created = attach_linkedin_messages_for_contact(db_session, contact, user_id=1)

        assert created == 1


class TestDateFloor:
    """Message events must respect the same effective_bewerbung_floor() rule
    as mail/calendar/call sync (sync_common.py): no anchor event yet -> no
    timed sync at all; a message dated before the earliest existing dated
    event on the application must not be attached either."""

    def test_negativ_ohne_jeden_bestehenden_termin_kein_event(self, db_session):
        app = application_factory(db_session, firma="Contoso")
        contact = contact_factory(db_session, name="Anna Recruiterin", vorname=None)
        app.contacts.append(contact)
        db_session.commit()

        _make_message(db_session, "conv-floor-1", "Anna Recruiterin", datetime.combine(date.today(), datetime.min.time()))
        db_session.commit()

        created = attach_linkedin_messages_for_contact(db_session, contact, user_id=1)

        assert created == 0
        assert db_session.query(models.Event).filter_by(source="linkedin_msg").count() == 0

    def test_negativ_nachricht_vor_dem_floor_wird_nicht_angehaengt(self, db_session):
        app = application_factory(db_session, firma="Contoso")
        contact = contact_factory(db_session, name="Anna Recruiterin", vorname=None)
        app.contacts.append(contact)
        seed_floor(db_session, app, days_ago=30)
        db_session.commit()

        too_old = datetime.combine(date.today() - timedelta(days=60), datetime.min.time())
        _make_message(db_session, "conv-floor-2", "Anna Recruiterin", too_old)
        db_session.commit()

        created = attach_linkedin_messages_for_contact(db_session, contact, user_id=1)

        assert created == 0

    def test_positiv_nachricht_nach_dem_floor_wird_angehaengt(self, db_session):
        app = application_factory(db_session, firma="Contoso")
        contact = contact_factory(db_session, name="Anna Recruiterin", vorname=None)
        app.contacts.append(contact)
        seed_floor(db_session, app, days_ago=30)
        db_session.commit()

        recent = datetime.combine(date.today() - timedelta(days=5), datetime.min.time())
        _make_message(db_session, "conv-floor-3", "Anna Recruiterin", recent)
        db_session.commit()

        created = attach_linkedin_messages_for_contact(db_session, contact, user_id=1)

        assert created == 1
        event = db_session.query(models.Event).filter_by(source="linkedin_msg", external_id="conv-floor-3").first()
        assert event.datum == recent.date()


class TestMessagesStatus:
    def test_positiv_status_spiegelt_gescrapte_daten_wider(self, client, db_session):
        resp0 = client.get("/api/sync/linkedin/messages/status")
        assert resp0.status_code == 200
        assert resp0.json()["conversation_count"] == 0
        assert resp0.json()["last_imported_at"] is None

        _make_message(db_session, "conv-status-1", "Someone", datetime(2026, 7, 16, 12, 0, 0))
        db_session.commit()

        resp1 = client.get("/api/sync/linkedin/messages/status")
        assert resp1.status_code == 200
        assert resp1.json()["conversation_count"] == 1
        assert resp1.json()["last_imported_at"] is not None
