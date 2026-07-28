"""L2 API — /api/contacts/: list, create, bulk-delete.

Deckt bislang ungetestete Pfade ab: GET / (inkl. Suche und dem in-memory
Anreichern von company_name_display/company_website aus verlinkten
CompanyProfiles), POST / (Anlage + Audit) und DELETE /bulk (gezielt und
per all=True), inkl. Mandanten-Scoping.
"""
import pytest

from app import models
from tests.factories import application_factory, company_profile_factory, contact_factory

pytestmark = pytest.mark.api


class TestListContacts:
    def test_positiv_liefert_alle_eigenen_kontakte(self, client, db_session):
        contact_factory(db_session, name="Anna Berg")
        contact_factory(db_session, name="Bruno Klein")
        db_session.commit()

        resp = client.get("/api/contacts/")

        assert resp.status_code == 200
        names = {c["name"] for c in resp.json()}
        assert names == {"Anna Berg", "Bruno Klein"}

    def test_positiv_andere_nutzer_werden_ignoriert(self, client, db_session):
        contact_factory(db_session, name="Meiner", user_id=1)
        contact_factory(db_session, name="Fremder", user_id=2)
        db_session.commit()

        resp = client.get("/api/contacts/")

        assert resp.status_code == 200
        names = {c["name"] for c in resp.json()}
        assert names == {"Meiner"}

    @pytest.mark.parametrize("term", ["Anna", "anna@", "Beispiel GmbH", "Recruiter"])
    def test_positiv_suche_filtert_ueber_mehrere_felder(self, client, db_session, term):
        contact_factory(
            db_session, name="Anna Berg", email="anna@example.com",
            firma="Beispiel GmbH", rolle="Recruiter",
        )
        contact_factory(db_session, name="Bruno Klein", email="bruno@other.de", firma="Andere AG", rolle="HR")
        db_session.commit()

        resp = client.get("/api/contacts/", params={"search": term})

        assert resp.status_code == 200
        names = {c["name"] for c in resp.json()}
        assert names == {"Anna Berg"}

    def test_positiv_suche_filtert_auch_ueber_vorname(self, client, db_session):
        # Regression: the search filter only checked name/email/firma/rolle,
        # never vorname — a contact stored as name="Berg", vorname="Anna"
        # (the common case since the vorname/name split) was invisible to a
        # search for "Anna" (live-reported).
        contact_factory(db_session, name="Berg", vorname="Anna")
        contact_factory(db_session, name="Klein", vorname="Bruno")
        db_session.commit()

        resp = client.get("/api/contacts/", params={"search": "Anna"})

        assert resp.status_code == 200
        names = {c["name"] for c in resp.json()}
        assert names == {"Berg"}

    def test_positiv_reichert_company_name_und_website_ueber_verlinkte_bewerbung_an(self, client, db_session):
        profile = company_profile_factory(db_session, name_display="Acme Corp", website="https://acme.example/")
        app_obj = application_factory(db_session, firma="Acme Corp", company_profile_id=profile.id)
        contact = contact_factory(db_session, name="Carla Fuchs")
        contact.applications.append(app_obj)
        db_session.commit()

        resp = client.get("/api/contacts/")

        assert resp.status_code == 200
        body = next(c for c in resp.json() if c["name"] == "Carla Fuchs")
        assert body["applications"][0]["company_name_display"] == "Acme Corp"
        assert body["company_website"] == "https://acme.example/"

    def test_corner_case_keine_kontakte_liefert_leere_liste(self, client):
        resp = client.get("/api/contacts/")

        assert resp.status_code == 200
        assert resp.json() == []


