"""L2 API — POST /api/sync/icloud/contacts/sync: per-contact Sync/Re-Sync.

Sync (force=False) only adds new phone numbers / fills empty fields; Re-Sync
(force=True) overwrites the contact wholesale from the matched vCard — the
two semantics confirmed for the multi-phone-numbers feature.
"""
from unittest.mock import AsyncMock, patch

import pytest

from app import models
from tests.factories import contact_factory

pytestmark = pytest.mark.api


def _vcard(fn: str, email: str | None = None, org: str | None = None, tel: str | None = None, tel_type: str = "CELL") -> str:
    lines = ["BEGIN:VCARD", "VERSION:3.0", f"FN:{fn}"]
    if email:
        lines.append(f"EMAIL:{email}")
    if org:
        lines.append(f"ORG:{org}")
    if tel:
        lines.append(f"TEL;TYPE={tel_type}:{tel}")
    lines.append("END:VCARD")
    return "\r\n".join(lines)


def _icloud_cfg(db_session):
    cfg = models.ICloudSync(apple_id="test@example.com", app_password_enc="x", user_id=1)
    db_session.add(cfg)
    db_session.commit()
    return cfg


class TestContactsSync:
    def test_negativ_ohne_icloud_config_liefert_400(self, client):
        resp = client.post("/api/sync/icloud/contacts/sync", json={"contact_ids": [1], "force": False})
        assert resp.status_code == 400

    def test_positiv_ohne_contact_ids_gibt_leeres_ergebnis_wenn_keine_kontakte(self, client, db_session):
        _icloud_cfg(db_session)
        resp = client.post("/api/sync/icloud/contacts/sync", json={"force": False})
        assert resp.status_code == 200
        assert resp.json() == {"synced": [], "not_found": [], "errors": []}

    def test_positiv_sync_fuegt_nur_neue_nummer_hinzu_ueberschreibt_nicht(self, client, db_session):
        _icloud_cfg(db_session)
        contact = contact_factory(
            db_session, name="Erika Musterfrau", email="erika@contoso.com",
            rolle="Bestehende Rolle", firma=None, phones=[{"number": "+49111", "type": "home"}],
        )
        db_session.commit()
        vcards = [_vcard("Erika Musterfrau", email="erika@contoso.com", org="Contoso AG", tel="+491701234567")]

        with patch("app.routers.sync_icloud.fetch_all_vcards", new=AsyncMock(return_value=vcards)):
            resp = client.post("/api/sync/icloud/contacts/sync", json={"contact_ids": [contact.id], "force": False})

        assert resp.status_code == 200
        assert resp.json()["synced"] == [contact.id]
        db_session.refresh(contact)
        numbers = {p.number for p in contact.phones}
        assert numbers == {"+49111", "+491701234567"}
        assert contact.rolle == "Bestehende Rolle"  # existing value untouched
        assert contact.firma == "Contoso AG"  # empty field filled
        assert contact.icloud_last_synced_at is not None

    def test_positiv_resync_ueberschreibt_bestehende_werte(self, client, db_session):
        _icloud_cfg(db_session)
        contact = contact_factory(
            db_session, name="Erika Musterfrau", email="erika@contoso.com",
            rolle="Alte Rolle", phones=[{"number": "+49111", "type": "home"}],
        )
        db_session.commit()
        vcards = [_vcard("Erika Musterfrau", email="erika@contoso.com", org="Contoso AG", tel="+491701234567", tel_type="WORK")]

        with patch("app.routers.sync_icloud.fetch_all_vcards", new=AsyncMock(return_value=vcards)):
            resp = client.post("/api/sync/icloud/contacts/sync", json={"contact_ids": [contact.id], "force": True})

        assert resp.status_code == 200
        assert resp.json()["synced"] == [contact.id]
        db_session.refresh(contact)
        assert [(p.number, p.type) for p in contact.phones] == [("+491701234567", "work")]
        assert contact.firma == "Contoso AG"

    def test_negativ_kein_treffer_landet_in_not_found(self, client, db_session):
        _icloud_cfg(db_session)
        contact = contact_factory(db_session, name="Ohne Treffer", email="niemand@nowhere.de")
        db_session.commit()

        with patch("app.routers.sync_icloud.fetch_all_vcards", new=AsyncMock(return_value=[])):
            resp = client.post("/api/sync/icloud/contacts/sync", json={"contact_ids": [contact.id], "force": False})

        assert resp.status_code == 200
        body = resp.json()
        assert body["synced"] == []
        assert body["not_found"] == [contact.id]

    def test_negativ_carddav_fehler_liefert_leere_ergebnisse_mit_error(self, client, db_session):
        _icloud_cfg(db_session)
        contact = contact_factory(db_session, name="Egal")
        db_session.commit()

        async def _raise(*a, **kw):
            raise RuntimeError("boom")

        with patch("app.routers.sync_icloud.fetch_all_vcards", new=_raise):
            resp = client.post("/api/sync/icloud/contacts/sync", json={"contact_ids": [contact.id], "force": False})

        assert resp.status_code == 200
        body = resp.json()
        assert body["synced"] == []
        assert body["errors"]
