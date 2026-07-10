"""L1 Unit — entity_type-Ableitung in add_audit(). Prüft, dass der neue Typ
korrekt aus den gesetzten FKs abgeleitet wird (contact > company > event >
application-Präzedenz, siehe app/audit.py::_infer_entity_type), und dass ein
explizit übergebener entity_type Vorrang vor der Ableitung hat.
"""
import pytest

from app.audit import add_audit
from app import models

pytestmark = pytest.mark.unit


class TestInferEntityType:
    def test_positiv_nur_app_id_liefert_application(self, db_session):
        add_audit(db_session, "create", "user", app_id=1)
        db_session.commit()
        row = db_session.query(models.AuditLog).filter_by(app_id=1).one()
        assert row.entity_type == "application"

    def test_positiv_nur_contact_id_liefert_contact(self, db_session):
        add_audit(db_session, "create", "user", contact_id=1)
        db_session.commit()
        row = db_session.query(models.AuditLog).filter_by(contact_id=1).one()
        assert row.entity_type == "contact"

    def test_positiv_nur_company_profile_id_liefert_company(self, db_session):
        add_audit(db_session, "create", "user", company_profile_id=1)
        db_session.commit()
        row = db_session.query(models.AuditLog).filter_by(company_profile_id=1).one()
        assert row.entity_type == "company"

    def test_positiv_nur_event_id_liefert_event(self, db_session):
        add_audit(db_session, "create", "user", event_id=1)
        db_session.commit()
        row = db_session.query(models.AuditLog).filter_by(event_id=1).one()
        assert row.entity_type == "event"

    def test_positiv_contact_und_app_gleichzeitig_priorisiert_contact(self, db_session):
        # Kontakt, der im Kontext einer Bewerbung angelegt wurde — der eigentlich
        # geänderte Datensatz (Kontakt) hat Vorrang vor dem Kontext (Bewerbung).
        add_audit(db_session, "create", "user", app_id=1, contact_id=2)
        db_session.commit()
        row = db_session.query(models.AuditLog).filter_by(contact_id=2).one()
        assert row.entity_type == "contact"

    def test_positiv_event_und_app_gleichzeitig_priorisiert_event(self, db_session):
        add_audit(db_session, "create", "user", app_id=1, event_id=3)
        db_session.commit()
        row = db_session.query(models.AuditLog).filter_by(event_id=3).one()
        assert row.entity_type == "event"

    def test_corner_case_keine_fk_gesetzt_liefert_none(self, db_session):
        add_audit(db_session, "create", "user")
        db_session.commit()
        row = db_session.query(models.AuditLog).filter_by(app_id=None, contact_id=None).order_by(models.AuditLog.id.desc()).first()
        assert row.entity_type is None

    def test_positiv_expliziter_entity_type_hat_vorrang_vor_ableitung(self, db_session):
        # Ein Firmen-Merge hat keine eindeutige "Kontext"-FK — hier wird der
        # Typ explizit gesetzt statt aus den FKs abgeleitet.
        add_audit(db_session, "merge", "user", company_profile_id=5, entity_type="company")
        db_session.commit()
        row = db_session.query(models.AuditLog).filter_by(company_profile_id=5).one()
        assert row.entity_type == "company"
