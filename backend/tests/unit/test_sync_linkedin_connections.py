"""L0 Unit — _scrape_linkedin_connections() in sync_linkedin.py.

Scrapes the user's own LinkedIn connections list ("My Network" -> Connections)
using the same card-parsing core (_parse_people_anchors) as the manual people
search, but with "click Next" pagination like _scrape_category's job-tracker
scraper (the connections list is server-paginated, not infinite-scroll).
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routers.sync_linkedin import _scrape_linkedin_connections

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    # The scroll-to-bottom pacing (asyncio.sleep(1)/(1.5) per page) is real
    # wall-clock time in production but just wastes test runtime here.
    monkeypatch.setattr("app.routers.sync_linkedin.asyncio.sleep", AsyncMock())


class _FakeConnectionsPage:
    """Simulates a Playwright page rendering one card-list per "page" of
    connections, advancing to the next page's card set each time a Next
    button is successfully located+clicked."""

    def __init__(self, pages: list[list[tuple[str, str]]], url: str = "https://www.linkedin.com/mynetwork/invite-connect/connections/"):
        self._pages = pages
        self._index = 0
        self.url = url
        self.goto = AsyncMock()
        self.close = AsyncMock()
        self.evaluate = AsyncMock()
        self.wait_for_load_state = AsyncMock()

    def _current_anchors(self):
        specs = self._pages[self._index] if self._index < len(self._pages) else []
        anchors = []
        for href, text in specs:
            a = MagicMock()
            a.get_attribute = AsyncMock(return_value=href)
            a.inner_text = AsyncMock(return_value=text)
            anchors.append(a)
        return anchors

    def locator(self, selector: str):
        if selector == "a[href*='/in/']":
            loc = MagicMock()
            loc.all = AsyncMock(return_value=self._current_anchors())
            return loc

        # Next-button selector: only "found" while there's a further page.
        has_next = self._index < len(self._pages) - 1
        target = MagicMock()
        target.count = AsyncMock(return_value=1 if has_next else 0)
        target.is_visible = AsyncMock(return_value=has_next)
        target.scroll_into_view_if_needed = AsyncMock()

        async def _click(timeout=None):
            self._index += 1

        target.click = AsyncMock(side_effect=_click)
        wrapper = MagicMock()
        wrapper.first = target
        return wrapper


class TestScrapeLinkedinConnections:
    async def test_positiv_extrahiert_kandidaten_einer_seite(self):
        card = "\n".join(["Max Mustermann", "• 1st", "Senior Engineer at Contoso GmbH", "Message"])
        page = _FakeConnectionsPage([[("https://www.linkedin.com/in/max-mustermann/?trk=x", card)]])
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _scrape_linkedin_connections(context, max_pages=5)

        assert result == [{
            "name": "Max Mustermann",
            "headline": "Senior Engineer at Contoso GmbH",
            "profile_url": "https://www.linkedin.com/in/max-mustermann",
        }]
        page.close.assert_awaited_once()

    async def test_positiv_folgt_next_button_ueber_mehrere_seiten(self):
        card1 = "\n".join(["Anna Muster", "• 1st", "CTO at Beispiel AG"])
        card2 = "\n".join(["Tom Beispiel", "• 2nd", "Head of Sales at Foo GmbH"])
        page = _FakeConnectionsPage([
            [("https://www.linkedin.com/in/anna-muster/", card1)],
            [("https://www.linkedin.com/in/tom-beispiel/", card2)],
        ])
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _scrape_linkedin_connections(context, max_pages=5)

        assert {c["name"] for c in result} == {"Anna Muster", "Tom Beispiel"}

    async def test_negativ_login_redirect_liefert_leere_liste(self):
        page = _FakeConnectionsPage([[]], url="https://www.linkedin.com/authwall?x=1")
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _scrape_linkedin_connections(context, max_pages=5)

        assert result == []
        page.close.assert_awaited_once()

    async def test_negativ_goto_exception_liefert_leere_liste(self):
        page = MagicMock()
        page.goto = AsyncMock(side_effect=RuntimeError("timeout"))
        page.close = AsyncMock()
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _scrape_linkedin_connections(context, max_pages=5)

        assert result == []
        page.close.assert_awaited_once()

    async def test_corner_case_stoppt_bei_max_pages(self):
        card1 = "\n".join(["Max Mustermann", "• 1st", "Engineer"])
        card2 = "\n".join(["Anna Muster", "• 1st", "CTO"])
        page = _FakeConnectionsPage([
            [("https://www.linkedin.com/in/max/", card1)],
            [("https://www.linkedin.com/in/anna/", card2)],
        ])
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _scrape_linkedin_connections(context, max_pages=1)

        assert len(result) == 1
        assert result[0]["name"] == "Max Mustermann"

    async def test_corner_case_dedupliziert_ueber_seiten_hinweg(self):
        # Same profile URL showing up again on a later page (e.g. reordering
        # between page loads) must not be double-counted.
        card = "\n".join(["Max Mustermann", "• 1st", "Engineer"])
        page = _FakeConnectionsPage([
            [("https://www.linkedin.com/in/max/", card)],
            [("https://www.linkedin.com/in/max/", card)],
        ])
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _scrape_linkedin_connections(context, max_pages=5)

        assert len(result) == 1
