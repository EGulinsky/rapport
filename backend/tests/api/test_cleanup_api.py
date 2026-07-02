"""L2 API — /api/cleanup/preview und /api/cleanup/run inkl. scope-Filterung."""
import pytest

from tests.factories import application_factory, company_profile_factory, contact_factory, event_factory
from app import models

pytestmark = pytest.mark.api


class TestCleanupPreview:
    def test_positiv_ohne_scope_liefert_alle_kategorien(self, client, db_session):
        application_factory(db_session, firma="Contoso AG", rolle="Engineer")
        application_factory(db_session, firma="Contoso AG", rolle="Engineer")
        db_session.commit()

        resp = client.get("/api/cleanup/preview")

        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) == {"applications", "contacts", "companies", "events", "cross_app_events"}
        assert len(body["applications"]) == 1

    def test_positiv_scope_applications_liefert_nur_applications(self, client, db_session):
        application_factory(db_session, firma="Contoso AG", rolle="Engineer")
        application_factory(db_session, firma="Contoso AG", rolle="Engineer")
        company_profile_factory(db_session, website="https://www.contoso.de/")
        company_profile_factory(db_session, website="https://www.contoso.de/")
        db_session.commit()

        resp = client.get("/api/cleanup/preview", params={"scope": "applications"})

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["applications"]) == 1
        assert body["companies"] == []
        assert body["contacts"] == []
        assert body["events"] == []

    def test_negativ_keine_duplikate_liefert_leere_listen(self, client, db_session):
        application_factory(db_session, firma="Contoso AG", rolle="Engineer")
        db_session.commit()

        resp = client.get("/api/cleanup/preview")

        assert resp.status_code == 200
        assert resp.json()["applications"] == []


class TestCleanupRun:
    def test_positiv_scope_applications_loescht_dublette_und_haengt_events_um(self, client, db_session):
        # keeper braucht genug "filled"-Bonusfelder, um den Score-Vergleich trotz
        # des Events auf der Dublette zu gewinnen (siehe _app_score in cleanup.py).
        keeper = application_factory(
            db_session, firma="Contoso AG", rolle="Engineer",
            quelle="LinkedIn", kommentar="voll", wurde_besetzt_von="y", zielfirma_bei_hh="z",
            gespraech_1="a", gespraech_2="b",
        )
        dup = application_factory(db_session, firma="Contoso AG", rolle="Engineer")
        ev = event_factory(db_session, dup, typ="notiz")
        db_session.commit()

        resp = client.post("/api/cleanup/run", params={"scope": "applications"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["deleted_applications"] == 1
        assert db_session.get(models.Application, dup.id) is None
        db_session.refresh(ev)
        assert ev.application_id == keeper.id

    def test_positiv_scope_companies_merged_direkt(self, client, db_session):
        company_profile_factory(db_session, website="https://www.contoso.de/", description="Ausführlich")
        loser = company_profile_factory(db_session, website="https://www.contoso.de/")
        db_session.commit()
        loser_id = loser.id

        resp = client.post("/api/cleanup/run", params={"scope": "companies"})

        assert resp.status_code == 200
        assert resp.json()["deleted_companies"] == 1
        assert db_session.get(models.CompanyProfile, loser_id) is None

    def test_positiv_scope_contacts_erzeugt_pending_match_statt_zu_loeschen(self, client, db_session):
        # Kontakt-Dubletten werden nicht automatisch gelöscht, sondern zur manuellen
        # Prüfung als PendingMatch vorgeschlagen (siehe cleanup.py Kommentar).
        cp = company_profile_factory(db_session)
        contact_factory(db_session, name="Max Mustermann", company_profile_id=cp.id)
        contact_factory(db_session, name="Max Mustermann", company_profile_id=cp.id)
        db_session.commit()

        resp = client.post("/api/cleanup/run", params={"scope": "contacts"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["contact_groups_queued"] == 1
        assert db_session.query(models.PendingMatch).filter_by(source="cleanup", event_type="duplicate_contact").count() == 1
        assert db_session.query(models.Contact).count() == 2  # nichts gelöscht

    def test_negativ_scope_ohne_duplikate_aendert_nichts(self, client, db_session):
        application_factory(db_session, firma="Contoso AG", rolle="Engineer")
        db_session.commit()

        resp = client.post("/api/cleanup/run", params={"scope": "applications"})

        assert resp.status_code == 200
        assert resp.json()["deleted_applications"] == 0

    def test_corner_case_wiederholter_lauf_erzeugt_keine_doppelten_pending_matches(self, client, db_session):
        cp = company_profile_factory(db_session)
        contact_factory(db_session, name="Max Mustermann", company_profile_id=cp.id)
        contact_factory(db_session, name="Max Mustermann", company_profile_id=cp.id)
        db_session.commit()

        client.post("/api/cleanup/run", params={"scope": "contacts"})
        client.post("/api/cleanup/run", params={"scope": "contacts"})

        assert db_session.query(models.PendingMatch).filter_by(source="cleanup").count() == 1
