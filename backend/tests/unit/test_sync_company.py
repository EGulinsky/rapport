"""L0/L1 Unit — Wikidata-Parsing, company_type-Heuristik, LinkedIn-Fallback-Regex.

Firmensync wurde von DuckDuckGo+Wikipedia auf Wikidata (primär) + LinkedIn-
Company-Page (Fallback bei Wikidata-Fehltreffer) umgestellt. Grund: DDGs
Infobox-Label-Matching mischte über den generischen Keyword "type" die
Rechtsform (Public/Private) mit der Branche — 127 von 183 Firmen landeten
dadurch bei identisch "Softwareentwicklung". Wikidatas P452-Property hat
dieses Problem nicht.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.routers.sync_company import (
    _classify_company_type,
    _clean_query,
    _domain_from_url,
    _employee_range,
    _linkedin_company_fallback,
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
        # Regressionsfall des ursprünglichen Bugs: alteingesessene kleine
        # Firmen (z.B. 40 Jahre alter Handwerksbetrieb) dürfen nicht als
        # "startup" klassifiziert werden, nur weil sie wenige Mitarbeiter haben.
        assert _classify_company_type(50, 1985) == "kmu"

    def test_corner_case_mittelgrosse_firma_ist_kmu(self):
        assert _classify_company_type(400, 2000) == "kmu"


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
        # Der ursprüngliche Bug (DDG) mischte die Rechtsform ("Public company")
        # mit der Branche. Wikidatas P452 (industryLabel) ist sauber getrennt
        # von der Rechtsform (die hier gar nicht abgefragt wird).
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


def _fake_page(main_text: str, company_href: str | None):
    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.close = AsyncMock()

    locator = MagicMock()
    first = MagicMock()
    first.get_attribute = AsyncMock(return_value=company_href)
    locator.first = first

    main_locator = MagicMock()
    main_locator.inner_text = AsyncMock(return_value=main_text)

    def _locator(selector):
        return main_locator if selector == "main" else locator

    page.locator = MagicMock(side_effect=_locator)
    return page


class TestLinkedInCompanyFallback:
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
        page = _fake_page(about_text, "https://www.linkedin.com/company/contoso-gmbh/?trk=x")
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _linkedin_company_fallback(context, "Contoso GmbH")

        assert result["industry"] == "Maschinenbau"
        assert result["employee_count"] == 51
        assert "hq_city" not in result  # bewusst nicht extrahiert, siehe Klassen-Docstring
        assert result["founded_year"] == 1998
        assert result["website"] == "https://contoso.example"
        assert result["linkedin_company_url"] == "https://www.linkedin.com/company/contoso-gmbh"

    async def test_negativ_kein_suchtreffer_liefert_leeres_dict(self):
        page = _fake_page("", None)
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _linkedin_company_fallback(context, "Unbekannte Firma XYZ")

        assert result == {}

    async def test_negativ_exception_liefert_leeres_dict_statt_crash(self):
        page = MagicMock()
        page.goto = AsyncMock(side_effect=RuntimeError("Timeout"))
        page.close = AsyncMock()
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _linkedin_company_fallback(context, "Contoso GmbH")

        assert result == {}

    async def test_corner_case_grosse_firma_10001_plus(self):
        about_text = "\n".join([
            "Industry", "Softwareentwicklung",
            "Company size", "10,001+ employees",
        ])
        page = _fake_page(about_text, "https://www.linkedin.com/company/bigcorp/")
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _linkedin_company_fallback(context, "BigCorp")

        assert result["employee_count"] == 10001

    async def test_negativ_headquarters_wird_nie_extrahiert(self):
        # Live-Regressionsfall (ZEISS Group, Mpowering People): LinkedIns
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
        page = _fake_page(about_text, "https://www.linkedin.com/company/zeiss/")
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)

        result = await _linkedin_company_fallback(context, "ZEISS Group")

        assert "hq_city" not in result
