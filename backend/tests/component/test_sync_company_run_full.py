"""L1 Component — _run_sync_batch() Happy-Path & Fehlerzweige (kein Cancel).

Ergänzt tests/component/test_sync_company_cancel.py, das ausschließlich das
Abbruchverhalten testet. Hier: der vollständige Wikidata-Erfolgspfad inkl.
Logo-Download (Phase 4/5, bislang nie bis zum Ende durchlaufen, weil die
Cancel-Tests absichtlich vor der SPARQL-Antwort abbrechen), sowie einzelne
Fehlerzweige (LinkedIn-Browser-Start, LinkedIn-Suche/Scrape, SPARQL-Batch,
gelöschtes Profil zwischen den Phasen, unerwarteter Top-Level-Fehler).
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import models
from app.database import SessionLocal
from app.routers import sync_company
from tests.factories import company_profile_factory

pytestmark = pytest.mark.component


def _fake_linkedin_context():
    playwright = MagicMock()
    playwright.stop = AsyncMock()
    browser = MagicMock()
    browser.close = AsyncMock()
    context = MagicMock()
    return playwright, browser, context


class TestRunSyncBatchWikidataHappyPath:
    async def test_positiv_kompletter_wikidata_erfolg_inkl_logo(self, db_session):
        p = company_profile_factory(db_session, sync_status="pending", website=None)
        db_session.commit()

        async def fake_search_one(client, name):
            return ("Q12345", "Ein deutsches Unternehmen")

        async def fake_sparql_batch(qids):
            return {"Q12345": {
                "industry": "Maschinenbau", "hq_city": "München",
                "employee_count": 20000, "founded_year": 1990,
                "website": "https://contoso.example", "logo_url": "http://wiki.example/logo.svg",
            }}

        with patch.object(sync_company, "_wikidata_search_one", new=fake_search_one), \
             patch.object(sync_company, "_wikidata_sparql_batch", new=fake_sparql_batch), \
             patch.object(sync_company, "_fetch_logo", new=AsyncMock(return_value="data:image/svg+xml;base64,LOGO")), \
             patch.object(sync_company.asyncio, "sleep", new=AsyncMock()):
            await sync_company._run_sync_batch([p.id], 1)

        db_session.expire_all()
        assert p.sync_status == "done"
        assert p.sync_source == "wikidata:Q12345"
        assert p.industry == "Maschinenbau"
        assert p.employee_count == 20000
        assert p.company_type == "konzern"
        assert p.logo_data == "data:image/svg+xml;base64,LOGO"
        assert p.sync_error is None

    async def test_positiv_wikidata_ohne_logo_url_nutzt_clearbit_fallback(self, db_session):
        p = company_profile_factory(db_session, sync_status="pending", website=None, logo_data=None)
        db_session.commit()

        async def fake_search_one(client, name):
            return ("Q1", "Testfirma")

        async def fake_sparql_batch(qids):
            return {"Q1": {"industry": "IT", "website": "https://contoso.example"}}

        with patch.object(sync_company, "_wikidata_search_one", new=fake_search_one), \
             patch.object(sync_company, "_wikidata_sparql_batch", new=fake_sparql_batch), \
             patch.object(sync_company, "_fetch_logo_with_clearbit_fallback",
                          new=AsyncMock(return_value="data:image/png;base64,CLEARBIT")), \
             patch.object(sync_company.asyncio, "sleep", new=AsyncMock()):
            await sync_company._run_sync_batch([p.id], 1)

        db_session.expire_all()
        assert p.sync_status == "done"
        assert p.logo_data == "data:image/png;base64,CLEARBIT"

    async def test_negativ_kein_treffer_weder_linkedin_noch_wikidata(self, db_session):
        p = company_profile_factory(db_session, sync_status="pending")
        db_session.commit()

        async def fake_search_one(client, name):
            return None

        with patch.object(sync_company, "_wikidata_search_one", new=fake_search_one), \
             patch.object(sync_company.asyncio, "sleep", new=AsyncMock()):
            await sync_company._run_sync_batch([p.id], 1)

        db_session.expire_all()
        assert p.sync_status == "done"
        assert p.sync_source == "wikidata"
        assert p.sync_error == "Kein Wikidata-Treffer gefunden"


class TestRunSyncBatchSparqlFehler:
    async def test_negativ_sparql_batch_fehler_setzt_failed(self, db_session):
        p = company_profile_factory(db_session, sync_status="pending")
        db_session.commit()

        async def fake_search_one(client, name):
            return ("Q1", "Testfirma")

        with patch.object(sync_company, "_wikidata_search_one", new=fake_search_one), \
             patch.object(sync_company, "_wikidata_sparql_batch",
                          new=AsyncMock(side_effect=RuntimeError("SPARQL down"))), \
             patch.object(sync_company.asyncio, "sleep", new=AsyncMock()):
            await sync_company._run_sync_batch([p.id], 1)

        db_session.expire_all()
        assert p.sync_status == "failed"
        assert "SPARQL" in p.sync_error


class TestRunSyncBatchLinkedinFehler:
    async def test_negativ_browser_start_fehlschlag_faellt_auf_wikidata_zurueck(self, db_session):
        p = company_profile_factory(db_session, sync_status="pending")
        db_session.commit()

        async def fake_get_context(user_id=None):
            raise RuntimeError("Browser-Crash")

        async def fake_search_one(client, name):
            return None

        with patch.object(sync_company, "_get_linkedin_context", new=fake_get_context), \
             patch.object(sync_company, "_wikidata_search_one", new=fake_search_one), \
             patch.object(sync_company.asyncio, "sleep", new=AsyncMock()):
            await sync_company._run_sync_batch([p.id], 1)

        db_session.expire_all()
        # Trotz gecrashtem Browser läuft der Wikidata-Fallback normal weiter.
        assert p.sync_status == "done"
        assert p.sync_source == "wikidata"

    async def test_negativ_linkedin_suche_fehler_faellt_auf_wikidata_zurueck(self, db_session):
        p = company_profile_factory(db_session, sync_status="pending")
        db_session.commit()

        async def fake_get_context(user_id=None):
            return _fake_linkedin_context()

        async def fake_search_candidates(context, name, limit=5):
            raise RuntimeError("Layout-Änderung")

        async def fake_search_one(client, name):
            return None

        with patch.object(sync_company, "_get_linkedin_context", new=fake_get_context), \
             patch.object(sync_company, "_linkedin_search_candidates", new=fake_search_candidates), \
             patch.object(sync_company, "_wikidata_search_one", new=fake_search_one), \
             patch.object(sync_company.asyncio, "sleep", new=AsyncMock()):
            await sync_company._run_sync_batch([p.id], 1)

        db_session.expire_all()
        assert p.sync_status == "done"
        assert p.sync_source == "wikidata"

    async def test_negativ_linkedin_scrape_fehler_faellt_auf_wikidata_zurueck(self, db_session):
        p = company_profile_factory(db_session, sync_status="pending")
        db_session.commit()

        async def fake_get_context(user_id=None):
            return _fake_linkedin_context()

        async def fake_search_candidates(context, name, limit=5):
            return [{"name": "Contoso GmbH", "url": "https://www.linkedin.com/company/contoso"}]

        async def fake_scrape_about(context, url):
            raise RuntimeError("Timeout")

        async def fake_search_one(client, name):
            return None

        with patch.object(sync_company, "_get_linkedin_context", new=fake_get_context), \
             patch.object(sync_company, "_linkedin_search_candidates", new=fake_search_candidates), \
             patch.object(sync_company, "_linkedin_scrape_about", new=fake_scrape_about), \
             patch.object(sync_company, "_wikidata_search_one", new=fake_search_one), \
             patch.object(sync_company.asyncio, "sleep", new=AsyncMock()):
            await sync_company._run_sync_batch([p.id], 1)

        db_session.expire_all()
        assert p.sync_status == "done"
        assert p.sync_source == "wikidata"

    async def test_negativ_leerer_scrape_faellt_auf_wikidata_zurueck(self, db_session):
        # Genau 1 LinkedIn-Treffer, aber Scrape liefert ein leeres Dict (kein
        # Fehler, aber auch keine Daten) — muss trotzdem in den
        # Wikidata-Fallback laufen statt fälschlich als LinkedIn-Erfolg zu gelten.
        p = company_profile_factory(db_session, sync_status="pending")
        db_session.commit()

        async def fake_get_context(user_id=None):
            return _fake_linkedin_context()

        async def fake_search_candidates(context, name, limit=5):
            return [{"name": "Contoso GmbH", "url": "https://www.linkedin.com/company/contoso"}]

        async def fake_scrape_about(context, url):
            return {}

        async def fake_search_one(client, name):
            return None

        with patch.object(sync_company, "_get_linkedin_context", new=fake_get_context), \
             patch.object(sync_company, "_linkedin_search_candidates", new=fake_search_candidates), \
             patch.object(sync_company, "_linkedin_scrape_about", new=fake_scrape_about), \
             patch.object(sync_company, "_wikidata_search_one", new=fake_search_one), \
             patch.object(sync_company.asyncio, "sleep", new=AsyncMock()):
            await sync_company._run_sync_batch([p.id], 1)

        db_session.expire_all()
        assert p.sync_status == "done"
        assert p.sync_source == "wikidata"
        assert p.sync_error == "Kein LinkedIn-/Wikidata-Treffer gefunden"

    async def test_positiv_linkedin_erfolg_nutzt_clearbit_logo_fallback(self, db_session):
        p = company_profile_factory(db_session, sync_status="pending", logo_data=None)
        db_session.commit()

        async def fake_get_context(user_id=None):
            return _fake_linkedin_context()

        async def fake_search_candidates(context, name, limit=5):
            return [{"name": "Contoso GmbH", "url": "https://www.linkedin.com/company/contoso"}]

        async def fake_scrape_about(context, url):
            return {"industry": "IT", "linkedin_company_url": url}

        with patch.object(sync_company, "_get_linkedin_context", new=fake_get_context), \
             patch.object(sync_company, "_linkedin_search_candidates", new=fake_search_candidates), \
             patch.object(sync_company, "_linkedin_scrape_about", new=fake_scrape_about), \
             patch.object(sync_company, "_fetch_logo_with_clearbit_fallback",
                          new=AsyncMock(return_value="data:image/png;base64,CLEARBIT")), \
             patch.object(sync_company.asyncio, "sleep", new=AsyncMock()):
            await sync_company._run_sync_batch([p.id], 1)

        db_session.expire_all()
        assert p.sync_status == "done"
        assert p.sync_source == "linkedin"
        assert p.logo_data == "data:image/png;base64,CLEARBIT"


class TestRunSyncBatchGeloeschtesProfil:
    async def test_corner_case_profil_zwischen_abruf_und_verarbeitung_geloescht(self, db_session):
        # profile_ids enthält eine id, die es in der DB gar nicht (mehr) gibt —
        # darf in keiner Phase crashen, sondern wird überall übersprungen.
        p = company_profile_factory(db_session, sync_status="pending")
        db_session.commit()
        ghost_id = p.id + 999

        async def fake_search_one(client, name):
            return None

        with patch.object(sync_company, "_wikidata_search_one", new=fake_search_one), \
             patch.object(sync_company.asyncio, "sleep", new=AsyncMock()):
            await sync_company._run_sync_batch([p.id, ghost_id], 1)

        db_session.expire_all()
        assert p.sync_status == "done"

    async def test_corner_case_ghost_profil_in_linkedin_phase_wird_uebersprungen(self, db_session):
        # Dieselbe Lücke wie oben, aber mit konfigurierter LinkedIn-Session, so
        # dass die Ghost-ID durch die LinkedIn-Schleife läuft (statt direkt in
        # den Wikidata-Fallback durchgereicht zu werden).
        p = company_profile_factory(db_session, sync_status="pending")
        db_session.commit()
        ghost_id = p.id + 999

        async def fake_get_context(user_id=None):
            return _fake_linkedin_context()

        async def fake_search_candidates(context, name, limit=5):
            return []

        async def fake_search_one(client, name):
            return None

        with patch.object(sync_company, "_get_linkedin_context", new=fake_get_context), \
             patch.object(sync_company, "_linkedin_search_candidates", new=fake_search_candidates), \
             patch.object(sync_company, "_wikidata_search_one", new=fake_search_one), \
             patch.object(sync_company.asyncio, "sleep", new=AsyncMock()):
            await sync_company._run_sync_batch([ghost_id, p.id], 1)

        db_session.expire_all()
        assert p.sync_status == "done"

    async def test_corner_case_profil_waehrend_wikidata_suche_geloescht(self, db_session):
        # Simuliert eine parallele Löschung genau in dem Await-Fenster
        # zwischen Wikidata-Treffer und der Schreibphase — das Profil ist
        # bereits als "attempted" erfasst, existiert aber beim finalen
        # db.query(...).get(pid) in Phase 5 nicht mehr.
        p = company_profile_factory(db_session, sync_status="pending")
        db_session.commit()
        pid = p.id

        async def fake_search_one(client, name):
            other = SessionLocal()
            other.query(models.CompanyProfile).filter_by(id=pid).delete()
            other.commit()
            other.close()
            return ("Q1", "Testfirma")

        async def fake_sparql_batch(qids):
            return {"Q1": {"industry": "IT"}}

        with patch.object(sync_company, "_wikidata_search_one", new=fake_search_one), \
             patch.object(sync_company, "_wikidata_sparql_batch", new=fake_sparql_batch), \
             patch.object(sync_company.asyncio, "sleep", new=AsyncMock()):
            await sync_company._run_sync_batch([pid], 1)

        db_session.expire_all()
        assert db_session.query(models.CompanyProfile).filter_by(id=pid).first() is None


class TestRunSyncBatchLogoTaskFehler:
    async def test_corner_case_logo_download_fehler_wird_ignoriert(self, db_session):
        # Phase 4 lädt Logos parallel per asyncio.gather(return_exceptions=True)
        # — schlägt ein einzelner Download fehl, darf das den restlichen
        # Wikidata-Erfolg (Phase 5) nicht verhindern.
        p = company_profile_factory(db_session, sync_status="pending", logo_data=None)
        db_session.commit()

        async def fake_search_one(client, name):
            return ("Q1", "Testfirma")

        async def fake_sparql_batch(qids):
            return {"Q1": {"industry": "IT", "logo_url": "http://wiki.example/logo.svg"}}

        with patch.object(sync_company, "_wikidata_search_one", new=fake_search_one), \
             patch.object(sync_company, "_wikidata_sparql_batch", new=fake_sparql_batch), \
             patch.object(sync_company, "_fetch_logo", new=AsyncMock(side_effect=RuntimeError("Download-Fehler"))), \
             patch.object(sync_company, "_fetch_logo_with_clearbit_fallback", new=AsyncMock(return_value=None)), \
             patch.object(sync_company.asyncio, "sleep", new=AsyncMock()):
            await sync_company._run_sync_batch([p.id], 1)

        db_session.expire_all()
        assert p.sync_status == "done"
        assert p.industry == "IT"
        assert p.logo_data is None


class TestRunSyncBatchUnerwarteterFehler:
    async def test_negativ_unerwarteter_fehler_wird_geloggt_und_lock_freigegeben(self, db_session):
        with patch.object(sync_company, "SessionLocal", side_effect=RuntimeError("DB weg")):
            await sync_company._run_sync_batch([1], 1)

        assert sync_company._SYNC_RUNNING is False
        assert sync_company._SYNC_CANCEL is False
        assert sync_company._CURRENT_COMPANY is None
