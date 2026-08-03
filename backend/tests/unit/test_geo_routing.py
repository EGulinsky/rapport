"""L1 Unit — driving_route() + geocode_one()/reverse_geocode_one() in geo.py.

The distance-to-job feature (KanbanBoard/ApplicationModal) needs a one-time
forward geocode of Application.ort and User.home_location, a reverse
geocode for the "use my location" button in Settings, and a car-navigation
route (distance + duration) between the two. driving_route() uses OSRM's
free public routing server; geocode_one()/reverse_geocode_one() use Photon
(komoot), a free, keyless OpenStreetMap-based geocoder. Mocks httpx at the
network boundary (same pattern as test_sync_company.py's Wikidata tests),
never hitting the real OSRM/Photon APIs.
"""
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.routers.geo import driving_route, geocode_one, reverse_geocode_one

pytestmark = pytest.mark.unit


def _mock_response(json_data, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    resp.json.return_value = json_data
    return resp


class TestDrivingRoute:
    async def test_positiv_liefert_km_und_minuten(self):
        data = {"code": "Ok", "routes": [{"distance": 504000, "duration": 18720}]}

        async def fake_get(self, url, params=None, **kw):
            assert "router.project-osrm.org" in url
            # OSRM's coordinate order is lng,lat -- opposite of every other
            # API used in this file.
            assert "13.405,52.52;11.582,48.1351" in url
            return _mock_response(data)

        with patch("httpx.AsyncClient.get", new=fake_get):
            result = await driving_route(52.52, 13.405, 48.1351, 11.582)

        assert result == (504.0, 312.0)

    async def test_negativ_code_nicht_ok_liefert_none(self):
        async def fake_get(self, url, params=None, **kw):
            return _mock_response({"code": "NoRoute", "routes": []})

        with patch("httpx.AsyncClient.get", new=fake_get):
            result = await driving_route(52.52, 13.405, 48.1351, 11.5820)

        assert result is None

    async def test_negativ_exception_wird_abgefangen(self):
        async def fake_get(self, url, params=None, **kw):
            raise httpx.ConnectError("kein Netz")

        with patch("httpx.AsyncClient.get", new=fake_get):
            result = await driving_route(52.52, 13.405, 48.1351, 11.5820)

        assert result is None


class TestGeocodeOne:
    async def test_positiv_liefert_lat_lng_aus_erstem_treffer(self):
        # Photon/GeoJSON coordinate order is lng,lat.
        data = {"features": [{"geometry": {"coordinates": [13.405, 52.52]}}]}

        async def fake_get(self, url, params=None, **kw):
            assert "photon.komoot.io" in url
            return _mock_response(data)

        with patch("httpx.AsyncClient.get", new=fake_get):
            result = await geocode_one("Berlin")

        assert result == (52.52, 13.405)

    async def test_negativ_keine_treffer_liefert_none(self):
        async def fake_get(self, url, params=None, **kw):
            return _mock_response({"features": []})

        with patch("httpx.AsyncClient.get", new=fake_get):
            result = await geocode_one("Nirgendwostadt")

        assert result is None

    async def test_negativ_exception_wird_abgefangen(self):
        async def fake_get(self, url, params=None, **kw):
            raise httpx.ConnectError("kein Netz")

        with patch("httpx.AsyncClient.get", new=fake_get):
            result = await geocode_one("Berlin")

        assert result is None

    async def test_negativ_leerer_term_wird_nicht_angefragt(self):
        result = await geocode_one("   ")
        assert result is None


class TestReverseGeocodeOne:
    async def test_positiv_baut_label_aus_stadt_und_land(self):
        data = {"features": [{"properties": {"name": "Berlin", "country": "Deutschland"}}]}

        async def fake_get(self, url, params=None, **kw):
            assert "photon.komoot.io/reverse" in url
            return _mock_response(data)

        with patch("httpx.AsyncClient.get", new=fake_get):
            result = await reverse_geocode_one(52.52, 13.405)

        assert result == "Berlin, Deutschland"

    async def test_negativ_keine_treffer_liefert_none(self):
        async def fake_get(self, url, params=None, **kw):
            return _mock_response({"features": []})

        with patch("httpx.AsyncClient.get", new=fake_get):
            result = await reverse_geocode_one(52.52, 13.405)

        assert result is None

    async def test_negativ_exception_wird_abgefangen(self):
        async def fake_get(self, url, params=None, **kw):
            raise httpx.ConnectError("kein Netz")

        with patch("httpx.AsyncClient.get", new=fake_get):
            result = await reverse_geocode_one(52.52, 13.405)

        assert result is None
