"""L2 API — /api/analytics/summary: Tenant-Scoping-Risiko.

Risk: analytics_summary() hat KEIN explizites user_id-Filter im Query
(db.query(Application).options(joinedload(company_profile)).all()).
Es verlässt sich vollständig auf with_loader_criteria. Wenn der Mechanismus
ausfällt (auth-Bug, Background-Task), würden ALLE Nutzerdaten einfließen.
"""
import pytest

from tests.factories import application_factory

pytestmark = pytest.mark.api


class TestAnalyticsTenantScoping:
    def test_positiv_nur_eigene_bewerbungen_zaehlen(self, client, db_session):
        application_factory(db_session, firma="Meine Firma", main_status="applied", user_id=1)
        application_factory(db_session, firma="Fremde Firma", main_status="applied", user_id=2)
        db_session.commit()

        resp = client.get("/api/analytics/summary")

        assert resp.status_code == 200
        kpis = resp.json()["kpis"]
        assert kpis["total"] == 1

    def test_positiv_andere_nutzer_werden_ignoriert(self, client, db_session):
        application_factory(db_session, firma="Meine Firma", main_status="applied", user_id=1)
        application_factory(db_session, firma="Fremde", main_status="hr", user_id=1)
        application_factory(db_session, firma="Noch Fremder", main_status="rejected", user_id=2)
        application_factory(db_session, firma="Ganz Fremd", main_status="signed", user_id=3)
        db_session.commit()

        resp = client.get("/api/analytics/summary")

        assert resp.status_code == 200
        kpis = resp.json()["kpis"]
        assert kpis["total"] == 2  # nur user_id=1
        assert kpis["active"] == 2  # applied + hr, rejected zählt nicht = beide aktiv

    def test_corner_case_keine_bewerbungen_liefert_leere_kpis(self, client):
        resp = client.get("/api/analytics/summary")

        assert resp.status_code == 200
        kpis = resp.json()["kpis"]
        assert kpis["total"] == 0
        assert all(kpis[k] == 0.0 for k in ("ghosting_rate", "hh_pct", "conversion_gespräch", "conversion_offer"))

    def test_positiv_funnel_zaehlt_nur_eigene(self, client, db_session):
        application_factory(db_session, main_status="applied", user_id=1)
        application_factory(db_session, main_status="hr", user_id=1)
        application_factory(db_session, main_status="applied", user_id=2)
        db_session.commit()

        resp = client.get("/api/analytics/summary")

        funnel = resp.json()["funnel"]
        # Beide user-1-Apps erreichten mindestens "applied" (eine ist applied, eine hr)
        applied_entry = next(f for f in funnel if f["status"] == "applied")
        assert applied_entry["count"] == 2
