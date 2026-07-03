"""L0 Unit — _linkedin_search_people() / _split_headline() in sync_linkedin.py.

Manuelle Personensuche für den Kontakt-Import: reine on-demand Suche, kein
Hintergrund-Batch. Nutzt dasselbe "erste Zeile = Name"-Muster wie der
Firmen-Suchscraper (sync_company.py), da LinkedIns Ergebnis-Link auch hier
oft die ganze Karte umschließt statt nur den Namen.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routers.sync_linkedin import _linkedin_search_people, _split_headline

pytestmark = pytest.mark.unit


def _fake_search_page(anchor_specs: list[tuple[str, str]]):
    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.close = AsyncMock()

    anchors = []
    for href, text in anchor_specs:
        a = MagicMock()
        a.get_attribute = AsyncMock(return_value=href)
        a.inner_text = AsyncMock(return_value=text)
        anchors.append(a)

    locator = MagicMock()
    locator.all = AsyncMock(return_value=anchors)
    page.locator = MagicMock(return_value=locator)
    return page


class TestLinkedinSearchPeople:
    async def test_positiv_extrahiert_name_und_headline(self):
        card_text = "\n".join(["Max Mustermann", "• 1st", "Senior Engineer at Contoso GmbH", "Connect"])
        page = _fake_search_page([("https://www.linkedin.com/in/max-mustermann/?trk=x", card_text)])
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _linkedin_search_people(context, "Max Mustermann")

        assert result == [{
            "name": "Max Mustermann",
            "headline": "Senior Engineer at Contoso GmbH",
            "profile_url": "https://www.linkedin.com/in/max-mustermann",
        }]

    async def test_negativ_kein_treffer_liefert_leere_liste(self):
        page = _fake_search_page([])
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _linkedin_search_people(context, "Unbekannte Person XYZ")

        assert result == []

    async def test_negativ_exception_liefert_leere_liste_statt_crash(self):
        page = MagicMock()
        page.goto = AsyncMock(side_effect=RuntimeError("Timeout"))
        page.close = AsyncMock()
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _linkedin_search_people(context, "Max Mustermann")

        assert result == []

    async def test_corner_case_dedupliziert_gleiche_profil_url(self):
        page = _fake_search_page([
            ("https://www.linkedin.com/in/max/?trk=a", "Max\n• 1st"),
            ("https://www.linkedin.com/in/max/?trk=b", "Max\n• 1st"),
        ])
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _linkedin_search_people(context, "Max")

        assert len(result) == 1

    async def test_corner_case_kein_headline_treffer_ohne_zweite_zeile(self):
        page = _fake_search_page([("https://www.linkedin.com/in/max/", "Max Mustermann\n• 2nd")])
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _linkedin_search_people(context, "Max")

        assert result[0]["headline"] is None

    async def test_negativ_rauschen_wird_nicht_als_headline_verwendet(self):
        # "1st"/"Connect"/etc. sind Verbindungsgrad- bzw. Button-Text, keine Headline.
        card_text = "\n".join(["Max Mustermann", "• 1st", "Connect"])
        page = _fake_search_page([("https://www.linkedin.com/in/max/", card_text)])
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _linkedin_search_people(context, "Max")

        assert result[0]["headline"] is None

    async def test_negativ_verbindungsgrad_klebt_am_namen_wird_entfernt(self):
        # Live-Regressionsfall (Suche nach 'Satya Nadella'): der Verbindungsgrad
        # steht nicht immer als eigene Zeile, sondern klebt direkt am Namen
        # ("Satya Nadella • 3rd+") — ohne Fix landete "• 3rd+" im Namen.
        card_text = "\n".join(["Satya Nadella • 3rd+", "Technical Support Specialist at Contoso Inc."])
        page = _fake_search_page([("https://www.linkedin.com/in/satyanadella/", card_text)])
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _linkedin_search_people(context, "Satya Nadella")

        assert result[0]["name"] == "Satya Nadella"
        assert result[0]["headline"] == "Technical Support Specialist at Contoso Inc."

    async def test_negativ_gemeinsame_kontakte_erwaehnung_wird_nicht_als_treffer_gezaehlt(self):
        # Live-Regressionsfall (Suche nach 'Michael Schmidt'): LinkedIns
        # Ergebnisliste verlinkt auch Personen, die nur als "X, Y und 20
        # weitere gemeinsame Kontakte" innerhalb einer FREMDEN Karte erwähnt
        # werden. Diese Erwähnungs-Links haben dieselbe /in/-Struktur wie
        # echte Suchergebnisse, aber nur den nackten Namen als Text (kein
        # Verbindungsgrad) — ohne Filter landeten sie als Kandidaten ohne
        # Firma/Headline und verbrauchten das `limit`-Kontingent, sodass es
        # wirkte, als käme nur die erste Trefferseite zurück.
        real_card = "\n".join([
            "Michael Schmidt • 2nd", "Team Lead at Contoso GmbH", "Fulda, Germany",
            "Connect", "Anna Muster, Tom Beispiel and 20 other mutual connections",
        ])
        page = _fake_search_page([
            ("https://www.linkedin.com/in/michael-schmidt-real/", real_card),
            ("https://www.linkedin.com/in/michael-schmidt-real/", "Michael Schmidt"),  # doppelter Link, nur Name
            ("https://www.linkedin.com/in/anna-muster/", "Anna Muster"),  # gemeinsamer Kontakt, kein echter Treffer
            ("https://www.linkedin.com/in/tom-beispiel/", "Tom Beispiel"),  # dito
        ])
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _linkedin_search_people(context, "Michael Schmidt")

        assert len(result) == 1
        assert result[0]["name"] == "Michael Schmidt"
        assert result[0]["headline"] == "Team Lead at Contoso GmbH"


class TestSplitHeadline:
    def test_positiv_englisches_at(self):
        assert _split_headline("Senior Engineer at Contoso GmbH") == ("Senior Engineer", "Contoso GmbH")

    def test_positiv_deutsches_bei(self):
        assert _split_headline("Senior Entwicklerin bei Contoso GmbH") == ("Senior Entwicklerin", "Contoso GmbH")

    def test_positiv_klammeraffe(self):
        assert _split_headline("Head of Sales @ Contoso GmbH") == ("Head of Sales", "Contoso GmbH")

    def test_negativ_kein_trenner_liefert_ganze_headline_als_rolle(self):
        assert _split_headline("Freiberuflich") == ("Freiberuflich", None)

    def test_negativ_headline_ohne_firmenerwaehnung_liefert_keine_firma(self):
        # Live-Regressionsfall (Philip Knöpfle): viele individuell angepasste
        # Headlines enthalten die Firma überhaupt nicht — kein Trenner heißt
        # hier nicht "geraten", sondern "firma bleibt None".
        assert _split_headline("Head of Customer Program Management") == ("Head of Customer Program Management", None)

    def test_negativ_pipe_getrennte_skill_liste_wird_nicht_als_firma_geraten(self):
        # Live beobachtet: Pipe-Zeichen trennen bei vielen Headlines Skills/
        # Schlagworte, nicht "Rolle | Firma" — ein Split auf " | " würde z.B.
        # "Ms Excel" fälschlich als Firma extrahieren.
        headline = "Data Analyst | Ms Excel | Power BI | Datastage | Netezza | Db2"
        rolle, firma = _split_headline(headline)
        assert firma is None
        assert rolle == headline

    def test_negativ_none_liefert_none_none(self):
        assert _split_headline(None) == (None, None)