class TestListContactsCompanyProfileIdFilter:
    """Regressionsfall (analog zu Applications): der "N Kontakte"-Klick in
    der Firmenansicht filterte per Freitextsuche über Contact.firma statt
    über die tatsächliche FK-Verknüpfung. company_profile_id filtert
    stattdessen wie _collect_contacts() in companies.py: direkt verlinkte
    Kontakte (Contact.company_profile_id) plus Kontakte, die über eine
    verlinkte Bewerbung an dieselbe Firma hängen."""

    def test_positiv_findet_direkt_verlinkten_kontakt(self, client, db_session):
        profile = company_profile_factory(db_session, name_display="Rohde+Schwarz")
        contact_factory(db_session, name="Anna Berg", firma="Ganz anderer Text", company_profile_id=profile.id)
        db_session.commit()

        resp = client.get("/api/contacts/", params={"company_profile_id": profile.id})

        assert resp.status_code == 200
        assert [c["name"] for c in resp.json()] == ["Anna Berg"]

    def test_positiv_findet_kontakt_ueber_verlinkte_bewerbung_trotz_abweichender_firma(self, client, db_session):
        profile = company_profile_factory(db_session, name_display="Rohde+Schwarz")
        app_obj = application_factory(db_session, firma="Rohde und Schwarz GmbH & Co. KG", company_profile_id=profile.id)
        contact = contact_factory(db_session, name="Carla Fuchs", firma="Rohde und Schwarz GmbH & Co. KG")
        contact.applications.append(app_obj)
        db_session.commit()

        resp = client.get("/api/contacts/", params={"company_profile_id": profile.id})

        assert resp.status_code == 200
        assert [c["name"] for c in resp.json()] == ["Carla Fuchs"]

    def test_positiv_findet_kontakt_ueber_target_company_profile_id(self, client, db_session):
        profile = company_profile_factory(db_session, name_display="Contoso")
        app_obj = application_factory(
            db_session, firma="Headhunter XY", is_headhunter=True,
            zielfirma_bei_hh="Contoso Corp", target_company_profile_id=profile.id,
        )
        contact = contact_factory(db_session, name="Ben Weiss")
        contact.applications.append(app_obj)
        db_session.commit()

        resp = client.get("/api/contacts/", params={"company_profile_id": profile.id})

        assert resp.status_code == 200
        assert [c["name"] for c in resp.json()] == ["Ben Weiss"]

    def test_negativ_andere_firma_wird_nicht_zurueckgegeben(self, client, db_session):
        profile_a = company_profile_factory(db_session, name_display="Firma A")
        profile_b = company_profile_factory(db_session, name_display="Firma B")
        contact_factory(db_session, name="Kontakt A", company_profile_id=profile_a.id)
        contact_factory(db_session, name="Kontakt B", company_profile_id=profile_b.id)
        db_session.commit()

        resp = client.get("/api/contacts/", params={"company_profile_id": profile_a.id})

        assert resp.status_code == 200
        assert [c["name"] for c in resp.json()] == ["Kontakt A"]


class TestCreateContact:
    def test_positiv_legt_kontakt_an_und_schreibt_audit(self, client, db_session):
        resp = client.post("/api/contacts/", json={"name": "Dana Voss", "firma": "Beta GmbH"})

        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Dana Voss"
        assert body["firma"] == "Beta GmbH"

        created = db_session.query(models.Contact).filter_by(id=body["id"]).first()
        assert created is not None
        assert created.user_id == 1

        audit = db_session.query(models.AuditLog).filter_by(contact_id=created.id, action="create").first()
        assert audit is not None
        assert audit.new_value == "Dana Voss"

    def test_negativ_ohne_name_liefert_422(self, client):
        resp = client.post("/api/contacts/", json={"firma": "Beta GmbH"})

        assert resp.status_code == 422

    def test_positiv_legt_kontakt_mit_mehreren_telefonnummern_an(self, client, db_session):
        resp = client.post("/api/contacts/", json={
            "name": "Multi Nummer",
            "phones": [
                {"number": "+491701234567", "type": "mobile"},
                {"number": "+49301234567", "type": "work"},
            ],
        })

        assert resp.status_code == 201
        created = db_session.query(models.Contact).filter_by(id=resp.json()["id"]).first()
        assert {(p.number, p.type) for p in created.phones} == {
            ("+491701234567", "mobile"), ("+49301234567", "work"),
        }


class TestUpdateContact:
    def test_negativ_nicht_gefunden_liefert_404(self, client):
        resp = client.patch("/api/contacts/999999", json={"rolle": "CTO"})

        assert resp.status_code == 404
        assert resp.json()["detail"]["error_key"] == "contact.not_found"

    def test_positiv_phones_werden_vollstaendig_ersetzt(self, client, db_session):
        contact = contact_factory(db_session, telefon="+49111")
        db_session.commit()

        resp = client.patch(f"/api/contacts/{contact.id}", json={
            "phones": [{"number": "+49222", "type": "home"}, {"number": "+49333", "type": "work"}],
        })

        assert resp.status_code == 200
        db_session.refresh(contact)
        assert {(p.number, p.type) for p in contact.phones} == {("+49222", "home"), ("+49333", "work")}

    def test_positiv_phones_weglassen_laesst_bestehende_unangetastet(self, client, db_session):
        contact = contact_factory(db_session, telefon="+49111")
        db_session.commit()

        resp = client.patch(f"/api/contacts/{contact.id}", json={"rolle": "CTO"})

        assert resp.status_code == 200
        db_session.refresh(contact)
        assert [p.number for p in contact.phones] == ["+49111"]


