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


def _google_cfg(db_session):
    from app.ai.provider import encrypt_api_key

    cfg = models.GoogleSync(
        client_id="test-client-id",
        client_secret_enc=encrypt_api_key("test-secret"),
        access_token_enc=encrypt_api_key("test-access-token"),
        refresh_token_enc=encrypt_api_key("test-refresh-token"),
        user_id=1,
    )
    db_session.add(cfg)
    db_session.commit()
    return cfg


def _google_person(email: str) -> dict:
    return {
        "name": "Doe", "vorname": "Jane", "fn": "Jane Doe", "email": email,
        "phones": [], "firma": None, "rolle": None, "linkedin_url": None,
    }


class TestContactsSync:
    def test_negativ_ohne_icloud_config_liefert_400(self, client):
        resp = client.post("/api/sync/icloud/contacts/sync", json={"contact_ids": [1], "force": False})
        assert resp.status_code == 400

    def test_positiv_ohne_contact_ids_startet_hintergrundlauf_mit_batch_result(self, client, db_session):
        # Ohne contact_ids läuft der Endpoint jetzt als Background-Task (fire
        # and poll, wie jeder andere Batch-Sync-Button) statt die ganze
        # Adressbuch-Synchronisierung inline zu blockieren — die Response
        # kommt sofort mit {"started": true}, das tatsächliche Ergebnis landet
        # unter dem Batch-Result-Key "contacts_manual_sync". Der FastAPI
        # TestClient führt BackgroundTasks synchron vor der Response aus,
        # daher ist das Ergebnis hier schon bereit, ohne echt pollen zu müssen.
        _icloud_cfg(db_session)
        vcards = [_vcard("Neue Person", email="neu@example.com")]

        with patch("app.routers.sync_icloud.fetch_all_vcards", new=AsyncMock(return_value=vcards)):
            resp = client.post("/api/sync/icloud/contacts/sync", json={"force": False})

        assert resp.status_code == 200
        assert resp.json()["started"] is True

        contact = db_session.query(models.Contact).filter_by(email="neu@example.com").one()
        batch = client.get("/api/sync/google/batch/results").json()["contacts_manual_sync"]
        assert batch["done"] is True
        assert batch["errors"] == []
        assert batch["synced"] == [contact.id]

    def test_positiv_beide_provider_konfiguriert_liefern_eigene_progress_eintraege(self, client, db_session):
        # _sync_all_contacts() initialisiert/beendet jetzt einen eigenen
        # Progress-Eintrag pro konfiguriertem Provider ("icloud_contacts" /
        # "google_contacts"), damit die Live-Fortschrittsanzeige beide
        # Hälften eines kombinierten Syncs zeigen kann, nicht nur iCloud.
        _icloud_cfg(db_session)
        _google_cfg(db_session)
        vcards = [_vcard("Neue Person", email="neu@example.com")]

        async def fake_google_fetch(cfg_arg, db_arg):
            return [_google_person("jane@example.com")]

        with patch("app.routers.sync_icloud.fetch_all_vcards", new=AsyncMock(return_value=vcards)), \
             patch("app.routers.sync_google.fetch_all_google_contacts", new=fake_google_fetch):
            resp = client.post("/api/sync/icloud/contacts/sync", json={"force": False})

        assert resp.status_code == 200
        progress = client.get("/api/sync/google/progress").json()
        assert progress["icloud_contacts"]["done"] is True
        assert progress["icloud_contacts"]["created"] == 1
        assert progress["google_contacts"]["done"] is True
        assert progress["google_contacts"]["created"] == 1

    def test_positiv_ohne_icloud_aber_mit_google_startet_hintergrundlauf(self, client, db_session):
        # Kein ICloudSync-Eintrag — nur Google konfiguriert. Der Endpoint darf
        # nicht mit 400 ablehnen, nur weil iCloud fehlt.
        _google_cfg(db_session)

        async def fake_google_fetch(cfg_arg, db_arg):
            return [_google_person("jane@example.com")]

        with patch("app.routers.sync_google.fetch_all_google_contacts", new=fake_google_fetch):
            resp = client.post("/api/sync/icloud/contacts/sync", json={"force": False})

        assert resp.status_code == 200
        assert resp.json()["started"] is True
        assert db_session.query(models.Contact).filter_by(email="jane@example.com").count() == 1
        batch = client.get("/api/sync/google/batch/results").json()["contacts_manual_sync"]
        assert batch["errors"] == []
        assert len(batch["synced"]) == 1

    def test_positiv_gescopter_re_match_kombiniert_beide_provider(self, client, db_session):
        _icloud_cfg(db_session)
        _google_cfg(db_session)
        contact = contact_factory(db_session, name="Doe", email="jane@example.com", firma=None)
        db_session.commit()
        vcards = [_vcard("Someone Else", email="someone@example.com")]

        async def fake_google_fetch(cfg_arg, db_arg):
            return [{
                "name": "Doe", "vorname": "Jane", "fn": "Jane Doe", "email": "jane@example.com",
                "phones": [], "firma": "Contoso AG", "rolle": None, "linkedin_url": None,
            }]

        with patch("app.routers.sync_icloud.fetch_all_vcards", new=AsyncMock(return_value=vcards)), \
             patch("app.routers.sync_google.fetch_all_google_contacts", new=fake_google_fetch):
            resp = client.post("/api/sync/icloud/contacts/sync", json={"contact_ids": [contact.id], "force": False})

        assert resp.status_code == 200
        assert resp.json()["synced"] == [contact.id]
        db_session.refresh(contact)
        assert contact.firma == "Contoso AG"

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

    def test_positiv_ein_konsolidierter_audit_eintrag_statt_einem_pro_feld(self, client, db_session):
        """Live-Feedback: nach einem Batch-Sync war im Audit-Log für einen
        geänderten Bestandskontakt nicht auf einen Blick ersichtlich, was
        sich geändert hat — ein Eintrag pro geändertem Feld, verstreut im
        Log. _merge_parsed_contact() fasst jetzt alle Feldänderungen EINES
        Kontakts in EINEM Audit-Eintrag zusammen."""
        db_session.add(models.SyncSettings(user_id=1, audit_log_level="verbose"))
        _icloud_cfg(db_session)
        contact = contact_factory(
            db_session, name="Erika Musterfrau", email="erika@contoso.com",
            rolle=None, firma=None, phones=[],
        )
        db_session.commit()
        vcards = [_vcard("Erika Musterfrau", email="erika@contoso.com", org="Contoso AG")]

        with patch("app.routers.sync_icloud.fetch_all_vcards", new=AsyncMock(return_value=vcards)):
            resp = client.post("/api/sync/icloud/contacts/sync", json={"contact_ids": [contact.id], "force": False})

        assert resp.status_code == 200
        audits = db_session.query(models.AuditLog).filter_by(
            action="update", contact_id=contact.id,
        ).all()
        assert len(audits) == 1
        assert "firma: Contoso AG" in audits[0].new_value

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
