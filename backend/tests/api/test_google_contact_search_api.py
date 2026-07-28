"""L2 API — /api/sync/google/contacts/search + /import.

Manueller Kontakt-Import analog zu test_icloud_contact_search_api.py: der
User sucht gezielt im vollen Google-Adressbuch und entscheidet selbst, wen
er importiert und ob er ihn mit einer Bewerbung verknüpft — unabhängig vom
automatischen Sync (_sync_contacts_from_google), der ebenfalls das ganze
Adressbuch importiert, aber nie anhand von Firmenname/Adressbuch-Match
verknüpft.
"""
from unittest.mock import AsyncMock, patch

import pytest

from app import models
from app.ai.provider import encrypt_api_key
from tests.factories import application_factory, contact_factory

pytestmark = pytest.mark.api


def _person(name: str, fn: str | None = None, email: str | None = None, firma: str | None = None) -> dict:
    return {
        "name": name, "vorname": None, "fn": fn or name, "email": email,
        "phones": [], "firma": firma, "rolle": None, "linkedin_url": None,
    }


def _google_cfg(db_session, contacts_scope_granted: bool = True) -> models.GoogleSync:
    cfg = models.GoogleSync(
        client_id="test-client-id",
        client_secret_enc=encrypt_api_key("test-secret"),
        access_token_enc=encrypt_api_key("test-access-token"),
        refresh_token_enc=encrypt_api_key("test-refresh-token"),
        contacts_scope_granted=contacts_scope_granted,
        user_id=1,
    )
    db_session.add(cfg)
    db_session.commit()
    return cfg


class TestSearchContacts:
    def test_positiv_findet_treffer_unabhaengig_von_relevanz(self, client, db_session):
        _google_cfg(db_session)
        people = [_person("Irrelevante Person", email="irrelevant@example.com", firma="Irgendeine Firma")]

        with patch("app.routers.sync_google.fetch_all_google_contacts", new=AsyncMock(return_value=people)):
            resp = client.get("/api/sync/google/contacts/search?q=Irrelevante")

        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 1
        assert results[0]["name"] == "Irrelevante Person"
        assert results[0]["email"] == "irrelevant@example.com"

    def test_positiv_bereits_vorhandener_kontakt_wird_markiert_statt_versteckt(self, client, db_session):
        _google_cfg(db_session)
        contact_factory(db_session, name="Schon Da", email="schonda@example.com")
        people = [_person("Schon Da", email="schonda@example.com")]

        with patch("app.routers.sync_google.fetch_all_google_contacts", new=AsyncMock(return_value=people)):
            resp = client.get("/api/sync/google/contacts/search?q=Schon")

        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 1
        assert results[0]["already_imported"] is True

    def test_negativ_neuer_kandidat_ist_nicht_als_already_imported_markiert(self, client, db_session):
        _google_cfg(db_session)
        people = [_person("Neue Person", email="neu@example.com")]

        with patch("app.routers.sync_google.fetch_all_google_contacts", new=AsyncMock(return_value=people)):
            resp = client.get("/api/sync/google/contacts/search?q=Neue")

        assert resp.status_code == 200
        assert resp.json()[0]["already_imported"] is False

    def test_negativ_ohne_google_config_liefert_400(self, client, db_session):
        resp = client.get("/api/sync/google/contacts/search?q=Test")
        assert resp.status_code == 400

    def test_negativ_ohne_contacts_scope_liefert_400(self, client, db_session):
        _google_cfg(db_session, contacts_scope_granted=False)
        resp = client.get("/api/sync/google/contacts/search?q=Test")
        assert resp.status_code == 400

    def test_negativ_kein_treffer_liefert_leere_liste(self, client, db_session):
        _google_cfg(db_session)
        people = [_person("Jemand Anders", email="anders@example.com")]

        with patch("app.routers.sync_google.fetch_all_google_contacts", new=AsyncMock(return_value=people)):
            resp = client.get("/api/sync/google/contacts/search?q=Gesuchtername")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_negativ_duplikate_werden_dedupliziert(self, client, db_session):
        _google_cfg(db_session)
        people = [
            _person("Erika Musterfrau", email="erika@example.com"),
            _person("Erika Musterfrau", email="erika@example.com"),
        ]

        with patch("app.routers.sync_google.fetch_all_google_contacts", new=AsyncMock(return_value=people)):
            resp = client.get("/api/sync/google/contacts/search?q=Erika")

        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_corner_case_ergebnisse_werden_bei_30_treffern_begrenzt(self, client, db_session):
        _google_cfg(db_session)
        people = [_person(f"Testperson {i}", email=f"test{i}@example.com") for i in range(35)]

        with patch("app.routers.sync_google.fetch_all_google_contacts", new=AsyncMock(return_value=people)):
            resp = client.get("/api/sync/google/contacts/search?q=Testperson")

        assert resp.status_code == 200
        assert len(resp.json()) == 30

    def test_positiv_bereits_vorhandener_kontakt_wird_ueber_alten_vollnamen_gefunden(self, client, db_session):
        # Alt-Kontakt (vor dem Vorname/Nachname-Split): name enthält den vollen
        # Anzeigenamen (fn), nicht nur den Nachnamen wie Google People API liefert.
        _google_cfg(db_session)
        contact_factory(db_session, name="Erika Musterfrau", email=None)
        people = [_person("Musterfrau", fn="Erika Musterfrau")]

        with patch("app.routers.sync_google.fetch_all_google_contacts", new=AsyncMock(return_value=people)):
            resp = client.get("/api/sync/google/contacts/search?q=Erika")

        assert resp.status_code == 200
        assert resp.json()[0]["already_imported"] is True


class TestImportContacts:
    def test_positiv_importiert_neue_kandidaten(self, client, db_session):
        resp = client.post("/api/sync/google/contacts/import", json={
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

        resp = client.post("/api/sync/google/contacts/import", json={
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

        resp = client.post("/api/sync/google/contacts/import", json={
            "candidates": [{"name": "Verknüpfte Person", "email": "verknuepft@example.com"}],
            "application_id": app.id,
        })

        assert resp.status_code == 200
        contact = db_session.query(models.Contact).filter_by(email="verknuepft@example.com").first()
        assert app in contact.applications

    def test_negativ_unbekannte_application_id_liefert_404(self, client, db_session):
        resp = client.post("/api/sync/google/contacts/import", json={
            "candidates": [{"name": "X"}],
            "application_id": 999999,
        })
        assert resp.status_code == 404

    def test_positiv_bereits_vorhandener_kontakt_wird_trotzdem_mit_bewerbung_verlinkt(self, client, db_session):
        contact = contact_factory(db_session, name="Schon Da", email="schonda@example.com")
        app = application_factory(db_session)
        db_session.commit()

        resp = client.post("/api/sync/google/contacts/import", json={
            "candidates": [{"name": "Schon Da", "email": "schonda@example.com"}],
            "application_id": app.id,
        })

        assert resp.status_code == 200
        assert resp.json()["skipped"] == 1
        db_session.refresh(contact)
        assert app in contact.applications
