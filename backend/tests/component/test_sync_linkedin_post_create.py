"""L2 Component — run_individual_sync_if_idle() and _sync_newly_created_apps()
in sync_linkedin.py: the two post-create-sync helpers, called automatically
right after a new Application is created (see applications.py's
create_application(), sync_targeted._do_post_create_sync(), and
sync_linkedin.py's _async_sync() batch branch for call sites).

_async_sync() itself (the real Playwright-driven scraper) is deliberately
not exercised here — it's mocked at the boundary, same approach as
tests/api/test_sync_linkedin_api.py."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import app.routers.sync_linkedin as sync_linkedin_module
from app import models
from tests.factories import application_factory

pytestmark = pytest.mark.component


@pytest.fixture(autouse=True)
def _reset_state():
    sync_linkedin_module._reset_state()
    yield
    sync_linkedin_module._reset_state()


class TestRunIndividualSyncIfIdle:
    async def test_negativ_no_op_ohne_linkedin_konfiguration(self, db_session, monkeypatch):
        async_sync_mock = AsyncMock()
        monkeypatch.setattr(sync_linkedin_module, "_async_sync", async_sync_mock)

        await sync_linkedin_module.run_individual_sync_if_idle(1)

        async_sync_mock.assert_not_called()

    async def test_negativ_no_op_wenn_bereits_ein_sync_laeuft(self, db_session, monkeypatch):
        db_session.add(models.LinkedInSync(email="user@example.com", password_enc="enc"))
        db_session.commit()
        async_sync_mock = AsyncMock()
        monkeypatch.setattr(sync_linkedin_module, "_async_sync", async_sync_mock)
        sync_linkedin_module._state["status"] = "running"

        await sync_linkedin_module.run_individual_sync_if_idle(1)

        async_sync_mock.assert_not_called()

    async def test_positiv_startet_individuellen_sync_wenn_idle_und_konfiguriert(self, db_session, monkeypatch):
        cfg = models.LinkedInSync(email="user@example.com", password_enc="enc")
        db_session.add(cfg)
        db_session.commit()
        async_sync_mock = AsyncMock()
        monkeypatch.setattr(sync_linkedin_module, "_async_sync", async_sync_mock)

        await sync_linkedin_module.run_individual_sync_if_idle(7)

        async_sync_mock.assert_awaited_once_with(cfg.id, 7)

    async def test_positiv_setzt_state_auf_running_vor_dem_sync(self, db_session, monkeypatch):
        db_session.add(models.LinkedInSync(email="user@example.com", password_enc="enc"))
        db_session.commit()
        seen_status = {}

        async def fake_async_sync(cfg_id, app_id):
            seen_status["status"] = sync_linkedin_module._state["status"]

        monkeypatch.setattr(sync_linkedin_module, "_async_sync", fake_async_sync)

        await sync_linkedin_module.run_individual_sync_if_idle(7)

        assert seen_status["status"] == "running"


class TestSyncNewlyCreatedApps:
    async def test_positiv_ruft_do_sync_fuer_jede_app_auf(self, db_session, monkeypatch):
        app1 = application_factory(db_session, firma="A GmbH")
        app2 = application_factory(db_session, firma="B GmbH")
        db_session.commit()
        calls: list[int] = []

        async def fake_do_sync(app_id):
            calls.append(app_id)
            return {"created": 0, "processed": 0, "errors": []}

        monkeypatch.setattr("app.routers.sync_targeted._do_sync", fake_do_sync)

        await sync_linkedin_module._sync_newly_created_apps([app1.id, app2.id])

        assert calls == [app1.id, app2.id]

    async def test_negativ_leere_liste_ist_no_op(self, monkeypatch):
        do_sync_mock = AsyncMock()
        monkeypatch.setattr("app.routers.sync_targeted._do_sync", do_sync_mock)

        await sync_linkedin_module._sync_newly_created_apps([])

        do_sync_mock.assert_not_called()

    async def test_negativ_fehler_bei_einer_app_stoppt_nicht_die_naechste(self, db_session, monkeypatch):
        app1 = application_factory(db_session, firma="A GmbH")
        app2 = application_factory(db_session, firma="B GmbH")
        db_session.commit()
        calls: list[int] = []

        async def flaky_do_sync(app_id):
            calls.append(app_id)
            if app_id == app1.id:
                raise RuntimeError("boom")
            return {"created": 0, "processed": 0, "errors": []}

        monkeypatch.setattr("app.routers.sync_targeted._do_sync", flaky_do_sync)

        await sync_linkedin_module._sync_newly_created_apps([app1.id, app2.id])  # must not raise

        assert calls == [app1.id, app2.id]
