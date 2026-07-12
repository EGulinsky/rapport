"""L2 API — HTTP-Endpunkte in companies.py.

Deckt CRUD für Firmenprofile, Eltern-Kind-Hierarchie (inkl. Zyklus-Schutz),
Logo-Upload, Kontakt-Zuordnung und die Hintergrund-Kontaktverknüpfung ab.
"""
import pytest

from app import models
from app.dedup import norm_firma
from tests.factories import application_factory, company_profile_factory, contact_factory

pytestmark = pytest.mark.api


def _make_verbose(db):
    db.add(models.SyncSettings(user_id=1, audit_log_level="verbose"))
    db.commit()


class TestCreateCompany:
    def test_positiv_legt_neues_profil_an(self, client, db_session):
        resp = client.post("/api/companies", json={"name": "Contoso AG"})

        assert resp.status_code == 201
        body = resp.json()
        assert body["name_display"] == "Contoso AG"
        assert body["sync_status"] == "pending"
        assert db_session.query(models.CompanyProfile).count() == 1

    def test_negativ_leerer_name_liefert_400(self, client):
        resp = client.post("/api/companies", json={"name": "   "})
        assert resp.status_code == 400

    def test_positiv_existierender_normalisierter_name_liefert_bestehendes_profil(self, client, db_session):
        company_profile_factory(db_session, name_display="Contoso AG", name_norm=norm_firma("Contoso AG"))
        db_session.commit()

        resp = client.post("/api/companies", json={"name": "Contoso AG"})

        assert resp.status_code == 201
        assert db_session.query(models.CompanyProfile).filter_by(name_norm=norm_firma("Contoso AG")).count() == 1


class TestListCompanies:
    def test_positiv_liefert_alle_profile(self, client, db_session):
        company_profile_factory(db_session, name_display="Contoso AG")
        company_profile_factory(db_session, name_display="Globex AG")
        db_session.commit()

        resp = client.get("/api/companies")

        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_positiv_suche_filtert_nach_namen(self, client, db_session):
        company_profile_factory(db_session, name_display="Contoso AG")
        company_profile_factory(db_session, name_display="Globex AG")
        db_session.commit()

        resp = client.get("/api/companies", params={"search": "contoso"})

        assert len(resp.json()) == 1
        assert resp.json()[0]["name_display"] == "Contoso AG"

    def test_positiv_suche_filtert_nach_branche_und_stadt(self, client, db_session):
        company_profile_factory(db_session, name_display="A", industry="Software", hq_city="Berlin")
        company_profile_factory(db_session, name_display="B", industry="Finance", hq_city="München")
        db_session.commit()

        resp = client.get("/api/companies", params={"search": "berlin"})
        assert len(resp.json()) == 1
        assert resp.json()[0]["name_display"] == "A"

    def test_positiv_sortierung_nach_industry_absteigend(self, client, db_session):
        company_profile_factory(db_session, name_display="A", industry="Software")
        company_profile_factory(db_session, name_display="B", industry="Zoo")
        db_session.commit()

        resp = client.get("/api/companies", params={"sort": "industry", "order": "desc"})

        assert resp.json()[0]["name_display"] == "B"

    def test_positiv_sortierung_nach_apps_und_sync_status(self, client, db_session):
        company_profile_factory(db_session, name_display="A", sync_status="done")
        company_profile_factory(db_session, name_display="B", sync_status="pending")
        db_session.commit()

        resp_apps = client.get("/api/companies", params={"sort": "apps"})
        assert resp_apps.status_code == 200
        resp_status = client.get("/api/companies", params={"sort": "sync_status"})
        assert resp_status.status_code == 200

    def test_positiv_parent_name_wird_aufgeloest(self, client, db_session):
        parent = company_profile_factory(db_session, name_display="Muttergesellschaft")
        company_profile_factory(db_session, name_display="Tochter", parent_company_id=parent.id)
        db_session.commit()

        resp = client.get("/api/companies")

        child = next(c for c in resp.json() if c["name_display"] == "Tochter")
        assert child["parent_name"] == "Muttergesellschaft"


