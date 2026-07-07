"""L2 API — /api/sync/icloud/contacts/search + /import.

Manueller Kontakt-Import: der User sucht gezielt im vollen Adressbuch (nicht
nur "relevante" Kontakte wie beim automatischen Sync) und entscheidet selbst,
wen er importiert — die Relevanz-Prüfung von _sync_contacts_http gilt hier
bewusst nicht.
"""
from unittest.mock import AsyncMock, patch

import pytest

from app import models
from tests.factories import application_factory, contact_factory

pytestmark = pytest.mark.api


def _vcard(fn: str, email: str | None = None, org: str | None = None, n: tuple[str, str] | None = None) -> str:
    """n: optionales (family, given) für das strukturierte N:-Feld."""
    lines = ["BEGIN:VCARD", "VERSION:3.0", f"FN:{fn}"]
    if n:
        lines.append(f"N:{n[0]};{n[1]};;;")
    if email:
        lines.append(f"EMAIL:{email}")
    if org:
        lines.append(f"ORG:{org}")
    lines.append("END:VCARD")
    return "\r\n".join(lines)


def _icloud_cfg(db_session):
    cfg = models.ICloudSync(apple_id="test@example.com", app_password_enc="x", user_id=1)
    db_session.add(cfg)
    db_session.commit()
    return cfg


class TestSearchContacts:
    def test_positiv_findet_treffer_unabhaengig_von_relevanz(self, client, db_session):
        # Kein CompanyProfile, keine Bewerbungserwähnung — der automatische Sync
        # würde diesen Kontakt NIE importieren. Die manuelle Suche soll ihn
        # trotzdem finden, weil der User bewusst danach sucht.
        _icloud_cfg(db_session)
        vcards = [_vcard("Irrelevante Person", email="irrelevant@example.com", org="Irgendeine Firma")]

        with patch("app.routers.sync_icloud.fetch_all_vcards", new=AsyncMock(return_value=vcards)):
            resp = client.get("/api/sync/icloud/contacts/search?q=Irrelevante")

        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 1
        assert results[0]["name"] == "Irrelevante Person"
        assert results[0]["email"] == "irrelevant@example.com"

    def test_positiv_bereits_vorhandener_kontakt_wird_markiert_statt_versteckt(self, client, db_session):
        # Live-Regressionsfall: Suche nach "qorix" fand 3 echte vCard-Treffer,
        # aber alle drei waren bereits importierte Kontakte — das alte
        # Verhalten (stillschweigend verstecken) lieferte dadurch fälschlich
        # ein leeres Ergebnis, obwohl echte Treffer existierten. Jetzt werden
        # sie weiterhin gezeigt, nur als "already_imported" markiert.
        _icloud_cfg(db_session)
        contact_factory(db_session, name="Schon Da", email="schonda@example.com")
        vcards = [_vcard("Schon Da", email="schonda@example.com")]

        with patch("app.routers.sync_icloud.fetch_all_vcards", new=AsyncMock(return_value=vcards)):
            resp = client.get("/api/sync/icloud/contacts/search?q=Schon")

        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 1
        assert results[0]["already_imported"] is True

    def test_negativ_neuer_kandidat_ist_nicht_als_already_imported_markiert(self, client, db_session):
        _icloud_cfg(db_session)
        vcards = [_vcard("Neue Person", email="neu@example.com")]

        with patch("app.routers.sync_icloud.fetch_all_vcards", new=AsyncMock(return_value=vcards)):
            resp = client.get("/api/sync/icloud/contacts/search?q=Neue")

        assert resp.status_code == 200
        results = resp.json()
        assert results[0]["already_imported"] is False

    def test_negativ_ohne_icloud_config_liefert_400(self, client, db_session):
        resp = client.get("/api/sync/icloud/contacts/search?q=Test")
        assert resp.status_code == 400

    def test_negativ_kein_treffer_liefert_leere_liste(self, client, db_session):
        _icloud_cfg(db_session)
        vcards = [_vcard("Jemand Anders", email="anders@example.com")]

        with patch("app.routers.sync_icloud.fetch_all_vcards", new=AsyncMock(return_value=vcards)):
            resp = client.get("/api/sync/icloud/contacts/search?q=Gesuchtername")

        assert resp.status_code == 200
        assert resp.json() == []


class TestImportContacts:
    def test_positiv_importiert_neue_kandidaten(self, client, db_session):
        resp = client.post("/api/sync/icloud/contacts/import", json={
            "candidates": [
                {"name": "Neue Person", "email": "neu@example.com", "firma": "Contoso"},
            ],
        })

        assert resp.status_code == 200
        body = resp.json()
        assert body["imported"] == 1
        assert body["skipped"] == 0
        contact = db_session.query(models.Contact).filter_by(email="neu@example.com").first()
        assert contact is not None
        assert contact.firma == "Contoso"

    def test_negativ_bereits_vorhandener_kontakt_wird_uebersprungen(self, client, db_session):
        contact_factory(db_session, name="Schon Da", email="schonda@example.com")
        db_session.commit()

        resp = client.post("/api/sync/icloud/contacts/import", json={
            "candidates": [{"name": "Schon Da", "email": "schonda@example.com"}],
        })

        assert resp.status_code == 200
        body = resp.json()
        assert body["imported"] == 0
        assert body["skipped"] == 1
        assert db_session.query(models.Contact).filter_by(email="schonda@example.com").count() == 1

    def test_positiv_verknuepft_mit_application_id(self, client, db_session):
        app = application_factory(db_session)
        db_session.commit()

        resp = client.post("/api/sync/icloud/contacts/import", json={
            "candidates": [{"name": "Verknüpfte Person", "email": "verknuepft@example.com"}],
            "application_id": app.id,
        })

        assert resp.status_code == 200
        contact = db_session.query(models.Contact).filter_by(email="verknuepft@example.com").first()
        assert app in contact.applications

    def test_negativ_unbekannte_application_id_liefert_404(self, client, db_session):
        resp = client.post("/api/sync/icloud/contacts/import", json={
            "candidates": [{"name": "X"}],
            "application_id": 999999,
        })
        assert resp.status_code == 404
