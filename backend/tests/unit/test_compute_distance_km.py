"""L0 Unit — _compute_distance_km() in routers/applications.py.
Pure function (no DB access needed) -- straight-line distance from the
account's home_lat/lng to the application's ort_lat/lng, both cached
geocodes (see _geocode_ort()/update_profile()'s geocoding).
"""
from types import SimpleNamespace

import pytest

from app.routers.applications import _compute_distance_km

pytestmark = pytest.mark.unit


def _app(ort_lat=None, ort_lng=None):
    return SimpleNamespace(ort_lat=ort_lat, ort_lng=ort_lng)


def _user(home_lat=None, home_lng=None):
    return SimpleNamespace(home_lat=home_lat, home_lng=home_lng)


class TestComputeDistanceKm:
    def test_positiv_beide_koordinaten_gesetzt(self):
        # Berlin -> Munich, ~504 km great-circle.
        app = _app(48.1351, 11.5820)
        user = _user(52.5200, 13.4050)
        result = _compute_distance_km(app, user)
        assert result is not None
        assert 490 < result < 520

    def test_negativ_kein_ort_koordinaten(self):
        app = _app(None, None)
        user = _user(52.52, 13.405)
        assert _compute_distance_km(app, user) is None

    def test_negativ_kein_home_location(self):
        app = _app(48.1351, 11.5820)
        user = _user(None, None)
        assert _compute_distance_km(app, user) is None

    def test_negativ_nur_lat_ohne_lng_gilt_als_fehlend(self):
        app = _app(48.1351, None)
        user = _user(52.52, 13.405)
        assert _compute_distance_km(app, user) is None
