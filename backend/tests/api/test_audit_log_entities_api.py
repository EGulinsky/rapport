"""L2 API — Audit-Log-Abdeckung für Kontakte, Firmen und Kalendereinträge (Events).

Ergänzt test_audit_log_coverage.py (das nur Bewerbungsfelder abdeckt) um die drei
neuen Entitätstypen, die AuditLog jetzt über contact_id/company_profile_id/event_id
referenzieren kann. `add_audit()` verwirft "update"-Einträge im Log-Level "normal" —
Tests dafür schalten vorher auf "verbose".
"""
import pytest

from tests.factories import application_factory, contact_factory, company_profile_factory, event_factory
from app import models

pytestmark = pytest.mark.api


def _make_verbose(db_session):
    db_session.add(models.SyncSettings(user_id=1, audit_log_level="verbose"))
    db_session.commit()


class TestContactAudit:
    def test_positiv_create_wird_protokolliert(self, client, db_session):
        resp = client.post("/api/contacts/", json={"name": "Max Mustermann"})

        assert resp.status_code == 201
        contact_id = resp.json()["id"]
        audit = db_session.query(models.AuditLog).filter_by(contact_id=contact_id, action="create").first()
        assert audit is not None
        assert audit.new_value == "Max Mustermann"

    def test_positiv_patch_wird_protokolliert(self, client, db_session):
        _make_verbose(db_session)
        contact = contact_factory(db_session, name="Alt", telefon=None)
        db_session.commit()

        resp = client.patch(f"/api/contacts/{contact.id}", json={"telefon": "+49123456"})

        assert resp.status_code == 200
        audit = db_session.query(models.AuditLog).filter_by(contact_id=contact.id, field="telefon").first()
        assert audit is not None
        assert audit.new_value == "+49123456"

    def test_positiv_bulk_delete_wird_protokolliert(self, client, db_session):
        contact = contact_factory(db_session, name="Zu löschen")
        db_session.commit()
        contact_id = contact.id

        resp = client.request("DELETE", "/api/contacts/bulk", json={"ids": [contact_id]})

        assert resp.status_code == 200
        audit = db_session.query(models.AuditLog).filter_by(contact_id=contact_id, action="delete").first()
        assert audit is not None
        assert audit.old_value == "Zu löschen"

    def test_positiv_app_scoped_create_und_delete_werden_protokolliert(self, client, db_session):
        app = application_factory(db_session)
        db_session.commit()

        resp = client.post(f"/api/applications/{app.id}/contacts", json={"name": "Kontakt A"})
        assert resp.status_code == 201
        contact_id = resp.json()["id"]
        create_audit = db_session.query(models.AuditLog).filter_by(contact_id=contact_id, action="create").first()
        assert create_audit is not None
        assert create_audit.app_id == app.id

        del_resp = client.delete(f"/api/applications/{app.id}/contacts/{contact_id}")
        assert del_resp.status_code == 204
        delete_audit = db_session.query(models.AuditLog).filter_by(contact_id=contact_id, action="delete").first()
        assert delete_audit is not None

    def test_positiv_merge_wird_protokolliert(self, client, db_session):
        winner = contact_factory(db_session, name="Gewinner")
        loser = contact_factory(db_session, name="Verlierer")
        db_session.commit()

        resp = client.post("/api/merge/contacts", json={
            "winner_id": winner.id, "loser_ids": [loser.id], "field_overrides": {},
        })

        assert resp.status_code == 200
        audit = db_session.query(models.AuditLog).filter_by(contact_id=winner.id, action="merge").first()
        assert audit is not None


class TestEntityTypeApi:
    def test_positiv_response_enthaelt_entity_type(self, client, db_session):
        resp = client.post("/api/contacts/", json={"name": "Max Mustermann"})
        assert resp.status_code == 201

        list_resp = client.get("/api/audit/", params={"contact_id": resp.json()["id"]})

        assert list_resp.status_code == 200
        items = list_resp.json()["items"]
        assert len(items) == 1
        assert items[0]["entity_type"] == "contact"

    def test_positiv_filter_nach_entity_type(self, client, db_session):
        client.post("/api/contacts/", json={"name": "Kontakt A"})
        client.post("/api/companies", json={"name": "Contoso AG"})

        resp = client.get("/api/audit/", params={"entity_type": "company"})

        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) >= 1
        assert all(i["entity_type"] == "company" for i in items)

    def test_positiv_firmenmerge_setzt_company_profile_id(self, client, db_session):
        # Regressionstest für einen Bug: der Merge-Audit-Eintrag hatte zuvor
        # keine einzige FK gesetzt (app_id=None, company_profile_id nie
        # übergeben) und war dadurch weder auffindbar noch typisierbar.
        winner = company_profile_factory(db_session, name_display="Contoso AG")
        loser = company_profile_factory(db_session, name_display="Contoso Old AG")
        db_session.commit()

        resp = client.post("/api/merge/companies", json={
            "winner_id": winner.id, "loser_ids": [loser.id], "field_overrides": {},
        })

        assert resp.status_code == 200
        audit = db_session.query(models.AuditLog).filter_by(action="merge", company_profile_id=winner.id).first()
        assert audit is not None
        assert audit.entity_type == "company"


