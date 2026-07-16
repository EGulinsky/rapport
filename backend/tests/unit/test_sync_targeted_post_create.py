"""L1 Unit — _do_post_create_sync() in sync_targeted.py: the orchestrator that
runs automatically right after a new Application is created (manual create,
LinkedIn single-link import, or the bulk LinkedIn scrape — see
applications.py's create_application() and sync_linkedin.py's _async_sync()).

_do_sync() and the LinkedIn per-app sync itself are already covered elsewhere
(tests/integration/test_sync_targeted_do_sync.py, tests/api/test_sync_linkedin_api.py)
— this file only tests the orchestration: is _do_sync() always called, is the
LinkedIn sync gated by skip_linkedin, and does a failure in either half never
propagate (this runs as a fire-and-forget background task; a raised exception
here would just vanish into FastAPI's background-task machinery, so it's not
"caught by the caller" so much as "must not matter either way" — but a clean
non-raising contract keeps behavior predictable for direct/test callers)."""
from __future__ import annotations

import pytest

from app.routers import sync_targeted

pytestmark = pytest.mark.unit


def _install_fakes(monkeypatch, *, do_sync_raises=False, li_raises=False):
    do_sync_calls: list[int] = []
    li_calls: list[int] = []

    async def fake_do_sync(app_id):
        do_sync_calls.append(app_id)
        if do_sync_raises:
            raise RuntimeError("do_sync boom")
        return {"created": 0, "processed": 0, "errors": []}

    async def fake_li(app_id):
        li_calls.append(app_id)
        if li_raises:
            raise RuntimeError("li boom")

    monkeypatch.setattr(sync_targeted, "_do_sync", fake_do_sync)
    monkeypatch.setattr("app.routers.sync_linkedin.run_individual_sync_if_idle", fake_li)
    return do_sync_calls, li_calls


class TestDoPostCreateSync:
    async def test_positiv_ruft_do_sync_immer_auf(self, monkeypatch):
        do_sync_calls, _ = _install_fakes(monkeypatch)

        await sync_targeted._do_post_create_sync(42, skip_linkedin=True)

        assert do_sync_calls == [42]

    async def test_positiv_ruft_linkedin_sync_auf_wenn_nicht_uebersprungen(self, monkeypatch):
        _, li_calls = _install_fakes(monkeypatch)

        await sync_targeted._do_post_create_sync(42, skip_linkedin=False)

        assert li_calls == [42]

    async def test_negativ_skip_linkedin_ueberspringt_linkedin_sync(self, monkeypatch):
        _, li_calls = _install_fakes(monkeypatch)

        await sync_targeted._do_post_create_sync(42, skip_linkedin=True)

        assert li_calls == []

    async def test_negativ_fehler_in_do_sync_bricht_linkedin_sync_nicht_ab(self, monkeypatch):
        do_sync_calls, li_calls = _install_fakes(monkeypatch, do_sync_raises=True)

        await sync_targeted._do_post_create_sync(42, skip_linkedin=False)  # must not raise

        assert do_sync_calls == [42]
        assert li_calls == [42]

    async def test_negativ_fehler_in_linkedin_sync_wird_geschluckt(self, monkeypatch):
        do_sync_calls, li_calls = _install_fakes(monkeypatch, li_raises=True)

        await sync_targeted._do_post_create_sync(42, skip_linkedin=False)  # must not raise

        assert do_sync_calls == [42]
        assert li_calls == [42]
