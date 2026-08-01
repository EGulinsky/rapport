"""L1 Component — _sync_contacts_from_linkedin() in sync_linkedin.py.

Scrapes the user's LinkedIn connections and imports them through the same
_sync_contacts_from_parsed() pipeline iCloud/Google contacts already use
(unconditional import, mention-based application linking). Both
_get_linkedin_context (session/browser) and _scrape_linkedin_connections
(the actual scrape) are mocked at their own module boundary — this test is
only about the parsed-dict shape + orchestration, not about Playwright or
card-parsing, which are covered by test_sync_linkedin_connections.py.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import models
from app.routers.sync_linkedin import _sync_contacts_from_linkedin

pytestmark = pytest.mark.component


def _fake_linkedin_context():
    playwright = MagicMock()
    playwright.stop = AsyncMock()
    browser = MagicMock()
    browser.close = AsyncMock()
    context = MagicMock()
    return playwright, browser, context


class TestSyncContactsFromLinkedin:
    async def test_positiv_importiert_kandidaten_ohne_namenssplit(self, db_session):
        with (
            patch("app.routers.sync_company._get_linkedin_context", new=AsyncMock(return_value=_fake_linkedin_context())),
            patch(
                "app.routers.sync_linkedin._scrape_linkedin_connections",
                new=AsyncMock(return_value=[{
                    "name": "Max Mustermann",
                    "headline": "Senior Engineer at Contoso GmbH",
                    "profile_url": "https://www.linkedin.com/in/max-mustermann",
                }]),
            ),
        ):
            created, errors, touched_ids = await _sync_contacts_from_linkedin(db_session, None)

        assert errors == []
        assert created == 1
        assert len(touched_ids) == 1
        contact = db_session.query(models.Contact).get(touched_ids[0])
        assert contact.name == "Max Mustermann"
        assert contact.vorname is None
        assert contact.rolle == "Senior Engineer"
        assert contact.firma == "Contoso GmbH"
        assert contact.linkedin_url == "https://www.linkedin.com/in/max-mustermann"

    async def test_positiv_headline_ohne_firma_bleibt_firma_none(self, db_session):
        with (
            patch("app.routers.sync_company._get_linkedin_context", new=AsyncMock(return_value=_fake_linkedin_context())),
            patch(
                "app.routers.sync_linkedin._scrape_linkedin_connections",
                new=AsyncMock(return_value=[{
                    "name": "Anna Muster",
                    "headline": "Head of Customer Program Management",
                    "profile_url": "https://www.linkedin.com/in/anna-muster",
                }]),
            ),
        ):
            created, errors, touched_ids = await _sync_contacts_from_linkedin(db_session, None)

        assert created == 1
        contact = db_session.query(models.Contact).get(touched_ids[0])
        assert contact.rolle == "Head of Customer Program Management"
        assert contact.firma is None

    async def test_negativ_ohne_session_liefert_leeres_ergebnis_ohne_fehler(self, db_session):
        with patch("app.routers.sync_company._get_linkedin_context", new=AsyncMock(return_value=None)):
            created, errors, touched_ids = await _sync_contacts_from_linkedin(db_session, None)

        assert (created, errors, touched_ids) == (0, [], [])

    async def test_negativ_browser_start_exception_liefert_leeres_ergebnis(self, db_session):
        with patch("app.routers.sync_company._get_linkedin_context", new=AsyncMock(side_effect=RuntimeError("boom"))):
            created, errors, touched_ids = await _sync_contacts_from_linkedin(db_session, None)

        assert (created, errors, touched_ids) == (0, [], [])

    async def test_positiv_schliesst_browser_auch_bei_scrape_fehler(self, db_session):
        playwright, browser, context = _fake_linkedin_context()
        with (
            patch("app.routers.sync_company._get_linkedin_context", new=AsyncMock(return_value=(playwright, browser, context))),
            patch(
                "app.routers.sync_linkedin._scrape_linkedin_connections",
                new=AsyncMock(side_effect=RuntimeError("scrape kaputt")),
            ),
            pytest.raises(RuntimeError),
        ):
            await _sync_contacts_from_linkedin(db_session, None)

        browser.close.assert_awaited_once()
        playwright.stop.assert_awaited_once()

    async def test_positiv_bereits_vorhandener_kontakt_wird_verlinkt_nicht_dupliziert(self, db_session):
        from tests.factories import contact_factory

        existing = contact_factory(db_session, name="Max Mustermann", linkedin_url=None)
        db_session.commit()

        with (
            patch("app.routers.sync_company._get_linkedin_context", new=AsyncMock(return_value=_fake_linkedin_context())),
            patch(
                "app.routers.sync_linkedin._scrape_linkedin_connections",
                new=AsyncMock(return_value=[{
                    "name": "Max Mustermann",
                    "headline": None,
                    "profile_url": "https://www.linkedin.com/in/max-mustermann",
                }]),
            ),
        ):
            created, errors, touched_ids = await _sync_contacts_from_linkedin(db_session, None)

        assert created == 0
        assert touched_ids == [existing.id]
        db_session.refresh(existing)
        assert existing.linkedin_url == "https://www.linkedin.com/in/max-mustermann"