class TestBulkDeleteContacts:
    def test_positiv_loescht_gezielt_ausgewaehlte(self, client, db_session):
        c1 = contact_factory(db_session, name="Löschen 1")
        c2 = contact_factory(db_session, name="Löschen 2")
        keep = contact_factory(db_session, name="Bleibt")
        db_session.commit()

        resp = client.request("DELETE", "/api/contacts/bulk", json={"ids": [c1.id, c2.id]})

        assert resp.status_code == 200
        assert resp.json() == {"deleted": 2}
        remaining = {c.name for c in db_session.query(models.Contact).all()}
        assert remaining == {"Bleibt"}
        assert db_session.get(models.Contact, keep.id) is not None

    def test_negativ_all_flag_wird_ignoriert_ohne_ids_wird_nichts_geloescht(self, client, db_session):
        # Regression: a client-supplied "all=true" used to bypass the id list
        # entirely and delete every contact on the account regardless of any
        # filter shown in the UI — caused real production data loss
        # (2026-07-10, 2026-07-21). The field no longer exists on the
        # endpoint's schema at all; a client still sending it must have zero
        # effect rather than silently reviving the old bypass.
        contact_factory(db_session, name="Eigener 1", user_id=1)
        contact_factory(db_session, name="Eigener 2", user_id=1)
        db_session.commit()

        resp = client.request("DELETE", "/api/contacts/bulk", json={"ids": [], "all": True})

        assert resp.status_code == 200
        assert resp.json() == {"deleted": 0}
        assert db_session.query(models.Contact).count() == 2

    def test_positiv_alle_eigenen_ids_explizit_loescht_nicht_fremde(self, client, db_session):
        own1 = contact_factory(db_session, name="Eigener 1", user_id=1)
        own2 = contact_factory(db_session, name="Eigener 2", user_id=1)
        contact_factory(db_session, name="Fremder", user_id=2)
        db_session.commit()

        resp = client.request("DELETE", "/api/contacts/bulk", json={"ids": [own1.id, own2.id, 99999]})

        assert resp.status_code == 200
        assert resp.json() == {"deleted": 2}
        db_session.info["current_user_id"] = None  # Request hat current_user_id=1 auf der Session hinterlassen
        remaining = [c.name for c in db_session.query(models.Contact).all()]
        assert remaining == ["Fremder"]

    def test_positiv_schreibt_audit_pro_geloeschtem_kontakt(self, client, db_session):
        c = contact_factory(db_session, name="Audit Mich")
        db_session.commit()

        resp = client.request("DELETE", "/api/contacts/bulk", json={"ids": [c.id]})

        assert resp.status_code == 200
        audit = db_session.query(models.AuditLog).filter_by(action="delete").first()
        assert audit is not None
        assert audit.old_value == "Audit Mich"

    def test_corner_case_leere_ids_ohne_all_loescht_nichts(self, client, db_session):
        contact_factory(db_session, name="Bleibt")
        db_session.commit()

        resp = client.request("DELETE", "/api/contacts/bulk", json={"ids": []})

        assert resp.status_code == 200
        assert resp.json() == {"deleted": 0}
        assert db_session.query(models.Contact).count() == 1

    def test_positiv_loescht_verknuepfungen_und_telefonnummern_mit(self, client, db_session):
        # Regression: q.delete(synchronize_session=False) is a bulk raw SQL
        # DELETE that bypasses SQLAlchemy's ORM-level relationship cascade —
        # it left contact_application/contact_phones rows behind for every
        # deleted contact. Harmless until SQLite later reused the freed id
        # for a brand-new contact (contacts.id has no AUTOINCREMENT), whose
        # own INSERT into contact_application then hit a UNIQUE-constraint
        # violation against the orphaned row and broke the whole batch sync.
        app_ = application_factory(db_session, firma="Contoso", rolle="Dev")
        c = contact_factory(db_session, name="Löschen", phones=[{"number": "+49111", "type": "mobile"}])
        c.applications.append(app_)
        db_session.commit()
        contact_id = c.id

        resp = client.request("DELETE", "/api/contacts/bulk", json={"ids": [contact_id]})

        assert resp.status_code == 200
        assert resp.json() == {"deleted": 1}
        from sqlalchemy import text
        links = db_session.execute(
            text("SELECT * FROM contact_application WHERE contact_id = :cid"), {"cid": contact_id}
        ).fetchall()
        phones = db_session.execute(
            text("SELECT * FROM contact_phones WHERE contact_id = :cid"), {"cid": contact_id}
        ).fetchall()
        assert links == []
        assert phones == []


