"""L1 Component — resolve_company_candidate() in sync_company.py.

Wird vom Review-Modal aufgerufen, wenn der User eine mehrdeutige LinkedIn-
Firmensuche manuell auflöst: entweder einen der Kandidaten wählt (annehmen)
oder "keiner davon" klickt (ablehnen → Wikidata-Fallback für genau diese
eine Firma).
"""
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.routers.sync_company import resolve_company_candidate
from tests.factories import company_profile_factory

pytestmark = pytest.mark.component


def _mock_response(json_data, status=200):
    from unittest.mock import MagicMock
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    resp.json.return_value = json_data
    resp.headers = {}
    return resp


class TestResolveCompanyCandidateWithUrl:
    async def test_positiv_scraped_gewaehlte_url_und_setzt_done(self, db_session):
        p = company_profile_factory(db_session, sync_status="needs_review")
        db_session.commit()

        async def fake_get_context():
            from unittest.mock import MagicMock
            playwright = MagicMock()
            playwright.stop = AsyncMock()
            browser = MagicMock()
            browser.close = AsyncMock()
            context = MagicMock()
            return playwright, browser, context

        async def fake_scrape_about(context, url):
            return {"industry": "Maschinenbau", "employee_count": 50, "linkedin_company_url": url}

        with patch("app.routers.sync_company._get_linkedin_context", new=fake_get_context), \
             patch("app.routers.sync_company._linkedin_scrape_about", new=fake_scrape_about), \
             patch("app.routers.sync_company._fetch_logo_with_clearbit_fallback", new=AsyncMock(return_value=None)):
            await resolve_company_candidate(db_session, p.id, "https://www.linkedin.com/company/contoso")

        db_session.commit()
        db_session.expire_all()
        assert p.sync_status == "done"
        assert p.sync_source == "linkedin"
        assert p.industry == "Maschinenbau"
        assert p.employee_count == 50
        assert p.sync_error is None

    async def test_negativ_scrape_fehlschlag_setzt_trotzdem_done_mit_hinweis(self, db_session):
        p = company_profile_factory(db_session, sync_status="needs_review")
        db_session.commit()

        async def fake_get_context():
            return None

        with patch("app.routers.sync_company._get_linkedin_context", new=fake_get_context), \
             patch("app.routers.sync_company._fetch_logo_with_clearbit_fallback", new=AsyncMock(return_value=None)):
            await resolve_company_candidate(db_session, p.id, "https://www.linkedin.com/company/contoso")

        db_session.commit()
        db_session.expire_all()
        assert p.sync_status == "done"
        assert p.sync_source == "linkedin"
        assert "fehlgeschlagen" in (p.sync_error or "")


class TestResolveCompanyCandidateNone:
    async def test_positiv_keiner_davon_faellt_auf_wikidata_zurueck(self, db_session):
        p = company_profile_factory(db_session, sync_status="needs_review")
        db_session.commit()

        search_data = {"search": [{"id": "Q999", "description": "Testfirma"}]}
        sparql_bindings = [{
            "company": {"value": "http://www.wikidata.org/entity/Q999"},
            "industryLabel": {"value": "Chemie"},
        }]

        call_urls = []

        async def fake_get(self, url, params=None, **kw):
            call_urls.append(url)
            if "wbsearchentities" in str(params):
                return _mock_response(search_data)
            return _mock_response({"results": {"bindings": sparql_bindings}})

        with patch("httpx.AsyncClient.get", new=fake_get), \
             patch("app.routers.sync_company._fetch_logo", new=AsyncMock(return_value=None)), \
             patch("app.routers.sync_company._fetch_logo_with_clearbit_fallback", new=AsyncMock(return_value=None)):
            await resolve_company_candidate(db_session, p.id, None)

        db_session.commit()
        db_session.expire_all()
        assert p.sync_status == "done"
        assert p.sync_source == "wikidata:Q999"
        assert p.industry == "Chemie"

    async def test_negativ_keiner_davon_und_kein_wikidata_treffer(self, db_session):
        p = company_profile_factory(db_session, sync_status="needs_review")
        db_session.commit()

        async def fake_get(self, url, params=None, **kw):
            return _mock_response({"search": []})

        with patch("httpx.AsyncClient.get", new=fake_get):
            await resolve_company_candidate(db_session, p.id, None)

        db_session.commit()
        db_session.expire_all()
        assert p.sync_status == "done"
        assert p.sync_error == "Kein LinkedIn-/Wikidata-Treffer gefunden"

    async def test_negativ_unbekannte_profile_id_tut_nichts(self, db_session):
        # Sollte nicht crashen, wenn das Profil zwischenzeitlich gelöscht wurde.
        await resolve_company_candidate(db_session, 999999, None)
