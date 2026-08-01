"""L0 Unit — _scrape_linkedin_connections() in sync_linkedin.py.

Scrapes the user's own LinkedIn connections list ("My Network" -> Connections).
Two things make this page's markup genuinely different from the people-search-
results page (found via live verification against a real account after the
first version of this scraper silently returned zero results):

1. No connection-degree marker ("• 1st") is ever rendered here — every entry
   is already a 1st-degree connection, so there's nothing to filter mutual-
   connection mentions against the way the search-results scraper needs to.
2. Each card renders TWO `a[href*='/in/']` anchors for the same profile: one
   wrapping only the avatar (empty inner_text), one wrapping the name+headline
   text. Dedup must skip the empty one without "spending" the href on it.

Pagination is scroll-triggered (infinite scroll, no Next button, no ?page=)
and terminates once two consecutive scrolls yield no new candidates.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routers.sync_linkedin import _scrape_linkedin_connections

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    # The scroll-to-bottom pacing (asyncio.sleep) is real wall-clock time in
    # production but just wastes test runtime here.
    monkeypatch.setattr("app.routers.sync_linkedin.asyncio.sleep", AsyncMock())


def _card_anchors(href: str, name: str, headline: str | None) -> list[tuple[str, str]]:
    """One real card's two anchors: an empty avatar-only duplicate first,
    then the text-bearing name+headline anchor — matches the real DOM order
    observed live."""
    text = f"{name}\n\n{headline}" if headline else name
    return [(href, ""), (href, text)]


class _FakeConnectionsPage:
    """Simulates infinite-scroll loading: the visible anchor set grows with
    each scroll-to-bottom, plateauing at the last snapshot once all content
    has "loaded" — no click-based pagination involved."""

    def __init__(self, snapshots: list[list[tuple[str, str]]], url: str = "https://www.linkedin.com/mynetwork/invite-connect/connections/"):
        self._snapshots = snapshots
        self._scroll_count = 0
        self.url = url
        self.goto = AsyncMock()
        self.close = AsyncMock()

    async def evaluate(self, script):
        self._scroll_count += 1

    def locator(self, selector: str):
        assert selector == "a[href*='/in/']"
        idx = min(max(self._scroll_count - 1, 0), len(self._snapshots) - 1) if self._snapshots else 0
        specs = self._snapshots[idx] if self._snapshots else []
        anchors = []
        for href, text in specs:
            a = MagicMock()
            a.get_attribute = AsyncMock(return_value=href)
            a.inner_text = AsyncMock(return_value=text)
            anchors.append(a)
        loc = MagicMock()
        loc.all = AsyncMock(return_value=anchors)
        return loc


class TestScrapeLinkedinConnections:
    async def test_positiv_extrahiert_kandidat_trotz_avatar_anker_duplikat(self):
        anchors = _card_anchors("https://www.linkedin.com/in/max-mustermann/?trk=x", "Max Mustermann", "Senior Engineer at Contoso GmbH")
        page = _FakeConnectionsPage([anchors])
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _scrape_linkedin_connections(context, max_scrolls=5)

        assert result == [{
            "name": "Max Mustermann",
            "headline": "Senior Engineer at Contoso GmbH",
            "profile_url": "https://www.linkedin.com/in/max-mustermann",
        }]
        page.close.assert_awaited_once()

    async def test_positiv_kein_verbindungsgrad_noetig(self):
        # The old (broken) implementation required a "• 1st" marker in the
        # anchor text — this page never renders one, so that check must be
        # gone entirely.
        anchors = _card_anchors("https://www.linkedin.com/in/anna/", "Anna Muster", "CTO at Beispiel AG")
        page = _FakeConnectionsPage([anchors])
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _scrape_linkedin_connections(context, max_scrolls=5)

        assert len(result) == 1
        assert result[0]["name"] == "Anna Muster"

    async def test_positiv_headline_ohne_trenner_bleibt_wie_geliefert(self):
        anchors = _card_anchors("https://www.linkedin.com/in/tobias/", "Tobias von Rad", "--")
        page = _FakeConnectionsPage([anchors])
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _scrape_linkedin_connections(context, max_scrolls=5)

        assert result[0]["headline"] == "--"

    async def test_positiv_waechst_ueber_mehrere_scrolls_bis_plateau(self):
        card1 = _card_anchors("https://www.linkedin.com/in/anna/", "Anna Muster", "CTO")
        card2 = _card_anchors("https://www.linkedin.com/in/tom/", "Tom Beispiel", "Head of Sales")
        snapshots = [
            card1,             # scroll 1: only first contact loaded
            card1 + card2,     # scroll 2: second contact appears
            card1 + card2,     # scroll 3: no growth (stall #1)
            card1 + card2,     # scroll 4: no growth (stall #2) -> stop here
        ]
        page = _FakeConnectionsPage(snapshots)
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _scrape_linkedin_connections(context, max_scrolls=20)

        assert {c["name"] for c in result} == {"Anna Muster", "Tom Beispiel"}
        # Stopped after the two-stall plateau, not by exhausting max_scrolls.
        assert page._scroll_count == 4

    async def test_negativ_login_redirect_liefert_leere_liste(self):
        page = _FakeConnectionsPage([[]], url="https://www.linkedin.com/authwall?x=1")
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _scrape_linkedin_connections(context, max_scrolls=5)

        assert result == []
        page.close.assert_awaited_once()

    async def test_negativ_goto_exception_liefert_leere_liste(self):
        page = MagicMock()
        page.goto = AsyncMock(side_effect=RuntimeError("timeout"))
        page.close = AsyncMock()
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _scrape_linkedin_connections(context, max_scrolls=5)

        assert result == []
        page.close.assert_awaited_once()

    async def test_corner_case_stoppt_bei_max_scrolls(self):
        card1 = _card_anchors("https://www.linkedin.com/in/max/", "Max Mustermann", "Engineer")
        card2 = _card_anchors("https://www.linkedin.com/in/anna/", "Anna Muster", "CTO")
        # Keeps growing every scroll (never plateaus) -> max_scrolls is the
        # only thing that stops it.
        snapshots = [card1, card1 + card2, card1 + card2 + [("https://www.linkedin.com/in/extra/", "")]]
        page = _FakeConnectionsPage(snapshots)
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _scrape_linkedin_connections(context, max_scrolls=1)

        assert len(result) == 1
        assert result[0]["name"] == "Max Mustermann"

    async def test_corner_case_dedupliziert_ueber_scrolls_hinweg(self):
        card = _card_anchors("https://www.linkedin.com/in/max/", "Max Mustermann", "Engineer")
        page = _FakeConnectionsPage([card, card])
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _scrape_linkedin_connections(context, max_scrolls=5)

        assert len(result) == 1
