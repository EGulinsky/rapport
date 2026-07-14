"""L2 API — HTTP-Endpunkte in sync_linkedin.py: Config, Status, Run,
Clear-Session, Submit-2FA, People-Suche/-Import, Firmen-Suche/-Import.
Der eigentliche Playwright-Scraper wird an der `_get_linkedin_context()`-
Grenze gemockt (siehe app.routers.sync_company, wiederverwendet von
sync_linkedin.py) — dieselbe Grenze wie in test_sync_company.py etabliert.
"""
from unittest.mock import AsyncMock, patch

import pytest

import app.routers.sync_linkedin as sync_linkedin_module
from app import models
from tests.factories import application_factory, contact_factory

pytestmark = pytest.mark.api


@pytest.fixture(autouse=True)
def _reset_state():
    sync_linkedin_module._reset_state()
    yield
    sync_linkedin_module._reset_state()


class TestConfigEndpoints:
    def test_positiv_ohne_konfiguration_liefert_configured_false(self, client):
        resp = client.get("/api/sync/linkedin/config")

        assert resp.status_code == 200
        assert resp.json()["configured"] is False

    def test_positiv_speichert_neue_konfiguration(self, client, db_session):
        resp = client.post("/api/sync/linkedin/config", json={"email": "user@example.com", "password": "geheim"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["configured"] is True
        assert body["email"] == "user@example.com"
        assert body["has_session"] is False
        cfg = db_session.query(models.LinkedInSync).one()
        assert cfg.password_enc is not None

    def test_positiv_erneutes_speichern_erzwingt_neuanmeldung(self, client, db_session):
        client.post("/api/sync/linkedin/config", json={"email": "user@example.com", "password": "geheim"})
        cfg = db_session.query(models.LinkedInSync).one()
        cfg.session_cookies = "[]"
        db_session.commit()

        client.post("/api/sync/linkedin/config", json={"email": "user@example.com", "password": "neu"})

        db_session.refresh(cfg)
        assert cfg.session_cookies is None

    def test_positiv_loescht_konfiguration(self, client, db_session):
        client.post("/api/sync/linkedin/config", json={"email": "user@example.com", "password": "geheim"})

        resp = client.delete("/api/sync/linkedin/config")

        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        assert db_session.query(models.LinkedInSync).count() == 0

    def test_negativ_loeschen_ohne_konfiguration_ist_no_op(self, client):
        resp = client.delete("/api/sync/linkedin/config")
        assert resp.status_code == 200


class TestStatusAndRun:
    def test_positiv_status_liefert_idle_zustand(self, client):
        resp = client.get("/api/sync/linkedin/status")

        assert resp.status_code == 200
        assert resp.json()["status"] == "idle"

    def test_negativ_run_ohne_konfiguration_liefert_400(self, client):
        resp = client.post("/api/sync/linkedin/run")
        assert resp.status_code == 400

    def test_positiv_run_startet_hintergrund_sync(self, client, db_session):
        client.post("/api/sync/linkedin/config", json={"email": "user@example.com", "password": "geheim"})

        with patch.object(sync_linkedin_module, "_run_sync_task"):
            resp = client.post("/api/sync/linkedin/run")

        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

    def test_negativ_run_waehrend_laufendem_sync_liefert_409(self, client, db_session):
        client.post("/api/sync/linkedin/config", json={"email": "user@example.com", "password": "geheim"})
        sync_linkedin_module._state["status"] = "running"

        resp = client.post("/api/sync/linkedin/run")

        assert resp.status_code == 409

    def test_positiv_run_mit_target_app_id(self, client, db_session):
        app = application_factory(db_session)
        db_session.commit()
        client.post("/api/sync/linkedin/config", json={"email": "user@example.com", "password": "geheim"})

        captured = {}

        def _fake_run_sync_task(cfg_id, target_app_id=None):
            captured["target_app_id"] = target_app_id

        with patch.object(sync_linkedin_module, "_run_sync_task", new=_fake_run_sync_task):
            resp = client.post("/api/sync/linkedin/run", json={"target_app_id": app.id})

        assert resp.status_code == 200
        assert captured["target_app_id"] == app.id


class TestClearSession:
    def test_positiv_loescht_session_cookies(self, client, db_session):
        client.post("/api/sync/linkedin/config", json={"email": "user@example.com", "password": "geheim"})
        cfg = db_session.query(models.LinkedInSync).one()
        cfg.session_cookies = "[]"
        db_session.commit()

        resp = client.post("/api/sync/linkedin/clear-session")

        assert resp.status_code == 200
        db_session.refresh(cfg)
        assert cfg.session_cookies is None

    def test_negativ_ohne_konfiguration_ist_no_op(self, client):
        resp = client.post("/api/sync/linkedin/clear-session")
        assert resp.status_code == 200


class TestSubmitTwoFa:
    def test_negativ_ohne_ausstehende_2fa_liefert_409(self, client):
        resp = client.post("/api/sync/linkedin/submit-2fa", json={"code": "123456"})
        assert resp.status_code == 409

    def test_positiv_setzt_code_wenn_2fa_ansteht(self, client):
        sync_linkedin_module._state["status"] = "needs_2fa"

        resp = client.post("/api/sync/linkedin/submit-2fa", json={"code": " 123456 "})

        assert resp.status_code == 200
        assert sync_linkedin_module._2fa_code_input == "123456"


class TestSearchPeople:
    def test_negativ_ohne_linkedin_session_liefert_400(self, client, monkeypatch):
        async def _fake_ctx(user_id):
            return None

        monkeypatch.setattr("app.routers.sync_company._get_linkedin_context", _fake_ctx)

        resp = client.get("/api/sync/linkedin/people/search", params={"q": "Jane Doe"})

        assert resp.status_code == 400

    def test_positiv_liefert_kandidaten(self, client, monkeypatch):
        fake_browser = AsyncMock()
        fake_playwright = AsyncMock()

        async def _fake_ctx(user_id):
            return (fake_playwright, fake_browser, object())

        async def _fake_search(context, query, limit=10):
            return [{"name": "Jane Doe", "headline": "Recruiter at Contoso", "profile_url": "https://linkedin.com/in/jane"}]

        monkeypatch.setattr("app.routers.sync_company._get_linkedin_context", _fake_ctx)
        monkeypatch.setattr(sync_linkedin_module, "_linkedin_search_people", _fake_search)

        resp = client.get("/api/sync/linkedin/people/search", params={"q": "Jane Doe"})

        assert resp.status_code == 200
        assert resp.json()[0]["name"] == "Jane Doe"
        fake_browser.close.assert_awaited_once()
        fake_playwright.stop.assert_awaited_once()


class TestSyncOwnProfile:
    """POST /profile — caches scraped LinkedIn-profile text on the user row
    for ai/tasks.py's assessment prompt. Needs a real, DB-tracked user (the
    endpoint persists linkedin_profile_text via current_user), unlike the
    other tests in this file which use the plain `client` fixture's
    detached fake user — so this uses `real_auth_client` with a directly
    created+committed row and a real bearer token instead."""

    def _authed(self, db_session, real_auth_client, linkedin_url="https://linkedin.com/in/jane-doe"):
        from app.auth.security import create_access_token

        user = models.User(
            email="profile-sync@example.com", password_hash="x", email_verified=True,
            linkedin_url=linkedin_url,
        )
        db_session.add(user)
        db_session.commit()
        token = create_access_token(user.id)
        return user, {"Authorization": f"Bearer {token}"}

    def test_negativ_ohne_linkedin_url_liefert_400(self, real_auth_client, db_session):
        _, headers = self._authed(db_session, real_auth_client, linkedin_url=None)

        resp = real_auth_client.post("/api/sync/linkedin/profile", headers=headers)

        assert resp.status_code == 400

    def test_negativ_ohne_linkedin_session_liefert_400(self, real_auth_client, db_session, monkeypatch):
        _, headers = self._authed(db_session, real_auth_client)

        async def _fake_ctx(user_id):
            return None

        monkeypatch.setattr("app.routers.sync_company._get_linkedin_context", _fake_ctx)

        resp = real_auth_client.post("/api/sync/linkedin/profile", headers=headers)

        assert resp.status_code == 400

    def test_negativ_leeres_scrape_ergebnis_liefert_502(self, real_auth_client, db_session, monkeypatch):
        fake_browser = AsyncMock()
        fake_playwright = AsyncMock()
        _, headers = self._authed(db_session, real_auth_client)

        async def _fake_ctx(user_id):
            return (fake_playwright, fake_browser, object())

        async def _fake_scrape(context, url):
            return None

        monkeypatch.setattr("app.routers.sync_company._get_linkedin_context", _fake_ctx)
        monkeypatch.setattr(sync_linkedin_module, "scrape_own_profile", _fake_scrape)

        resp = real_auth_client.post("/api/sync/linkedin/profile", headers=headers)

        assert resp.status_code == 502
        fake_browser.close.assert_awaited_once()
        fake_playwright.stop.assert_awaited_once()

    def test_positiv_cached_profiltext_und_zeitstempel(self, real_auth_client, db_session, monkeypatch):
        fake_browser = AsyncMock()
        fake_playwright = AsyncMock()
        user, headers = self._authed(db_session, real_auth_client)

        async def _fake_ctx(user_id):
            return (fake_playwright, fake_browser, object())

        async def _fake_scrape(context, url):
            return "Senior Engineer at Contoso. 10 years experience."

        monkeypatch.setattr("app.routers.sync_company._get_linkedin_context", _fake_ctx)
        monkeypatch.setattr(sync_linkedin_module, "scrape_own_profile", _fake_scrape)

        resp = real_auth_client.post("/api/sync/linkedin/profile", headers=headers)

        assert resp.status_code == 200
        assert resp.json()["chars"] == len("Senior Engineer at Contoso. 10 years experience.")
        db_session.refresh(user)
        assert user.linkedin_profile_text == "Senior Engineer at Contoso. 10 years experience."
        assert user.linkedin_profile_synced_at is not None


class TestImportPeople:
    def test_positiv_importiert_neue_person(self, client, db_session):
        resp = client.post("/api/sync/linkedin/people/import", json={
            "candidates": [{"name": "Jane Doe", "headline": "Recruiter at Contoso", "profile_url": "https://linkedin.com/in/jane"}],
        })

        assert resp.status_code == 200
        assert resp.json() == {"imported": 1, "skipped": 0}
        contact = db_session.query(models.Contact).filter_by(name="Jane Doe").one()
        assert contact.firma == "Contoso"
        assert contact.rolle == "Recruiter"

    def test_positiv_bestehender_kontakt_wird_uebersprungen_und_verknuepft(self, client, db_session):
        app = application_factory(db_session)
        contact = contact_factory(db_session, name="Jane Doe", linkedin_url="https://linkedin.com/in/jane")
        db_session.commit()

        resp = client.post("/api/sync/linkedin/people/import", json={
            "candidates": [{"name": "Jane Doe", "profile_url": "https://linkedin.com/in/jane"}],
            "application_id": app.id,
        })

        assert resp.status_code == 200
        assert resp.json() == {"imported": 0, "skipped": 1}
        db_session.refresh(contact)
        assert contact in app.contacts

    def test_negativ_unbekannte_bewerbung_liefert_404(self, client):
        resp = client.post("/api/sync/linkedin/people/import", json={
            "candidates": [], "application_id": 999,
        })
        assert resp.status_code == 404


class TestSearchCompanies:
    def test_negativ_ohne_linkedin_session_liefert_400(self, client, monkeypatch):
        async def _fake_ctx(user_id):
            return None

        monkeypatch.setattr("app.routers.sync_company._get_linkedin_context", _fake_ctx)

        resp = client.get("/api/sync/linkedin/companies/search", params={"q": "Contoso"})

        assert resp.status_code == 400

    def test_positiv_liefert_kandidaten(self, client, monkeypatch):
        fake_browser = AsyncMock()
        fake_playwright = AsyncMock()

        async def _fake_ctx(user_id):
            return (fake_playwright, fake_browser, object())

        async def _fake_search(context, name, limit=5):
            return [{"name": "Contoso AG", "url": "https://linkedin.com/company/contoso", "snippet": "Software"}]

        monkeypatch.setattr("app.routers.sync_company._get_linkedin_context", _fake_ctx)
        monkeypatch.setattr("app.routers.sync_company._linkedin_search_candidates", _fake_search)

        resp = client.get("/api/sync/linkedin/companies/search", params={"q": "Contoso"})

        assert resp.status_code == 200
        assert resp.json()[0]["name"] == "Contoso AG"


class TestImportCompanies:
    def test_positiv_importiert_neues_profil(self, client, db_session):
        resp = client.post("/api/sync/linkedin/companies/import", json={
            "candidates": [{"name": "Contoso AG", "url": "https://linkedin.com/company/contoso"}],
        })

        assert resp.status_code == 200
        assert resp.json() == {"imported": 1, "skipped": 0}
        profile = db_session.query(models.CompanyProfile).filter_by(name_display="Contoso AG").one()
        assert profile.sync_status == "pending"
        assert profile.linkedin_company_url == "https://linkedin.com/company/contoso"

    def test_positiv_bestehendes_profil_wird_uebersprungen(self, client, db_session):
        from tests.factories import company_profile_factory
        from app.dedup import norm_firma

        company_profile_factory(db_session, name_display="Contoso AG", name_norm=norm_firma("Contoso AG"))
        db_session.commit()

        resp = client.post("/api/sync/linkedin/companies/import", json={
            "candidates": [{"name": "Contoso AG", "url": "https://linkedin.com/company/contoso"}],
        })

        assert resp.status_code == 200
        assert resp.json() == {"imported": 0, "skipped": 1}

    def test_negativ_leerer_name_wird_uebersprungen(self, client):
        resp = client.post("/api/sync/linkedin/companies/import", json={
            "candidates": [{"name": "   ", "url": "https://linkedin.com/company/x"}],
        })

        assert resp.status_code == 200
        assert resp.json() == {"imported": 0, "skipped": 1}
