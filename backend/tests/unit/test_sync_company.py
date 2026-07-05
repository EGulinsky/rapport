"""L0/L1 Unit — LinkedIn-Suche/Scrape, Wikidata-Parsing, company_type-Heuristik, Feld-Anwendung.

Firmensync-Reihenfolge: LinkedIn-Firmenseite ist primär, Wikidata (Search API +
SPARQL) ist Fallback bei 0 (eindeutigen) LinkedIn-Treffern. Bei mehreren
LinkedIn-Treffern wird nicht geraten — die Firma landet als "needs_review" mit
einem PendingMatch in der bestehenden "Manuelle Überprüfung"-Queue
(app/routers/review.py), bis der User einen Kandidaten wählt oder "keiner
davon" klickt (siehe test_sync_company_review.py für diesen Teil).

Historischer Kontext für die Quellenwahl: DuckDuckGos Infobox-Label-Matching
mischte über den generischen Keyword "type" die Rechtsform (Public/Private)
mit der Branche — 127 von 183 Firmen landeten dadurch bei identisch
"Softwareentwicklung". Wikidatas P452-Property hat dieses Problem nicht.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.routers.sync_company import (
    _apply_linkedin_fields,
    _apply_wikidata_fields,
    _classify_company_type,
    _clean_query,
    _domain_from_url,
    _employee_range,
    _linkedin_scrape_about,
    _linkedin_search_candidates,
    _parse_year,
    _wikidata_search_one,
    _wikidata_sparql_batch,
)

pytestmark = pytest.mark.unit


def _mock_response(json_data, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    resp.json.return_value = json_data
    resp.headers = {}
    return resp


def _fake_profile(**overrides):
    defaults = dict(
        description=None, hq_city=None, hq_country=None, industry=None,
        employee_count=None, employee_range=None, founded_year=None,
        website=None, linkedin_company_url=None, company_type=None,
        logo_data=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestEmployeeRange:
    def test_positiv_grenzwerte(self):
        assert _employee_range(1) == "1-10"
        assert _employee_range(10) == "1-10"
        assert _employee_range(11) == "11-50"
        assert _employee_range(10000) == "5001-10000"

    def test_corner_case_ueber_max(self):
        assert _employee_range(50000) == "10001+"


class TestParseYear:
    def test_positiv_extrahiert_jahr_aus_iso_datum(self):
        assert _parse_year("1998-04-04T00:00:00Z") == 1998

    def test_negativ_kein_jahr_liefert_none(self):
        assert _parse_year("unbekannt") is None

    def test_corner_case_unplausibles_jahr_wird_verworfen(self):
        assert _parse_year("9999") is None


class TestCleanQuery:
    def test_positiv_kappt_headhunter_suffix(self):
        assert _clean_query("Akkodis | inContext AB") == "Akkodis"

    def test_negativ_ohne_trennzeichen_unveraendert(self):
        assert _clean_query("Contoso GmbH") == "Contoso GmbH"


class TestDomainFromUrl:
    def test_positiv_entfernt_www_praefix(self):
        assert _domain_from_url("https://www.example.com/about") == "example.com"

    def test_negativ_ungueltige_url_liefert_none(self):
        assert _domain_from_url("::not a url::") is None


class TestClassifyCompanyType:
    def test_negativ_ohne_mitarbeiterzahl_kein_typ(self):
        assert _classify_company_type(None, 2020) is None

    def test_positiv_grosskonzern(self):
        assert _classify_company_type(20000, 1990) == "konzern"

    def test_positiv_junge_kleine_firma_ist_startup(self):
        assert _classify_company_type(50, 2022) == "startup"

    def test_positiv_alte_kleine_firma_ist_kein_startup(self):
        assert _classify_company_type(50, 1985) == "kmu"

    def test_corner_case_mittelgrosse_firma_ist_kmu(self):
        assert _classify_company_type(400, 2000) == "kmu"


class TestApplyLinkedinFields:
    def test_positiv_setzt_felder_und_company_type(self):
        p = _fake_profile()
        _apply_linkedin_fields(p, {
            "industry": "Maschinenbau", "employee_count": 50,
            "founded_year": 2022, "website": "https://x.example",
            "linkedin_company_url": "https://www.linkedin.com/company/x",
        })
        assert p.industry == "Maschinenbau"
        assert p.employee_count == 50
        assert p.employee_range == "11-50"
        assert p.founded_year == 2022
        assert p.website == "https://x.example"
        assert p.company_type == "startup"

    def test_negativ_website_wird_nicht_ueberschrieben_wenn_vorhanden(self):
        p = _fake_profile(website="https://schon-da.example")
        _apply_linkedin_fields(p, {"website": "https://neu.example"})
        assert p.website == "https://schon-da.example"

    def test_corner_case_kein_hq_city_feld_wird_je_gesetzt(self):
        # _linkedin_scrape_about liefert nie "hq_city" (siehe eigene Testklasse) —
        # _apply_linkedin_fields liest es entsprechend auch nirgends.
        p = _fake_profile()
        _apply_linkedin_fields(p, {"hq_city": "Berlin", "industry": "IT"})
        assert p.hq_city is None


class TestApplyWikidataFields:
    def test_positiv_ueberschreibt_industrie_und_hq(self):
        p = _fake_profile(industry="Alt", hq_city="Alt-Stadt")
        _apply_wikidata_fields(p, "Beschreibung", {
            "industry": "Maschinenbau", "hq_city": "München", "hq_country": "Deutschland",
            "employee_count": 20000, "founded_year": 1990,
        })
        assert p.industry == "Maschinenbau"
        assert p.hq_city == "München"
        assert p.company_type == "konzern"

    def test_negativ_website_wird_nicht_ueberschrieben_wenn_vorhanden(self):
        p = _fake_profile(website="https://schon-da.example")
        _apply_wikidata_fields(p, "", {"website": "https://neu.example"})
        assert p.website == "https://schon-da.example"

    def test_negativ_leeres_data_dict_aendert_nichts(self):
        p = _fake_profile(industry="Bestand")
        _apply_wikidata_fields(p, "", {})
        assert p.industry == "Bestand"
        assert p.company_type is None


class TestWikidataSearchOne:
    async def test_positiv_liefert_qid_und_beschreibung(self):
        data = {"search": [{"id": "Q12345", "description": "deutsches Softwareunternehmen"}]}
        async def fake_get(self, url, params=None, **kw):
            return _mock_response(data)

        with patch("httpx.AsyncClient.get", new=fake_get):
            async with httpx.AsyncClient() as client:
                result = await _wikidata_search_one(client, "Contoso GmbH")

        assert result == ("Q12345", "deutsches Softwareunternehmen")

    async def test_negativ_kein_treffer_liefert_none(self):
        async def fake_get(self, url, params=None, **kw):
            return _mock_response({"search": []})

        with patch("httpx.AsyncClient.get", new=fake_get):
            async with httpx.AsyncClient() as client:
                result = await _wikidata_search_one(client, "Unbekannte Firma XYZ")

        assert result is None

    async def test_negativ_exception_wird_abgefangen(self):
        async def fake_get(self, url, params=None, **kw):
            raise httpx.ConnectError("kein Netz")

        with patch("httpx.AsyncClient.get", new=fake_get):
            async with httpx.AsyncClient() as client:
                result = await _wikidata_search_one(client, "Contoso GmbH")

        assert result is None


class TestWikidataSparqlBatch:
    async def test_positiv_industrie_kommt_aus_p452_nicht_aus_rechtsform(self):
        bindings = [{
            "company": {"value": "http://www.wikidata.org/entity/Q12345"},
            "hqLabel": {"value": "München"},
            "countryLabel": {"value": "Deutschland"},
            "industryLabel": {"value": "Maschinenbau"},
            "website": {"value": "https://contoso.example"},
            "employees": {"value": "120"},
            "founded": {"value": "1998-01-01T00:00:00Z"},
        }]
        data = {"results": {"bindings": bindings}}
        async def fake_get(self, url, params=None, **kw):
            return _mock_response(data)

        with patch("httpx.AsyncClient.get", new=fake_get):
            result = await _wikidata_sparql_batch(["Q12345"])

        assert result["Q12345"]["industry"] == "Maschinenbau"
        assert result["Q12345"]["hq_city"] == "München"
        assert result["Q12345"]["employee_count"] == 120
        assert result["Q12345"]["founded_year"] == 1998

    async def test_corner_case_linkedin_id_wird_zu_voller_url(self):
        bindings = [{
            "company": {"value": "http://www.wikidata.org/entity/Q99"},
            "linkedinId": {"value": "contoso-gmbh"},
        }]
        async def fake_get(self, url, params=None, **kw):
            return _mock_response({"results": {"bindings": bindings}})

        with patch("httpx.AsyncClient.get", new=fake_get):
            result = await _wikidata_sparql_batch(["Q99"])

        assert result["Q99"]["linkedin_company_url"] == "https://www.linkedin.com/company/contoso-gmbh"

    async def test_negativ_leere_bindings_liefert_leeres_dict(self):
        async def fake_get(self, url, params=None, **kw):
            return _mock_response({"results": {"bindings": []}})

        with patch("httpx.AsyncClient.get", new=fake_get):
            result = await _wikidata_sparql_batch(["Q1"])

        assert result == {}


def _fake_search_page(anchor_specs: list[tuple[str, str]]):
    """anchor_specs: Liste von (href, sichtbarer Name)."""
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


class TestLinkedinSearchCandidates:
    async def test_positiv_mehrere_eindeutige_treffer(self):
        page = _fake_search_page([
            ("https://www.linkedin.com/company/contoso-gmbh/?trk=x", "Contoso GmbH"),
            ("https://www.linkedin.com/company/contoso-inc/", "Contoso Inc."),
        ])
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _linkedin_search_candidates(context, "Contoso")

        assert result == [
            {"name": "Contoso GmbH", "url": "https://www.linkedin.com/company/contoso-gmbh", "snippet": None},
            {"name": "Contoso Inc.", "url": "https://www.linkedin.com/company/contoso-inc", "snippet": None},
        ]

    async def test_negativ_kein_treffer_liefert_leere_liste(self):
        page = _fake_search_page([])
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _linkedin_search_candidates(context, "Unbekannte Firma XYZ")

        assert result == []

    async def test_negativ_exception_liefert_leere_liste_statt_crash(self):
        page = MagicMock()
        page.goto = AsyncMock(side_effect=RuntimeError("Timeout"))
        page.close = AsyncMock()
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _linkedin_search_candidates(context, "Contoso GmbH")

        assert result == []

    async def test_corner_case_dedupliziert_gleiche_url_trotz_tracking_params(self):
        page = _fake_search_page([
            ("https://www.linkedin.com/company/contoso/?trk=a", "Contoso"),
            ("https://www.linkedin.com/company/contoso/?trk=b", "Contoso"),
        ])
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _linkedin_search_candidates(context, "Contoso")

        assert len(result) == 1

    async def test_corner_case_limit_wird_respektiert(self):
        anchors = [(f"https://www.linkedin.com/company/c{i}/", f"C{i}") for i in range(10)]
        page = _fake_search_page(anchors)
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _linkedin_search_candidates(context, "C", limit=3)

        assert len(result) == 3

    async def test_corner_case_fehlender_name_faellt_auf_url_slug_zurueck(self):
        page = _fake_search_page([("https://www.linkedin.com/company/contoso-gmbh/", "")])
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _linkedin_search_candidates(context, "Contoso")

        assert result[0]["name"] == "Contoso Gmbh"

    async def test_negativ_mehrzeilige_suchergebnis_karte_liefert_nur_ersten_zeile(self):
        # Live-Regressionsfall ('GitLab'): der Suchergebnis-Link umschließt die
        # ganze Karte (Name, Branche, Ort, "Follow"-Button, Beschreibung) —
        # inner_text() lieferte den kompletten Kartentext statt nur den Namen.
        card_text = "\n".join([
            "GitLab", "", "IT Services and IT Consulting", "",
            "San Francisco, California", "", "Follow", "",
            "GitLab is the Intelligent Orchestration Platform…",
        ])
        page = _fake_search_page([("https://www.linkedin.com/company/gitlab-com/", card_text)])
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _linkedin_search_candidates(context, "GitLab")

        assert result[0]["name"] == "GitLab"

    async def test_positiv_snippet_aus_branche_und_ort_fuer_disambiguierung(self):
        # Hilft im Review-Modal, mehrere Treffer zu unterscheiden (z.B.
        # "GitLab" von "GitLab Foundation").
        card_text = "\n".join([
            "GitLab", "", "IT Services and IT Consulting", "",
            "San Francisco, California", "", "Follow", "",
            "GitLab is the Intelligent Orchestration Platform…",
        ])
        page = _fake_search_page([("https://www.linkedin.com/company/gitlab-com/", card_text)])
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _linkedin_search_candidates(context, "GitLab")

        assert result[0]["snippet"] == "IT Services and IT Consulting · San Francisco, California"

    async def test_negativ_kein_snippet_bei_nur_einer_zeile(self):
        page = _fake_search_page([("https://www.linkedin.com/company/contoso/", "Contoso")])
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _linkedin_search_candidates(context, "Contoso")

        assert result[0]["snippet"] is None


def _fake_about_page(main_text: str):
    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.close = AsyncMock()
    main_locator = MagicMock()
    main_locator.inner_text = AsyncMock(return_value=main_text)
    page.locator = MagicMock(return_value=main_locator)
    return page


class TestLinkedinScrapeAbout:
    async def test_positiv_extrahiert_felder_aus_about_seite(self):
        about_text = "\n".join([
            "Contoso GmbH",
            "Industry",
            "Maschinenbau",
            "Company size",
            "51-200 employees",
            "Headquarters",
            "München, Bayern",
            "Founded",
            "1998",
            "Website",
            "https://contoso.example",
        ])
        page = _fake_about_page(about_text)
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _linkedin_scrape_about(context, "https://www.linkedin.com/company/contoso-gmbh")

        assert result["industry"] == "Maschinenbau"
        assert result["employee_count"] == 51
        assert "hq_city" not in result  # bewusst nicht extrahiert, siehe Klassen-Docstring
        assert result["founded_year"] == 1998
        assert result["website"] == "https://contoso.example"
        assert result["linkedin_company_url"] == "https://www.linkedin.com/company/contoso-gmbh"

    async def test_negativ_exception_liefert_leeres_dict_statt_crash(self):
        page = MagicMock()
        page.goto = AsyncMock(side_effect=RuntimeError("Timeout"))
        page.close = AsyncMock()
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _linkedin_scrape_about(context, "https://www.linkedin.com/company/contoso-gmbh")

        assert result == {}

    async def test_corner_case_grosse_firma_10001_plus(self):
        about_text = "\n".join([
            "Industry", "Softwareentwicklung",
            "Company size", "10,001+ employees",
        ])
        page = _fake_about_page(about_text)
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _linkedin_scrape_about(context, "https://www.linkedin.com/company/bigcorp")

        assert result["employee_count"] == 10001

    async def test_negativ_headquarters_wird_nie_extrahiert(self):
        # Live-Regressionsfall (reale Firmenprofile mit ungewöhnlicher Feldbelegung): LinkedIns
        # 'About'-Seite rendert unter "Headquarters" teils eine unsichtbare
        # Screenreader-Zeile ("Hauptsitz-Stadt"), die inner_text() mitliefert
        # und ohne zuverlässiges Filtermuster fälschlich als hq_city landete.
        # Deshalb wird das Feld bewusst gar nicht mehr aus LinkedIn gelesen —
        # Wikidata (P159) ist hier die verlässliche Quelle.
        about_text = "\n".join([
            "Headquarters",
            "Hauptsitz-Stadt",
            "Oberkochen, Baden-Württemberg",
        ])
        page = _fake_about_page(about_text)
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _linkedin_scrape_about(context, "https://www.linkedin.com/company/zeiss")

        assert "hq_city" not in result
