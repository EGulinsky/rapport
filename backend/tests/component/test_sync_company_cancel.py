"""L1 Component — _run_sync_batch() Cancel-Verhalten in sync_company.py.

Regressionstest für einen live gefundenen Bug: beim Umbau auf die
phasenbasierte Wikidata-Pipeline schrieb Phase 5 ("Ergebnisse schreiben")
über ALLE übergebenen profile_ids, nicht nur über die tatsächlich
durchsuchten. Bei einem Cancel mitten in Phase 1 (Wikidata-Suche) wurden
dadurch auch nie versuchte Profile fälschlich auf sync_status="done" mit
sync_error="Kein ... Treffer gefunden" gesetzt.

Folge in Produktion: alle 183 CompanyProfiles landeten nach einem
abgebrochenen Force-Resync fälschlich als "done" — und weil "done"-Profile
laut _collect_sync_candidates NIE automatisch erneut aufgegriffen werden,
wären sie dauerhaft mit falschen "kein Treffer"-Fehlern hängen geblieben,
obwohl sie nie tatsächlich durchsucht wurden.

Fix: attempted_pids trackt nur wirklich versuchte Profile; Phase 5 schreibt
nur für diese. Nicht versuchte Profile bleiben "pending" (von
_collect_sync_candidates bereits so gesetzt) und werden beim nächsten
normalen Sync-Lauf erneut erfasst.
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.routers import sync_company
from tests.factories import company_profile_factory

pytestmark = pytest.mark.component


class TestRunSyncBatchCancel:
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
        assert p1.sync_error == "Kein Wikidata-/LinkedIn-Treffer gefunden"
        assert p2.sync_status == "pending"
        assert p2.sync_error is None
        assert p3.sync_status == "pending"
        assert p3.sync_error is None

    async def test_negativ_gefundene_qid_ohne_sparql_bleibt_pending_bei_cancel(self, db_session):
        # Live-Regressionsfall: Cancel kam nach Phase 1 (Wikidata-Suche fand
        # bereits eine Q-ID), aber vor Phase 3 (SPARQL-Abfrage der Q-ID-Daten).
        # Ohne Fix landete das Profil "done" mit "Kein Wikidata-Datensatz (nur
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
