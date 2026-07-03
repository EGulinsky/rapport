"""L1 Component — _run_sync_batch() Cancel-Verhalten in sync_company.py.

Regressionstest für einen live gefundenen Bug: beim Umbau auf die
phasenbasierte Sync-Pipeline schrieb die Schreibphase über ALLE übergebenen
profile_ids, nicht nur über die tatsächlich versuchten. Bei einem Cancel
mitten in der Suche wurden dadurch auch nie angefasste Profile fälschlich auf
sync_status="done" mit sync_error="Kein ... Treffer gefunden" gesetzt.

Folge in Produktion: alle 183 CompanyProfiles landeten nach einem
abgebrochenen Force-Resync fälschlich als "done" — und weil "done"-Profile
laut _collect_sync_candidates NIE automatisch erneut aufgegriffen werden,
wären sie dauerhaft mit falschen "kein Treffer"-Fehlern hängen geblieben,
obwohl sie nie tatsächlich durchsucht wurden.

Fix: li_attempted_pids/wikidata_attempted_pids tracken nur wirklich versuchte
Profile; die Schreibphase schreibt nur für diese. Nicht versuchte Profile
bleiben "pending" (von _collect_sync_candidates bereits so gesetzt) und
werden beim nächsten normalen Sync-Lauf erneut erfasst.

Die Tests unten laufen ohne konfigurierte LinkedIn-Session (Standard in der
Test-DB) — _get_linkedin_context() liefert dann None, die Pipeline fällt
direkt auf Wikidata durch. Das deckt exakt den Live-Fall ab (Wikidata-Phase
abgebrochen). Ein separater Test deckt einen Cancel mitten in der
LinkedIn-Phase ab (mit gemockter Session).
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers import sync_company
from tests.factories import company_profile_factory

pytestmark = pytest.mark.component


class TestRunSyncBatchCancelWikidata:
    """Cancel während der Wikidata-Phase (kein LinkedIn konfiguriert)."""

    async def test_negativ_nicht_versuchte_profile_bleiben_pending_bei_cancel(self, db_session):
        p1 = company_profile_factory(db_session, sync_status="pending")
        p2 = company_profile_factory(db_session, sync_status="pending")
        p3 = company_profile_factory(db_session, sync_status="pending")
        db_session.commit()

        async def fake_search_one(client, name):
            # Cancel kommt "während" die erste Firma durchsucht wird — p1 gilt
            # als versucht (kein Treffer), p2/p3 werden nie angefasst.
            sync_company._SYNC_CANCEL = True
            return None

        with patch.object(sync_company, "_wikidata_search_one", new=fake_search_one), \
             patch.object(sync_company.asyncio, "sleep", new=AsyncMock()):
            await sync_company._run_sync_batch([p1.id, p2.id, p3.id])

        db_session.expire_all()
        assert p1.sync_status == "done"
        assert p1.sync_error == "Kein Wikidata-Treffer gefunden"
        assert p2.sync_status == "pending"
        assert p2.sync_error is None
        assert p3.sync_status == "pending"
        assert p3.sync_error is None

    async def test_negativ_gefundene_qid_ohne_sparql_bleibt_pending_bei_cancel(self, db_session):
        # Live-Regressionsfall: Cancel kam nach der Wikidata-Suche (fand bereits
        # eine Q-ID), aber vor der SPARQL-Abfrage der Q-ID-Daten. Ohne Fix
        # landete das Profil "done" mit "Kein Wikidata-Datensatz (nur
        # Basistreffer)" — obwohl SPARQL für diese Q-ID nie abgefragt wurde.
        # In Produktion betraf das nach einem User-Abbruch über 150 Firmen.
        p1 = company_profile_factory(db_session, sync_status="pending")
        db_session.commit()

        async def fake_search_one(client, name):
            sync_company._SYNC_CANCEL = True
            return ("Q12345", "Beschreibung")

        with patch.object(sync_company, "_wikidata_search_one", new=fake_search_one), \
             patch.object(sync_company.asyncio, "sleep", new=AsyncMock()):
            await sync_company._run_sync_batch([p1.id])

        db_session.expire_all()
        assert p1.sync_status == "pending"
        assert p1.sync_error is None
        assert p1.sync_source is None

    async def test_positiv_ohne_cancel_werden_alle_profile_verarbeitet(self, db_session):
        p1 = company_profile_factory(db_session, sync_status="pending")
        p2 = company_profile_factory(db_session, sync_status="pending")
        db_session.commit()

        async def fake_search_one(client, name):
            return None

        with patch.object(sync_company, "_wikidata_search_one", new=fake_search_one), \
             patch.object(sync_company.asyncio, "sleep", new=AsyncMock()):
            await sync_company._run_sync_batch([p1.id, p2.id])

        db_session.expire_all()
        assert p1.sync_status == "done"
        assert p2.sync_status == "done"


def _fake_linkedin_context():
    playwright = MagicMock()
    playwright.stop = AsyncMock()
    browser = MagicMock()
    browser.close = AsyncMock()
    context = MagicMock()
    return playwright, browser, context


class TestRunSyncBatchCancelLinkedin:
    """Cancel während der LinkedIn-Phase (primäre Quelle) — mit gemockter Session."""

    async def test_negativ_nicht_versuchte_profile_bleiben_pending_bei_cancel(self, db_session):
        p1 = company_profile_factory(db_session, sync_status="pending")
        p2 = company_profile_factory(db_session, sync_status="pending")
        db_session.commit()

        async def fake_get_context():
            return _fake_linkedin_context()

        async def fake_search_candidates(context, name, limit=5):
            sync_company._SYNC_CANCEL = True
            return []

        with patch.object(sync_company, "_get_linkedin_context", new=fake_get_context), \
             patch.object(sync_company, "_linkedin_search_candidates", new=fake_search_candidates), \
             patch.object(sync_company.asyncio, "sleep", new=AsyncMock()):
            await sync_company._run_sync_batch([p1.id, p2.id])

        db_session.expire_all()
        # p1: LinkedIn-Suche lief (0 Treffer) → für Wikidata vorgesehen, aber
        # Cancel kam davor → bleibt pending statt fälschlich "done".
        assert p1.sync_status == "pending"
        assert p1.sync_error is None
        # p2: nie angefasst (Cancel kam schon bei p1) → bleibt pending.
        assert p2.sync_status == "pending"
        assert p2.sync_error is None

    async def test_positiv_eindeutiger_treffer_wird_direkt_gescraped(self, db_session):
        p1 = company_profile_factory(db_session, sync_status="pending")
        db_session.commit()

        async def fake_get_context():
            return _fake_linkedin_context()

        async def fake_search_candidates(context, name, limit=5):
            return [{"name": "Contoso GmbH", "url": "https://www.linkedin.com/company/contoso"}]

        async def fake_scrape_about(context, url):
            return {"industry": "Maschinenbau", "employee_count": 50, "linkedin_company_url": url}

        with patch.object(sync_company, "_get_linkedin_context", new=fake_get_context), \
             patch.object(sync_company, "_linkedin_search_candidates", new=fake_search_candidates), \
             patch.object(sync_company, "_linkedin_scrape_about", new=fake_scrape_about), \
             patch.object(sync_company, "_fetch_logo_with_clearbit_fallback", new=AsyncMock(return_value=None)), \
             patch.object(sync_company.asyncio, "sleep", new=AsyncMock()):
            await sync_company._run_sync_batch([p1.id])

        db_session.expire_all()
        assert p1.sync_status == "done"
        assert p1.sync_source == "linkedin"
        assert p1.industry == "Maschinenbau"
        assert p1.employee_count == 50

    async def test_positiv_mehrere_treffer_erzeugen_pending_match(self, db_session):
        import json
        from app import models

        p1 = company_profile_factory(db_session, sync_status="pending")
        db_session.commit()

        async def fake_get_context():
            return _fake_linkedin_context()

        async def fake_search_candidates(context, name, limit=5):
            return [
                {"name": "Contoso GmbH", "url": "https://www.linkedin.com/company/contoso-gmbh"},
                {"name": "Contoso Inc.", "url": "https://www.linkedin.com/company/contoso-inc"},
            ]

        with patch.object(sync_company, "_get_linkedin_context", new=fake_get_context), \
             patch.object(sync_company, "_linkedin_search_candidates", new=fake_search_candidates), \
             patch.object(sync_company.asyncio, "sleep", new=AsyncMock()):
            await sync_company._run_sync_batch([p1.id])

        db_session.expire_all()
        assert p1.sync_status == "needs_review"

        match = db_session.query(models.PendingMatch).filter(
            models.PendingMatch.event_type == "company_candidate",
        ).first()
        assert match is not None
        assert match.review_status == "pending"
        payload = json.loads(match.raw_content)
        assert payload["company_profile_id"] == p1.id
        assert len(payload["candidates"]) == 2