class TestBulkUnlinkApplications:
    """DELETE /api/contacts/{id}/applications/bulk — mirror of applications.py's
    bulk_delete_contacts(), from the contact's side: removes only the link,
    never the application, and (unlike the app-side endpoint) never
    hard-deletes the contact even if this empties its application list."""

    def test_positiv_entfernt_gezielt_ausgewaehlte_verknuepfungen(self, client, db_session):
        c = contact_factory(db_session, name="Mehrfach Verlinkt")
        app1 = application_factory(db_session, firma="Contoso", rolle="Dev")
        app2 = application_factory(db_session, firma="Fabrikam", rolle="PM")
        app3 = application_factory(db_session, firma="Adatum", rolle="QA")
        c.applications.extend([app1, app2, app3])
        db_session.commit()

        resp = client.request("DELETE", f"/api/contacts/{c.id}/applications/bulk", json={"ids": [app1.id, app2.id]})

        assert resp.status_code == 200
        assert resp.json() == {"unlinked": 2}
        db_session.refresh(c)
        assert [a.id for a in c.applications] == [app3.id]

    def test_positiv_bewerbung_und_kontakt_bleiben_erhalten(self, client, db_session):
        # Explicit user requirement: only the link is removed — neither the
        # application nor the contact itself gets deleted, even if this
        # leaves the contact with zero remaining applications (unlike the
        # app-side bulk-delete-contacts endpoint, which hard-deletes an
        # orphaned contact — the wrong behavior here since the user is
        # editing this specific contact from its own modal).
        c = contact_factory(db_session, name="Wird Nicht Geloescht")
        app = application_factory(db_session, firma="Contoso", rolle="Dev")
        c.applications.append(app)
        db_session.commit()
        contact_id, app_id = c.id, app.id

        resp = client.request("DELETE", f"/api/contacts/{contact_id}/applications/bulk", json={"ids": [app_id]})

        assert resp.status_code == 200
        assert db_session.get(models.Contact, contact_id) is not None
        assert db_session.get(models.Application, app_id) is not None
        db_session.refresh(c)
        assert c.applications == []

    def test_negativ_unbekannter_kontakt_liefert_404(self, client, db_session):
        resp = client.request("DELETE", "/api/contacts/99999/applications/bulk", json={"ids": [1]})
        assert resp.status_code == 404

    def test_negativ_nicht_verlinkte_id_wird_ignoriert(self, client, db_session):
        c = contact_factory(db_session, name="Solo")
        app = application_factory(db_session, firma="Contoso", rolle="Dev")
        unrelated = application_factory(db_session, firma="Fabrikam", rolle="PM")
        c.applications.append(app)
        db_session.commit()

        resp = client.request("DELETE", f"/api/contacts/{c.id}/applications/bulk", json={"ids": [unrelated.id]})

        assert resp.status_code == 200
        assert resp.json() == {"unlinked": 0}
        db_session.refresh(c)
        assert [a.id for a in c.applications] == [app.id]

    def test_positiv_schreibt_audit_pro_entfernter_verknuepfung(self, client, db_session):
        # add_audit() only persists "update"-action entries in verbose mode
        # (normal mode is create/delete/status_change/merge/import only) —
        # same convention every other field-level audit call in this
        # codebase follows, so exercise it explicitly here.
        db_session.add(models.SyncSettings(user_id=1, audit_log_level="verbose"))
        c = contact_factory(db_session, name="Audit Mich")
        app = application_factory(db_session, firma="Contoso", rolle="Dev")
        c.applications.append(app)
        db_session.commit()

        resp = client.request("DELETE", f"/api/contacts/{c.id}/applications/bulk", json={"ids": [app.id]})

        assert resp.status_code == 200
        audit = db_session.query(models.AuditLog).filter_by(action="update", contact_id=c.id).first()
        assert audit is not None
        assert audit.app_id == app.id
