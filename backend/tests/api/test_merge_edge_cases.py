"""L2 API — /api/merge/*: Gefährliche Edge Cases.

Risk: merge_applications() hat keine explizite Prüfung, ob winner_id in
loser_ids enthalten ist — die lebt vom zufälligen Schutz durch dict-
Deduplizierung. Bei merge_contacts() und merge_companies() exakt dasselbe
Muster.
"""
import pytest

from app import models
from tests.factories import application_factory, contact_factory, company_profile_factory

pytestmark = pytest.mark.api


class TestMergeApplicationsEdgeCases:
    def test_negativ_winner_in_loser_ids_gibt_400(self, client, db_session):
        """Winner in loser_ids → explizite Prüfung gibt 400.
        Regression: vor dem Fix gab es 404 (len(all_ids) != len(apps) wegen Duplikaten)
        oder, bei loser_ids=[winner_id], Datenverlust durch Delete des Winners."""
        a1 = application_factory(db_session, firma="Contoso AG", rolle="Engineer")
        a2 = application_factory(db_session, firma="Contoso AG", rolle="Engineer")
        db_session.commit()

        resp = client.post("/api/merge/applications", json={
            "winner_id": a1.id,
            "loser_ids": [a2.id, a1.id],
            "field_overrides": {},
        })

        assert resp.status_code == 400
        assert db_session.get(models.Application, a1.id) is not None
        assert db_session.get(models.Application, a2.id) is not None

    def test_negativ_leere_loser_ids_ergibt_400(self, client, db_session):
        app = application_factory(db_session)
        db_session.commit()

        resp = client.post("/api/merge/applications", json={
            "winner_id": app.id, "loser_ids": [], "field_overrides": {},
        })

        assert resp.status_code == 400

    def test_negativ_nur_winner_in_loser_ids_gibt_400(self, client, db_session):
        a1 = application_factory(db_session)
        db_session.commit()

        resp = client.post("/api/merge/applications", json={
            "winner_id": a1.id,
            "loser_ids": [a1.id],
            "field_overrides": {},
        })

        assert resp.status_code == 400
        assert db_session.get(models.Application, a1.id) is not None

    def test_negativ_nicht_existente_ids_geben_404(self, client, db_session):
        resp = client.post("/api/merge/applications", json={
            "winner_id": 99999, "loser_ids": [99998], "field_overrides": {},
        })
        assert resp.status_code == 404


class TestMergeContactsEdgeCases:
    def test_negativ_winner_in_loser_ids_gibt_400(self, client, db_session):
        c1 = contact_factory(db_session)
        c2 = contact_factory(db_session)
        db_session.commit()

        resp = client.post("/api/merge/contacts", json={
            "winner_id": c1.id,
            "loser_ids": [c2.id, c1.id],
            "field_overrides": {},
        })

        assert resp.status_code == 400
        assert db_session.get(models.Contact, c1.id) is not None
        assert db_session.get(models.Contact, c2.id) is not None

    def test_negativ_leere_loser_ids(self, client, db_session):
        c = contact_factory(db_session)
        db_session.commit()
        resp = client.post("/api/merge/contacts", json={
            "winner_id": c.id, "loser_ids": [], "field_overrides": {},
        })
        assert resp.status_code == 400


class TestMergeCompaniesEdgeCases:
    def test_negativ_winner_in_loser_ids_gibt_400(self, client, db_session):
        cp1 = company_profile_factory(db_session)
        cp2 = company_profile_factory(db_session)
        db_session.commit()

        resp = client.post("/api/merge/companies", json={
            "winner_id": cp1.id,
            "loser_ids": [cp2.id, cp1.id],
            "field_overrides": {},
        })

        assert resp.status_code == 400
        assert db_session.get(models.CompanyProfile, cp1.id) is not None
        assert db_session.get(models.CompanyProfile, cp2.id) is not None

    def test_negativ_leere_loser_ids(self, client, db_session):
        cp = company_profile_factory(db_session)
        db_session.commit()
        resp = client.post("/api/merge/companies", json={
            "winner_id": cp.id, "loser_ids": [], "field_overrides": {},
        })
        assert resp.status_code == 400
