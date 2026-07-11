"""L1 Component — _get_linkedin_context() in sync_company.py.

Startet (best-effort) einen Playwright-Browser mit der gespeicherten
LinkedIn-Session. Läuft über eine eigene `SessionLocal()`-Session (nicht die
Request-Session) — daher L1 (echte Test-DB) statt L0.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import models
from app.routers.sync_company import _get_linkedin_context

pytestmark = pytest.mark.component


class TestGetLinkedinContext:
    async def test_negativ_keine_konfiguration_liefert_none(self, db_session):
        result = await _get_linkedin_context()
        assert result is None

    async def test_negativ_konfiguration_ohne_session_cookies_liefert_none(self, db_session):
        db_session.add(models.LinkedInSync(email="a@b.de", password_enc="x", session_cookies=None, user_id=1))
        db_session.commit()

        result = await _get_linkedin_context()

        assert result is None

    async def test_positiv_startet_browser_mit_gespeicherten_cookies(self, db_session):
        db_session.add(models.LinkedInSync(
            email="a@b.de", password_enc="x",
            session_cookies=json.dumps([{"name": "li_at", "value": "xyz"}]),
            user_id=1,
        ))
        db_session.commit()

        fake_context = MagicMock()
        fake_context.add_init_script = AsyncMock()
        fake_context.add_cookies = AsyncMock()
        fake_browser = MagicMock()
        fake_browser.new_context = AsyncMock(return_value=fake_context)
        fake_playwright_instance = MagicMock()
        fake_playwright_instance.chromium.launch = AsyncMock(return_value=fake_browser)
        fake_playwright_starter = MagicMock()
        fake_playwright_starter.start = AsyncMock(return_value=fake_playwright_instance)

        with patch("playwright.async_api.async_playwright", return_value=fake_playwright_starter):
            result = await _get_linkedin_context(user_id=1)

        assert result == (fake_playwright_instance, fake_browser, fake_context)
        fake_context.add_cookies.assert_awaited_once_with([{"name": "li_at", "value": "xyz"}])

    async def test_corner_case_kaputte_cookie_json_wird_abgefangen(self, db_session):
        db_session.add(models.LinkedInSync(
            email="a@b.de", password_enc="x", session_cookies="not-json", user_id=1,
        ))
        db_session.commit()

        fake_context = MagicMock()
        fake_context.add_init_script = AsyncMock()
        fake_context.add_cookies = AsyncMock()
        fake_browser = MagicMock()
        fake_browser.new_context = AsyncMock(return_value=fake_context)
        fake_playwright_instance = MagicMock()
        fake_playwright_instance.chromium.launch = AsyncMock(return_value=fake_browser)
        fake_playwright_starter = MagicMock()
        fake_playwright_starter.start = AsyncMock(return_value=fake_playwright_instance)

        with patch("playwright.async_api.async_playwright", return_value=fake_playwright_starter):
            result = await _get_linkedin_context(user_id=1)

        # Kaputtes JSON darf den Browserstart nicht verhindern — nur die Cookies fehlen dann.
        assert result == (fake_playwright_instance, fake_browser, fake_context)
        fake_context.add_cookies.assert_not_awaited()
