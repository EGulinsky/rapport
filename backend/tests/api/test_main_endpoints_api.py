"""L2 API — /health und /api/sync/schedule/status in main.py."""
import pytest

pytestmark = pytest.mark.api


class TestHealth:
    def test_positiv_liefert_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestScheduleStatus:
    def test_positiv_liefert_intervall_und_laufende_quellen(self, client):
        resp = client.get("/api/sync/schedule/status")

        assert resp.status_code == 200
        body = resp.json()
        assert body["interval_minutes"] == 20
        assert isinstance(body["running_sources"], list)
