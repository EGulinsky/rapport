"""L2 API — /api/merge/*: Applications/Contacts/Companies zusammenführen.

Bisher komplett ungetestet, obwohl die Endpoints destruktiv sind (löschen die
Verlierer-Entitäten dauerhaft) und Reassignment-Logik für Events/Kontakte/
Bewerbungen enthalten.
"""
import pytest

from tests.factories import application_factory, contact_factory, company_profile_factory, event_factory
from app import models

pytestmark = pytest.mark.api


class TestMergeApplications:
    def test_positiv_events_und_kontakte_werden_auf_gewinner_umgehaengt(self, client, db_session):
        winner = application_factory(db_session, firma="Contoso AG", rolle="Engineer")
        loser = application_factory(db_session, firma="Contoso AG", rolle="Engineer")
        ev = event_factory(db_session, loser, typ="notiz", notiz="Telefonat")
        contact = contact_factory(db_session)
        loser.contacts.append(contact)
        db_session.commit()

        resp = client.post("/api/merge/applications", json={
            "winner_id": winner.id, "loser_ids": [loser.id], "field_overrides": {},
        })

        assert resp.status_code == 200
        assert resp.json() == {"success": True, "winner_id": winner.id}
        db_session.refresh(winner)
        # Bewusst per db_session.refresh() statt des In-Memory-Attributs geprüft:
        # ein gecachter Python-Wert würde eine ORM-Kaskade, die das Event beim
        # Löschen der Dublette mitreißt, nicht aufdecken (live-verifizierter Bug).
        db_session.refresh(ev)
        assert ev.application_id == winner.id
        assert contact in winner.contacts
        assert db_session.get(models.Application, loser.id) is None

    def test_positiv_field_override_uebernimmt_wert_vom_verlierer(self, client, db_session):
        winner = application_factory(db_session, firma="Contoso AG", kommentar="alt")
        loser = application_factory(db_session, firma="Contoso AG", kommentar="besserer Kommentar")
        db_session.commit()

        resp = client.post("/api/merge/applications", json={
            "winner_id": winner.id, "loser_ids": [loser.id],
            "field_overrides": {"kommentar": loser.id},
        })

        assert resp.status_code == 200
        db_session.refresh(winner)
        assert winner.kommentar == "besserer Kommentar"

    def test_positiv_bereits_verknuepfter_kontakt_wird_nicht_dupliziert(self, client, db_session):
        winner = application_factory(db_session)
        loser = application_factory(db_session)
        contact = contact_factory(db_session)
        winner.contacts.append(contact)
        loser.contacts.append(contact)
        db_session.commit()

        resp = client.post("/api/merge/applications", json={
            "winner_id": winner.id, "loser_ids": [loser.id], "field_overrides": {},
        })

        assert resp.status_code == 200
        db_session.refresh(winner)
        assert winner.contacts.count(contact) == 1

    def test_positiv_merge_alias_wird_fuer_zukuenftige_syncs_angelegt(self, client, db_session):
        winner = application_factory(db_session, firma="Contoso AG")
        loser = application_factory(db_session, firma="Contoso Old GmbH", rolle="Alter Titel")
        db_session.commit()

        client.post("/api/merge/applications", json={
            "winner_id": winner.id, "loser_ids": [loser.id], "field_overrides": {},
        })

        alias = db_session.query(models.MergeAlias).filter_by(entity_type="application").first()
        assert alias is not None
        assert alias.canonical_id == winner.id
        assert alias.alias_firma == "Contoso Old GmbH"

    def test_negativ_leere_loser_ids_liefert_400(self, client, db_session):
        winner = application_factory(db_session)
        db_session.commit()

        resp = client.post("/api/merge/applications", json={
            "winner_id": winner.id, "loser_ids": [], "field_overrides": {},
        })

        assert resp.status_code == 400

    def test_negativ_nicht_existierende_id_liefert_404(self, client, db_session):
        winner = application_factory(db_session)
        db_session.commit()

        resp = client.post("/api/merge/applications", json={
            "winner_id": winner.id, "loser_ids": [999999], "field_overrides": {},
        })

        assert resp.status_code == 404
        assert resp.json()["detail"]["error_key"] == "merge.applications_not_found"

    def test_corner_case_status_wechsel_beim_merge_wird_auditiert(self, client, db_session):
        winner = application_factory(db_session, main_status="applied")
        loser = application_factory(db_session, main_status="hr")
        db_session.commit()

        client.post("/api/merge/applications", json={
            "winner_id": winner.id, "loser_ids": [loser.id],
            "field_overrides": {"main_status": loser.id},
        })

        db_session.refresh(winner)
        assert winner.main_status == "hr"
        audit = db_session.query(models.AuditLog).filter_by(app_id=winner.id, action="status_change").first()
        assert audit is not None


