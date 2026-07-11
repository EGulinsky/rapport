"""L1 Unit — _run_source() in main.py: Schutz gegen konkurrierende Läufe
derselben Sync-Quelle und Exception-Schlucken (Hintergrund-Loop darf nicht
wegen eines einzelnen fehlgeschlagenen Sources abbrechen)."""
import pytest

from app.main import _RUNNING_SOURCES, _run_source

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clean_running_sources():
    _RUNNING_SOURCES.clear()
    yield
    _RUNNING_SOURCES.clear()


class TestRunSource:
    async def test_positiv_fuehrt_coroutine_aus_und_entfernt_lock_danach(self):
        called = []

        async def _coro():
            called.append(True)

        await _run_source("gmail", _coro)

        assert called == [True]
        assert "gmail" not in _RUNNING_SOURCES

    async def test_negativ_bereits_laufende_quelle_wird_uebersprungen(self):
        _RUNNING_SOURCES.add("gmail")
        called = []

        async def _coro():
            called.append(True)

        await _run_source("gmail", _coro)

        assert called == []

    async def test_negativ_exception_wird_geschluckt_und_lock_freigegeben(self):
        async def _coro():
            raise RuntimeError("boom")

        await _run_source("gmail", _coro)  # darf nicht propagieren

        assert "gmail" not in _RUNNING_SOURCES
