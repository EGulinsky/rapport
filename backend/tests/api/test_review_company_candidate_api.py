"""L2 API — /api/review für event_type="company_candidate" (Firmensync-Disambiguierung).

Mehrdeutige LinkedIn-Treffer landen als PendingMatch in der bestehenden
"Manuelle Überprüfung"-Queue statt live im Sync aufgelöst zu werden. Annehmen
(mit gewählter linkedin_url) übernimmt die Auswahl; Ablehnen ("keiner davon")
löst den Wikidata-Fallback für genau diese eine Firma aus.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import models
from tests.factories import company_profile_factory

pytestmark = pytest.mark.api


def _make_pending_match(db_session, profile_id: int, candidates: list[dict]) -> models.PendingMatch:
    match = models.PendingMatch(
        source="linkedin",
        external_id=f"company:{profile_id}",
        confidence=0,
        event_type="company_candidate",
        titel="Contoso GmbH",
        raw_content=json.dumps({"company_profile_id": profile_id, "candidates": candidates}),
        status_only=False,
        user_id=1,  # muss mit conftest.py::DEFAULT_TEST_USER_ID übereinstimmen
    )
    db_session.add(match)
    db_session.commit()
    db_session.refresh(match)
    return match


class TestApproveCompanyCandidate:
    def test_positiv_gewaehlte_url_wird_gescraped_und_uebernommen(self, client, db_session):
        p = company_profile_factory(db_session, sync_status="needs_review")
        match = _make_pending_match(db_session, p.id, [
            {"name": "Contoso GmbH", "url": "https://www.linkedin.com/company/contoso-gmbh"},
            {"name": "Contoso Inc.", "url": "https://www.linkedin.com/company/contoso-inc"},
        ])

        async def fake_get_context():
            playwright = MagicMock()
            playwright.stop = AsyncMock()
            browser = MagicMock()
            browser.close = AsyncMock()
            context = MagicMock()
            return playwright, browser, context

        async def fake_scrape_about(context, url):
            return {"industry": "Maschinenbau", "linkedin_company_url": url}

        with patch("app.routers.sync_company._get_linkedin_context", new=fake_get_context), \
             patch("app.routers.sync_company._linkedin_scrape_about", new=fake_scrape_about), \
             patch("app.routers.sync_company._fetch_logo_with_clearbit_fallback", new=AsyncMock(return_value=None)):
            resp = client.post(f"/api/review/{match.id}/approve", json={
                "linkedin_url": "https://www.linkedin.com/company/contoso-gmbh",
            })

        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

        db_session.expire_all()
        assert p.sync_status == "done"
        assert p.industry == "Maschinenbau"
        updated_match = db_session.query(models.PendingMatch).filter(models.PendingMatch.id == match.id).first()
        assert updated_match.review_status == "approved"

    def test_negativ_ohne_linkedin_url_wird_nichts_aufgeloest(self, client, db_session):
        p = company_profile_factory(db_session, sync_status="needs_review")
        match = _make_pending_match(db_session, p.id, [
            {"name": "Contoso GmbH", "url": "https://www.linkedin.com/company/contoso-gmbh"},
        ])

        resp = client.post(f"/api/review/{match.id}/approve", json={})

        assert resp.status_code == 200
        db_session.expire_all()
        # Ohne gewählte URL bleibt das Profil unverändert im Review-Status —
        # nur der PendingMatch wird als approved markiert.
        assert p.sync_status == "needs_review"


class TestRejectCompanyCandidate:
    def test_positiv_keiner_davon_loest_wikidata_fallback_aus(self, client, db_session):
        p = company_profile_factory(db_session, sync_status="needs_review")
        match = _make_pending_match(db_session, p.id, [
            {"name": "Contoso GmbH", "url": "https://www.linkedin.com/company/contoso-gmbh"},
        ])

        async def fake_get(self, url, params=None, **kw):
            resp = MagicMock()
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            resp.headers = {}
            resp.json.return_value = {"search": []}
            return resp

        with patch("httpx.AsyncClient.get", new=fake_get):
            resp = client.delete(f"/api/review/{match.id}")

        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

        db_session.expire_all()
        assert p.sync_status == "done"
        assert p.sync_error == "Kein LinkedIn-/Wikidata-Treffer gefunden"
        updated_match = db_session.query(models.PendingMatch).filter(models.PendingMatch.id == match.id).first()
        assert updated_match.review_status == "rejected"
