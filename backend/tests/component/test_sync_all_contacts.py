"""L1 Component — _sync_all_contacts() in sync_icloud.py: orchestration of
both contacts providers (iCloud CardDAV + Google People API) behind the
single unified "sync contacts" action.

Both providers' fetch functions are mocked at their own module boundary
(fetch_all_vcards / fetch_all_google_contacts) — this test is only about the
orchestration logic (which provider runs when, error isolation, last_sync
stamping), not about vCard/People-API parsing, which are covered by
test_sync_icloud_contacts.py and test_google_contacts_fetch.py respectively.
"""
from unittest.mock import AsyncMock, patch

import pytest

from app import models
from app.ai.provider import encrypt_api_key
from app.routers.sync_icloud import _sync_all_contacts
from tests.factories import icloud_vcard

pytestmark = pytest.mark.component


def _icloud_cfg(db_session) -> models.ICloudSync:
    cfg = models.ICloudSync(apple_id="test@example.com", app_password_enc=encrypt_api_key("pw"))
    db_session.add(cfg)
    db_session.commit()
    return cfg


def _google_cfg(db_session) -> models.GoogleSync:
    cfg = models.GoogleSync(
        client_id="test-client-id",
        client_secret_enc=encrypt_api_key("test-secret"),
        access_token_enc=encrypt_api_key("test-access-token"),
        refresh_token_enc=encrypt_api_key("test-refresh-token"),
    )
    db_session.add(cfg)
    db_session.commit()
    return cfg


def _google_person(name: str, email: str) -> dict:
    return {"name": name, "vorname": None, "fn": name, "email": email, "phones": [], "firma": None, "rolle": None, "linkedin_url": None}


class TestSyncAllContacts:
    async def test_positiv_nur_icloud_konfiguriert(self, db_session, monkeypatch):
        icloud_cfg = _icloud_cfg(db_session)
        raw = icloud_vcard("Erika Musterfrau", family="Musterfrau", given="Erika", email="erika@example.com")
        monkeypatch.setattr("app.routers.sync_icloud.fetch_all_vcards", AsyncMock(return_value=[raw]))

        created, errors, touched_ids, updated = await _sync_all_contacts(db_session, None, "de")

        assert errors == []
        assert created == 1
        assert len(touched_ids) == 1
        db_session.refresh(icloud_cfg)
        assert icloud_cfg.contacts_last_sync is not None

    async def test_positiv_nur_google_konfiguriert(self, db_session, monkeypatch):
        google_cfg = _google_cfg(db_session)
        with patch(
            "app.routers.sync_google.fetch_all_google_contacts",
            new=AsyncMock(return_value=[_google_person("Jane Doe", "jane@example.com")]),
        ):
            created, errors, touched_ids, updated = await _sync_all_contacts(db_session, None, "de")

        assert errors == []
        assert created == 1
        assert len(touched_ids) == 1
        db_session.refresh(google_cfg)
        assert google_cfg.contacts_last_sync is not None

    async def test_positiv_beide_konfiguriert_werden_kombiniert(self, db_session, monkeypatch):
        icloud_cfg = _icloud_cfg(db_session)
        google_cfg = _google_cfg(db_session)
        raw = icloud_vcard("Erika Musterfrau", family="Musterfrau", given="Erika", email="erika@example.com")
        monkeypatch.setattr("app.routers.sync_icloud.fetch_all_vcards", AsyncMock(return_value=[raw]))
        with patch(
            "app.routers.sync_google.fetch_all_google_contacts",
            new=AsyncMock(return_value=[_google_person("Jane Doe", "jane@example.com")]),
        ):
            created, errors, touched_ids, updated = await _sync_all_contacts(db_session, None, "de")

        assert errors == []
        assert created == 2
        assert len(touched_ids) == 2
        db_session.refresh(icloud_cfg)
        db_session.refresh(google_cfg)
        assert icloud_cfg.contacts_last_sync is not None
        assert google_cfg.contacts_last_sync is not None

    async def test_negativ_icloud_fehler_blockiert_google_nicht(self, db_session, monkeypatch):
        _icloud_cfg(db_session)
        google_cfg = _google_cfg(db_session)
        monkeypatch.setattr(
            "app.routers.sync_icloud.fetch_all_vcards", AsyncMock(side_effect=RuntimeError("401 Unauthorized"))
        )
        with patch(
            "app.routers.sync_google.fetch_all_google_contacts",
            new=AsyncMock(return_value=[_google_person("Jane Doe", "jane@example.com")]),
        ):
            created, errors, touched_ids, updated = await _sync_all_contacts(db_session, None, "de")

        assert created == 1
        assert any("CardDAV" in e for e in errors)
        db_session.refresh(google_cfg)
        assert google_cfg.contacts_last_sync is not None

    async def test_positiv_ohne_jede_konfiguration_liefert_leeres_ergebnis(self, db_session):
        created, errors, touched_ids, updated = await _sync_all_contacts(db_session, None, "de")

        assert created == 0
        assert errors == []
        assert touched_ids == []
        assert updated == 0

    async def test_positiv_backfill_verlinkt_bestandskontakt_ueber_erwaehnung(self, db_session, monkeypatch):
        from tests.factories import application_factory, contact_factory

        app = application_factory(db_session, firma="Andere Firma GmbH", kommentar="Telefonat mit Erika Musterfrau.")
        existing = contact_factory(db_session, name="Musterfrau", vorname="Erika", email="erika-bereits-da@example.com")
        db_session.commit()
        _icloud_cfg(db_session)
        monkeypatch.setattr("app.routers.sync_icloud.fetch_all_vcards", AsyncMock(return_value=[]))

        created, errors, touched_ids, updated = await _sync_all_contacts(db_session, None, "de")

        assert created == 0
        assert updated == 1
        db_session.refresh(existing)
        assert app in existing.applications