class TestGetCompany:
    def test_negativ_nicht_gefunden_liefert_404(self, client):
        resp = client.get("/api/companies/999")
        assert resp.status_code == 404
        assert resp.json()["detail"]["error_key"] == "company.not_found"

    def test_positiv_liefert_details_mit_apps_und_kontakten(self, client, db_session):
        profile = company_profile_factory(db_session, name_display="Contoso AG")
        app = application_factory(db_session, firma="Contoso AG", company_profile_id=profile.id)
        contact = contact_factory(db_session, name="Jane Doe")
        app.contacts.append(contact)
        db_session.commit()

        resp = client.get(f"/api/companies/{profile.id}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["app_count"] == 1
        assert body["contact_count"] == 1
        assert body["applications"][0]["firma"] == "Contoso AG"
        assert body["contacts"][0]["name"] == "Jane Doe"

    def test_positiv_zeigt_subsidiaries(self, client, db_session):
        parent = company_profile_factory(db_session, name_display="Mutter")
        company_profile_factory(db_session, name_display="Tochter", parent_company_id=parent.id)
        db_session.commit()

        resp = client.get(f"/api/companies/{parent.id}")

        assert len(resp.json()["subsidiaries"]) == 1
        assert resp.json()["subsidiaries"][0]["name_display"] == "Tochter"


class TestUpdateCompany:
    def test_negativ_nicht_gefunden_liefert_404(self, client):
        resp = client.patch("/api/companies/999", json={"industry": "Software"})
        assert resp.status_code == 404
        assert resp.json()["detail"]["error_key"] == "company.not_found"

    def test_positiv_aktualisiert_felder_und_schreibt_audit(self, client, db_session):
        profile = company_profile_factory(db_session, name_display="Contoso AG", industry=None)
        _make_verbose(db_session)
        db_session.commit()

        resp = client.patch(f"/api/companies/{profile.id}", json={"industry": "Software"})

        assert resp.status_code == 200
        assert resp.json()["industry"] == "Software"
        audit = db_session.query(models.AuditLog).filter_by(company_profile_id=profile.id, field="industry").first()
        assert audit is not None

    def test_positiv_setzt_parent_company_id(self, client, db_session):
        parent = company_profile_factory(db_session, name_display="Mutter")
        child = company_profile_factory(db_session, name_display="Kind")
        db_session.commit()

        resp = client.patch(f"/api/companies/{child.id}", json={"parent_company_id": parent.id})

        assert resp.status_code == 200
        assert resp.json()["parent_company_id"] == parent.id

    def test_negativ_zyklische_hierarchie_wird_abgelehnt(self, client, db_session):
        a = company_profile_factory(db_session, name_display="A")
        b = company_profile_factory(db_session, name_display="B", parent_company_id=a.id)
        db_session.commit()

        resp = client.patch(f"/api/companies/{a.id}", json={"parent_company_id": b.id})

        assert resp.status_code == 400
        assert resp.json()["detail"]["error_key"] == "company.cyclic_hierarchy"


class TestLinkContacts:
    def test_positiv_status_wenn_nicht_laufend(self, client):
        resp = client.get("/api/companies/link-contacts/status")
        assert resp.status_code == 200
        assert resp.json()["running"] is False

    def test_positiv_cancel_setzt_flag(self, client):
        resp = client.post("/api/companies/link-contacts/cancel")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_positiv_startet_verknuepfung_und_verlinkt_kontakt(self, client, db_session):
        profile = company_profile_factory(db_session, name_display="Contoso AG", name_norm=norm_firma("Contoso AG"))
        contact = contact_factory(db_session, firma="Contoso AG", company_profile_id=None)
        db_session.commit()

        resp = client.post("/api/companies/link-contacts")

        assert resp.status_code == 200
        assert resp.json()["started"] is True
        db_session.refresh(contact)
        assert contact.company_profile_id == profile.id

    def test_positiv_scoped_run_erstellt_keine_neuen_profile(self, client, db_session):
        other_profile = company_profile_factory(db_session, name_display="Andere AG")
        contact_factory(db_session, firma="Unbekannte Firma GmbH", company_profile_id=None)
        db_session.commit()

        resp = client.post("/api/companies/link-contacts", params={"company_ids": [other_profile.id]})

        assert resp.status_code == 200
        assert db_session.query(models.CompanyProfile).count() == 1


class TestCompanyLogo:
    def test_positiv_upload_speichert_logo(self, client, db_session):
        profile = company_profile_factory(db_session)
        db_session.commit()

        resp = client.post(
            f"/api/companies/{profile.id}/logo",
            files={"file": ("logo.png", b"\x89PNG\r\n", "image/png")},
        )

        assert resp.status_code == 200
        db_session.refresh(profile)
        assert profile.logo_data.startswith("data:image/png;base64,")

    def test_negativ_upload_ohne_profil_liefert_404(self, client):
        resp = client.post(
            "/api/companies/999/logo",
            files={"file": ("logo.png", b"data", "image/png")},
        )
        assert resp.status_code == 404

    def test_positiv_delete_entfernt_logo(self, client, db_session):
        profile = company_profile_factory(db_session, logo_data="data:image/png;base64,xxx")
        db_session.commit()

        resp = client.delete(f"/api/companies/{profile.id}/logo")

        assert resp.status_code == 200
        db_session.refresh(profile)
        assert profile.logo_data is None

    def test_negativ_delete_ohne_profil_liefert_404(self, client):
        resp = client.delete("/api/companies/999/logo")
        assert resp.status_code == 404


class TestAssignContact:
    def test_positiv_weist_kontakt_zu(self, client, db_session):
        profile = company_profile_factory(db_session)
        contact = contact_factory(db_session, company_profile_id=None)
        db_session.commit()

        resp = client.post(f"/api/companies/{profile.id}/contacts/{contact.id}")

        assert resp.status_code == 200
        db_session.refresh(contact)
        assert contact.company_profile_id == profile.id

    def test_negativ_profil_nicht_gefunden(self, client, db_session):
        contact = contact_factory(db_session)
        db_session.commit()

        resp = client.post(f"/api/companies/999/contacts/{contact.id}")
        assert resp.status_code == 404
        assert resp.json()["detail"]["error_key"] == "company.not_found"

    def test_negativ_kontakt_nicht_gefunden(self, client, db_session):
        profile = company_profile_factory(db_session)
        db_session.commit()

        resp = client.post(f"/api/companies/{profile.id}/contacts/999")
        assert resp.status_code == 404
        assert resp.json()["detail"]["error_key"] == "contact.not_found"

    def test_positiv_unassign_entfernt_zuordnung(self, client, db_session):
        profile = company_profile_factory(db_session)
        contact = contact_factory(db_session, company_profile_id=profile.id)
        db_session.commit()

        resp = client.delete(f"/api/companies/{profile.id}/contacts/{contact.id}")

        assert resp.status_code == 200
        db_session.refresh(contact)
        assert contact.company_profile_id is None

    def test_negativ_unassign_kontakt_nicht_gefunden(self, client):
        resp = client.delete("/api/companies/1/contacts/999")
        assert resp.status_code == 404

    def test_corner_case_unassign_mit_falscher_firma_ist_no_op(self, client, db_session):
        profile_a = company_profile_factory(db_session)
        profile_b = company_profile_factory(db_session)
        contact = contact_factory(db_session, company_profile_id=profile_a.id)
        db_session.commit()

        resp = client.delete(f"/api/companies/{profile_b.id}/contacts/{contact.id}")

        assert resp.status_code == 200
        db_session.refresh(contact)
        assert contact.company_profile_id == profile_a.id


class TestBulkDeleteCompanies:
    def test_positiv_loescht_ausgewaehlte_profile(self, client, db_session):
        a = company_profile_factory(db_session)
        b = company_profile_factory(db_session)
        db_session.commit()

        resp = client.request("DELETE", "/api/companies/bulk", json={"ids": [a.id, b.id]})

        assert resp.status_code == 200
        assert resp.json()["deleted"] == 2
        assert db_session.query(models.CompanyProfile).count() == 0

    def test_corner_case_leere_id_liste_loescht_nichts(self, client, db_session):
        company_profile_factory(db_session)
        db_session.commit()

        resp = client.request("DELETE", "/api/companies/bulk", json={"ids": []})

        assert resp.json()["deleted"] == 0
        assert db_session.query(models.CompanyProfile).count() == 1
