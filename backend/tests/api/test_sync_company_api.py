"""L2 API — HTTP-Endpunkte in sync_company.py (Status, Run, Cancel,
Reset-Lock, Reset-Failed, Profil-Reset). Der eigentliche Batch-Sync
(_run_sync_batch) läuft als Hintergrund-Task und wird hier bewusst NICHT
inhaltlich getestet — das übernehmen tests/component/test_sync_company_*.py.
"""
import pytest

import app.routers.sync_company as sync_company_module
from app import models
from tests.factories import company_profile_factory

pytestmark = pytest.mark.api


@pytest.fixture(autouse=True)
def _reset_module_globals():
    """_SYNC_RUNNING/_SYNC_CANCEL/_CURRENT_COMPANY sind Modul-globals — zwischen
    Tests zurücksetzen, damit sich Tests nicht gegenseitig beeinflussen."""
    sync_company_module._SYNC_RUNNING = False
    sync_company_module._SYNC_CANCEL = False
    sync_company_module._CURRENT_COMPANY = None
    yield
    sync_company_module._SYNC_RUNNING = False
    sync_company_module._SYNC_CANCEL = False
    sync_company_module._CURRENT_COMPANY = None


class TestCompanySyncStatus:
    def test_positiv_leere_liste_ohne_profile(self, client):
        resp = client.get("/api/sync/company/status")

        assert resp.status_code == 200
        body = resp.json()
        assert body["running"] is False
        assert body["pending"] == 0
        assert body["profiles"] == []

    def test_positiv_zaehlt_profile_nach_status(self, client, db_session):
        company_profile_factory(db_session, sync_status="pending")
        company_profile_factory(db_session, sync_status="done")
        company_profile_factory(db_session, sync_status="failed")
        company_profile_factory(db_session, sync_status="needs_review")
        db_session.commit()

        resp = client.get("/api/sync/company/status")

        body = resp.json()
        assert body["pending"] == 1
        assert body["done"] == 1
        assert body["failed"] == 1
        assert body["needs_review"] == 1
        assert len(body["profiles"]) == 4


class TestCompanySyncRun:
    def test_negativ_bereits_laufend_liefert_started_false(self, client, db_session, monkeypatch):
        monkeypatch.setattr(sync_company_module, "_SYNC_RUNNING", True)
        company_profile_factory(db_session, sync_status="pending")
        db_session.commit()

        resp = client.post("/api/sync/company/run")

        assert resp.status_code == 200
        assert resp.json()["started"] is False

    def test_negativ_keine_pending_profile_liefert_started_false(self, client, db_session):
        company_profile_factory(db_session, sync_status="done")
        db_session.commit()

        resp = client.post("/api/sync/company/run")

        assert resp.status_code == 200
        assert resp.json()["started"] is False
        assert resp.json()["count"] == 0

    def test_positiv_startet_batch_fuer_pending_profile(self, client, db_session, monkeypatch):
        company_profile_factory(db_session, sync_status="pending")
        company_profile_factory(db_session, sync_status="pending")
        db_session.commit()

        monkeypatch.setattr(sync_company_module, "_run_sync_batch", lambda ids, uid: None)

        resp = client.post("/api/sync/company/run")

        assert resp.status_code == 200
        assert resp.json()["started"] is True
        assert resp.json()["count"] == 2

    def test_positiv_force_schliesst_bereits_erledigte_profile_ein(self, client, db_session, monkeypatch):
        company_profile_factory(db_session, sync_status="done")
        db_session.commit()

        monkeypatch.setattr(sync_company_module, "_run_sync_batch", lambda ids, uid: None)

        resp = client.post("/api/sync/company/run", params={"force": True})

        assert resp.status_code == 200
        assert resp.json()["started"] is True
        assert resp.json()["count"] == 1

    def test_positiv_company_ids_scoped_auf_auswahl(self, client, db_session, monkeypatch):
        p1 = company_profile_factory(db_session, sync_status="pending")
        company_profile_factory(db_session, sync_status="pending")
        db_session.commit()

        monkeypatch.setattr(sync_company_module, "_run_sync_batch", lambda ids, uid: None)

        resp = client.post("/api/sync/company/run", params={"company_ids": [p1.id]})

        assert resp.status_code == 200
        assert resp.json()["count"] == 1


class TestCancelAndResetLock:
    def test_positiv_cancel_setzt_flag(self, client):
        resp = client.post("/api/sync/company/cancel")

        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        assert sync_company_module._SYNC_CANCEL is True

    def test_positiv_reset_lock_setzt_alle_globals_zurueck(self, client, monkeypatch):
        monkeypatch.setattr(sync_company_module, "_SYNC_RUNNING", True)
        monkeypatch.setattr(sync_company_module, "_SYNC_CANCEL", True)
        monkeypatch.setattr(sync_company_module, "_CURRENT_COMPANY", "Contoso AG")

        resp = client.post("/api/sync/company/reset-lock")

        assert resp.status_code == 200
        assert sync_company_module._SYNC_RUNNING is False
        assert sync_company_module._SYNC_CANCEL is False
        assert sync_company_module._CURRENT_COMPANY is None


class TestResetFailed:
    def test_positiv_setzt_fehlgeschlagene_profile_auf_pending(self, client, db_session):
        p1 = company_profile_factory(db_session, sync_status="failed", sync_error="Fehler X")
        company_profile_factory(db_session, sync_status="done")
        db_session.commit()

        resp = client.post("/api/sync/company/reset-failed")

        assert resp.status_code == 200
        assert resp.json()["reset"] == 1
        db_session.refresh(p1)
        assert p1.sync_status == "pending"
        assert p1.sync_error is None

    def test_negativ_ohne_fehlgeschlagene_profile_liefert_null(self, client, db_session):
        company_profile_factory(db_session, sync_status="done")
        db_session.commit()

        resp = client.post("/api/sync/company/reset-failed")

        assert resp.json()["reset"] == 0


class TestResetProfile:
    def test_negativ_nicht_gefunden_liefert_404(self, client):
        resp = client.post("/api/sync/company/profiles/999/reset")
        assert resp.status_code == 404

    def test_positiv_setzt_profil_auf_pending_zurueck(self, client, db_session):
        p = company_profile_factory(db_session, sync_status="failed", sync_error="Fehler X")
        db_session.add(models.SyncSettings(user_id=1, audit_log_level="verbose"))
        db_session.commit()

        resp = client.post(f"/api/sync/company/profiles/{p.id}/reset")

        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "id": p.id}
        db_session.refresh(p)
        assert p.sync_status == "pending"
        assert p.sync_error is None
        audit = db_session.query(models.AuditLog).filter_by(company_profile_id=p.id, field="sync_status").first()
        assert audit is not None
