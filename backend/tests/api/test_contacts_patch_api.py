"""L2 API — PATCH /api/contacts/{id}.

Regressionstest für einen live gefundenen Bug: ContactPatch.letzter_kontakt
war als `Optional[str]` statt `Optional[date]` typisiert. Da patch_contact
die Werte per `setattr` ungeprüft auf die ORM-Instanz schreibt, landete beim
Speichern ein roher String im Date-Spaltentyp — SQLite/SQLAlchemy lehnt das
mit einem 500er ab, sobald das Formular (z.B. beim Vorname/Nachname-Split
im Kontakt-Modal) auch letzter_kontakt mitschickt.
"""
import pytest

from app import models
from tests.factories import contact_factory

pytestmark = pytest.mark.api


class TestPatchContact:
    def test_positiv_letzter_kontakt_als_datum_wird_korrekt_gespeichert(self, client, db_session):
        c = contact_factory(db_session, name="Kühne", vorname=None)
        db_session.commit()

        resp = client.patch(f"/api/contacts/{c.id}", json={
            "vorname": "Natalia",
            "name": "Kühne",
            "letzter_kontakt": "2026-07-03",
        })

        assert resp.status_code == 200
        db_session.expire_all()
        updated = db_session.query(models.Contact).filter_by(id=c.id).first()
        assert updated.vorname == "Natalia"
        assert str(updated.letzter_kontakt) == "2026-07-03"

    def test_positiv_vorname_nachname_split_ohne_datum_funktioniert(self, client, db_session):
        c = contact_factory(db_session, name="Max Mustermann", vorname=None)
        db_session.commit()

        resp = client.patch(f"/api/contacts/{c.id}", json={
            "vorname": "Max",
            "name": "Mustermann",
        })

        assert resp.status_code == 200
        db_session.expire_all()
        updated = db_session.query(models.Contact).filter_by(id=c.id).first()
        assert updated.vorname == "Max"
        assert updated.name == "Mustermann"

    def test_negativ_ungueltiges_datumsformat_liefert_422_statt_500(self, client, db_session):
        c = contact_factory(db_session)
        db_session.commit()

        resp = client.patch(f"/api/contacts/{c.id}", json={"letzter_kontakt": "nicht-ein-datum"})

        assert resp.status_code == 422

    def test_negativ_unbekannte_id_liefert_404(self, client, db_session):
        resp = client.patch("/api/contacts/999999", json={"name": "X"})
        assert resp.status_code == 404
