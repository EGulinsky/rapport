"""L0 — health.py: polls /health until status: ok or attempts run out,
mirroring ci.yml's deploy-job health-poll shape (30 attempts, 2s apart)."""
from unittest.mock import MagicMock, patch

import requests

from installer import health


class TestIsHealthy:
    def test_positiv_status_ok_liefert_true(self):
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"status": "ok"}
        with patch("requests.get", return_value=resp):
            assert health.is_healthy() is True

    def test_negativ_falscher_status_wert(self):
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"status": "starting"}
        with patch("requests.get", return_value=resp):
            assert health.is_healthy() is False

    def test_negativ_http_fehlercode(self):
        resp = MagicMock(status_code=500)
        resp.json.return_value = {}
        with patch("requests.get", return_value=resp):
            assert health.is_healthy() is False

    def test_negativ_verbindung_fehlgeschlagen(self):
        with patch("requests.get", side_effect=requests.RequestException("boom")):
            assert health.is_healthy() is False


class TestWaitForHealthy:
    def test_positiv_wird_beim_ersten_erfolgreichen_versuch_beendet(self):
        with patch.object(health, "is_healthy", side_effect=[False, False, True]), \
             patch("time.sleep") as mock_sleep:
            assert health.wait_for_healthy(attempts=5, interval_seconds=1) is True
        assert mock_sleep.call_count == 2

    def test_negativ_niemals_gesund_liefert_false_nach_allen_versuchen(self):
        with patch.object(health, "is_healthy", return_value=False), \
             patch("time.sleep") as mock_sleep:
            assert health.wait_for_healthy(attempts=3, interval_seconds=1) is False
        assert mock_sleep.call_count == 3
