"""L0 Unit — scrape_own_profile() in sync_linkedin.py.

Extracts broad visible text from the profile page's <main> element rather
than targeting specific section selectors (headline/about/experience) —
there's no established selector set for LinkedIn profile pages anywhere in
this codebase, and its DOM/class names change often; broad text extraction
degrades gracefully instead of breaking outright when the layout shifts."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routers.sync_linkedin import MAX_PROFILE_TEXT_CHARS, scrape_own_profile

pytestmark = pytest.mark.unit


def _fake_profile_page(main_text: str | None, main_count: int = 1):
    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.close = AsyncMock()

    main = MagicMock()
    main.count = AsyncMock(return_value=main_count)
    if main_text is not None:
        main.inner_text = AsyncMock(return_value=main_text)
    page.locator = MagicMock(return_value=main)
    return page


class TestScrapeOwnProfile:
    async def test_positiv_extrahiert_und_normalisiert_text(self):
        raw = "Senior Engineer at Contoso\n\n\n\nAbout\n\n\nBuilding things."
        page = _fake_profile_page(raw)
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await scrape_own_profile(context, "https://linkedin.com/in/jane-doe")

        assert result == "Senior Engineer at Contoso\n\nAbout\n\nBuilding things."
        page.goto.assert_awaited_once_with(
            "https://linkedin.com/in/jane-doe", wait_until="domcontentloaded", timeout=20000
        )
        page.close.assert_awaited_once()

    async def test_positiv_kappt_bei_max_zeichen(self):
        page = _fake_profile_page("x" * (MAX_PROFILE_TEXT_CHARS + 500))
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await scrape_own_profile(context, "https://linkedin.com/in/jane-doe")

        assert len(result) == MAX_PROFILE_TEXT_CHARS

    async def test_negativ_kein_main_element_liefert_none(self):
        page = _fake_profile_page(None, main_count=0)
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await scrape_own_profile(context, "https://linkedin.com/in/jane-doe")

        assert result is None
        page.close.assert_awaited_once()

    async def test_negativ_leerer_text_liefert_none(self):
        page = _fake_profile_page("   \n\n  ")
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await scrape_own_profile(context, "https://linkedin.com/in/jane-doe")

        assert result is None

    async def test_negativ_navigation_fehler_liefert_none_statt_exception(self):
        page = MagicMock()
        page.goto = AsyncMock(side_effect=TimeoutError("navigation timed out"))
        page.close = AsyncMock()
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await scrape_own_profile(context, "https://linkedin.com/in/jane-doe")

        assert result is None
        page.close.assert_awaited_once()