class TestMergeCompanies:
    def test_positiv_bewerbungen_und_kontakte_werden_umgehaengt(self, client, db_session):
        winner = company_profile_factory(db_session, name_display="Contoso AG")
        loser = company_profile_factory(db_session, name_display="Contoso Old AG")
        app = application_factory(db_session, company_profile_id=loser.id, firma="Contoso Old AG")
        contact = contact_factory(db_session, company_profile_id=loser.id, firma="Contoso Old AG")
        db_session.commit()

        resp = client.post("/api/merge/companies", json={
            "winner_id": winner.id, "loser_ids": [loser.id], "field_overrides": {},
        })

        assert resp.status_code == 200
        db_session.refresh(app)
        db_session.refresh(contact)
        assert app.company_profile_id == winner.id
        assert app.firma == "Contoso AG"
        assert contact.company_profile_id == winner.id
        assert db_session.get(models.CompanyProfile, loser.id) is None

    def test_positiv_headhunter_zielfirma_wird_umgehaengt(self, client, db_session):
        winner = company_profile_factory(db_session, name_display="Contoso AG")
        loser = company_profile_factory(db_session, name_display="Contoso Old AG")
        hh_app = application_factory(
            db_session, is_headhunter=True, target_company_profile_id=loser.id, zielfirma_bei_hh="Contoso Old AG",
        )
        db_session.commit()

        client.post("/api/merge/companies", json={
            "winner_id": winner.id, "loser_ids": [loser.id], "field_overrides": {},
        })

        db_session.refresh(hh_app)
        assert hh_app.target_company_profile_id == winner.id
        assert hh_app.zielfirma_bei_hh == "Contoso AG"

    def test_negativ_leere_loser_ids_liefert_400(self, client, db_session):
        winner = company_profile_factory(db_session)
        db_session.commit()

        resp = client.post("/api/merge/companies", json={
            "winner_id": winner.id, "loser_ids": [], "field_overrides": {},
        })

        assert resp.status_code == 400

    def test_negativ_nicht_existierende_id_liefert_404(self, client, db_session):
        winner = company_profile_factory(db_session)
        db_session.commit()

        resp = client.post("/api/merge/companies", json={
            "winner_id": winner.id, "loser_ids": [999999], "field_overrides": {},
        })

        assert resp.status_code == 404
        assert resp.json()["detail"]["error_key"] == "merge.companies_not_found"


class TestMergeContacts:
    def test_positiv_bewerbungsverknuepfungen_werden_dedupliziert_zusammengefuehrt(self, client, db_session):
        winner = contact_factory(db_session, name="Max Mustermann")
        loser = contact_factory(db_session, name="Max Mustermann")
        app_a = application_factory(db_session)
        app_b = application_factory(db_session)
        winner.applications.append(app_a)
        loser.applications.append(app_a)   # bereits bei beiden verknüpft — darf nicht doppelt landen
        loser.applications.append(app_b)
        db_session.commit()

        resp = client.post("/api/merge/contacts", json={
            "winner_id": winner.id, "loser_ids": [loser.id], "field_overrides": {},
        })

        assert resp.status_code == 200
        db_session.refresh(winner)
        assert winner.applications.count(app_a) == 1
        assert app_b in winner.applications
        assert db_session.get(models.Contact, loser.id) is None

    def test_positiv_merge_alias_wird_angelegt(self, client, db_session):
        winner = contact_factory(db_session, name="Max Mustermann", email="max@contoso.de")
        loser = contact_factory(db_session, name="M. Mustermann", email="m.mustermann@contoso.de")
        db_session.commit()

        client.post("/api/merge/contacts", json={
            "winner_id": winner.id, "loser_ids": [loser.id], "field_overrides": {},
        })

        alias = db_session.query(models.MergeAlias).filter_by(entity_type="contact").first()
        assert alias is not None
        assert alias.canonical_id == winner.id
        assert alias.alias_email == "m.mustermann@contoso.de"

    def test_negativ_leere_loser_ids_liefert_400(self, client, db_session):
        winner = contact_factory(db_session)
        db_session.commit()

        resp = client.post("/api/merge/contacts", json={
            "winner_id": winner.id, "loser_ids": [], "field_overrides": {},
        })

        assert resp.status_code == 400

    def test_negativ_nicht_existierende_id_liefert_404(self, client, db_session):
        winner = contact_factory(db_session)
        db_session.commit()

        resp = client.post("/api/merge/contacts", json={
            "winner_id": winner.id, "loser_ids": [999999], "field_overrides": {},
        })

        assert resp.status_code == 404
        assert resp.json()["detail"]["error_key"] == "merge.contacts_not_found"