class TestCompanyAudit:
    def test_positiv_create_wird_protokolliert(self, client, db_session):
        resp = client.post("/api/companies", json={"name": "Contoso AG"})

        assert resp.status_code == 201
        company_id = resp.json()["id"]
        audit = db_session.query(models.AuditLog).filter_by(company_profile_id=company_id, action="create").first()
        assert audit is not None
        assert audit.new_value == "Contoso AG"

    def test_positiv_update_wird_protokolliert(self, client, db_session):
        _make_verbose(db_session)
        cp = company_profile_factory(db_session, industry=None)
        db_session.commit()

        resp = client.patch(f"/api/companies/{cp.id}", json={"industry": "Software"})

        assert resp.status_code == 200
        audit = db_session.query(models.AuditLog).filter_by(company_profile_id=cp.id, field="industry").first()
        assert audit is not None
        assert audit.new_value == "Software"

    def test_positiv_bulk_delete_wird_protokolliert(self, client, db_session):
        cp = company_profile_factory(db_session, name_display="Zu löschen AG")
        db_session.commit()
        cp_id = cp.id

        resp = client.request("DELETE", "/api/companies/bulk", json={"ids": [cp_id]})

        assert resp.status_code == 200
        audit = db_session.query(models.AuditLog).filter_by(company_profile_id=cp_id, action="delete").first()
        assert audit is not None

    def test_positiv_firmenmerge_protokolliert_gewinner_feld(self, client, db_session):
        _make_verbose(db_session)
        winner = company_profile_factory(db_session, name_display="Contoso AG", industry="alt")
        loser = company_profile_factory(db_session, name_display="Contoso Old AG", industry="neu")
        db_session.commit()

        resp = client.post("/api/merge/companies", json={
            "winner_id": winner.id, "loser_ids": [loser.id],
            "field_overrides": {"industry": loser.id},
        })

        assert resp.status_code == 200
        audit = db_session.query(models.AuditLog).filter_by(company_profile_id=winner.id, field="industry").first()
        assert audit is not None
        assert audit.new_value == "neu"


class TestEventAudit:
    def test_positiv_manuelles_erstellen_wird_protokolliert(self, client, db_session):
        app = application_factory(db_session)
        db_session.commit()

        resp = client.post(f"/api/applications/{app.id}/events", json={"typ": "notiz", "titel": "Telefonat"})

        assert resp.status_code == 201
        event_id = resp.json()["id"]
        audit = db_session.query(models.AuditLog).filter_by(event_id=event_id, action="create").first()
        assert audit is not None
        assert audit.app_id == app.id
        assert audit.new_value == "Telefonat"

    def test_positiv_update_wird_protokolliert(self, client, db_session):
        _make_verbose(db_session)
        app = application_factory(db_session)
        ev = event_factory(db_session, app, titel="Alt")
        db_session.commit()

        resp = client.patch(f"/api/applications/{app.id}/events/{ev.id}", json={"titel": "Neu"})

        assert resp.status_code == 200
        audit = db_session.query(models.AuditLog).filter_by(event_id=ev.id, field="titel").first()
        assert audit is not None
        assert audit.old_value == "Alt"
        assert audit.new_value == "Neu"

    def test_positiv_loeschen_wird_protokolliert(self, client, db_session):
        app = application_factory(db_session)
        ev = event_factory(db_session, app, titel="Zu löschen")
        db_session.commit()

        resp = client.delete(f"/api/applications/{app.id}/events/{ev.id}")

        assert resp.status_code == 204
        audit = db_session.query(models.AuditLog).filter_by(event_id=ev.id, action="delete").first()
        assert audit is not None
        assert audit.old_value == "Zu löschen"

    def test_positiv_status_wechsel_erzeugt_event_audit(self, client, db_session):
        app = application_factory(db_session, main_status="applied")
        db_session.commit()

        resp = client.patch(f"/api/applications/{app.id}", json={"main_status": "hr"})

        assert resp.status_code == 200
        audit = db_session.query(models.AuditLog).filter_by(app_id=app.id, action="create").filter(
            models.AuditLog.event_id.isnot(None)
        ).first()
        assert audit is not None


class TestCleanupEventAudit:
    def test_positiv_automatisch_geloeschtes_duplikat_event_wird_protokolliert(self, client, db_session):
        app = application_factory(db_session)
        keeper = event_factory(db_session, app, typ="gespräch", titel="Gleicher Titel", source=None)
        dup = event_factory(db_session, app, typ="gespräch", titel="Gleicher Titel",
                             datum=keeper.datum, source=None)
        db_session.commit()

        resp = client.post("/api/cleanup/run", params={"scope": "events"})

        assert resp.status_code == 200
        assert db_session.get(models.Event, dup.id) is None
        audit = db_session.query(models.AuditLog).filter_by(event_id=dup.id, action="delete").first()
        assert audit is not None
