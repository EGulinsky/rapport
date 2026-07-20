"""L1 Unit — driving_route() + geocode_one()/reverse_geocode_one() in geo.py.

The distance-to-job feature (KanbanBoard/ApplicationModal) needs a one-time
forward geocode of Application.ort and User.home_location, a reverse
geocode for the "use my location" button in Settings, and a car-navigation
route (distance + duration) between the two -- replacing an earlier
straight-line/haversine calculation. Mocks httpx at the network boundary
(same pattern as test_sync_company.py's Wikidata tests), never hitting the
real Nominatim/Google/OSRM APIs.
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


class TestDrivingRouteGoogle:
    async def test_positiv_liefert_km_und_minuten(self):
        data = {
            "status": "OK",
            "rows": [{"elements": [{"status": "OK", "distance": {"value": 504000}, "duration": {"value": 18720}}]}],
        }

        async def fake_get(self, url, params=None, **kw):
            assert "distancematrix" in url
            return _mock_response(data)

        with patch("httpx.AsyncClient.get", new=fake_get):
            result = await driving_route(52.52, 13.405, 48.1351, 11.5820, "fake-key")

        assert result == (504.0, 312.0)

    async def test_negativ_element_status_nicht_ok_liefert_none(self):
        data = {"status": "OK", "rows": [{"elements": [{"status": "ZERO_RESULTS"}]}]}

        async def fake_get(self, url, params=None, **kw):
            return _mock_response(data)

        with patch("httpx.AsyncClient.get", new=fake_get):
            result = await driving_route(52.52, 13.405, 48.1351, 11.5820, "fake-key")

        assert result is None

    async def test_negativ_exception_wird_abgefangen(self):
        async def fake_get(self, url, params=None, **kw):
            raise httpx.ConnectError("kein Netz")

        with patch("httpx.AsyncClient.get", new=fake_get):
            result = await driving_route(52.52, 13.405, 48.1351, 11.5820, "fake-key")

        assert result is None


class TestDrivingRouteOsrmFallback:
    async def test_positiv_ohne_api_key_wird_osrm_genutzt(self):
        data = {"code": "Ok", "routes": [{"distance": 504000, "duration": 18720}]}

        async def fake_get(self, url, params=None, **kw):
            assert "router.project-osrm.org" in url
            # OSRM's coordinate order is lng,lat -- opposite of Google's.
            assert "13.405,52.52;11.582,48.1351" in url
            return _mock_response(data)

        with patch("httpx.AsyncClient.get", new=fake_get):
            result = await driving_route(52.52, 13.405, 48.1351, 11.582, None)

        assert result == (504.0, 312.0)

    async def test_negativ_code_nicht_ok_liefert_none(self):
        async def fake_get(self, url, params=None, **kw):
            return _mock_response({"code": "NoRoute", "routes": []})

        with patch("httpx.AsyncClient.get", new=fake_get):
            result = await driving_route(52.52, 13.405, 48.1351, 11.5820, None)

        assert result is None

    async def test_negativ_exception_wird_abgefangen(self):
        async def fake_get(self, url, params=None, **kw):
            raise httpx.ConnectError("kein Netz")

        with patch("httpx.AsyncClient.get", new=fake_get):
            result = await driving_route(52.52, 13.405, 48.1351, 11.5820, None)

        assert result is None


class TestGeocodeOneGoogle:
    async def test_positiv_liefert_lat_lng_aus_erstem_treffer(self):
        data = {"status": "OK", "results": [{"geometry": {"location": {"lat": 52.52, "lng": 13.405}}}]}

        async def fake_get(self, url, params=None, **kw):
            return _mock_response(data)

        with patch("httpx.AsyncClient.get", new=fake_get):
            result = await geocode_one("Berlin", "fake-key")

        assert result == (52.52, 13.405)

    async def test_negativ_zero_results_liefert_none(self):
        async def fake_get(self, url, params=None, **kw):
            return _mock_response({"status": "ZERO_RESULTS", "results": []})

        with patch("httpx.AsyncClient.get", new=fake_get):
            result = await geocode_one("Nirgendwostadt", "fake-key")

        assert result is None

    async def test_negativ_exception_wird_abgefangen(self):
        async def fake_get(self, url, params=None, **kw):
            raise httpx.ConnectError("kein Netz")

        with patch("httpx.AsyncClient.get", new=fake_get):
            result = await geocode_one("Berlin", "fake-key")

        assert result is None


class TestGeocodeOneNominatimFallback:
    async def test_positiv_ohne_api_key_wird_nominatim_genutzt(self):
        async def fake_get(self, url, params=None, **kw):
            assert "nominatim" in url
            return _mock_response([{"lat": "52.52", "lon": "13.405"}])

        with patch("httpx.AsyncClient.get", new=fake_get):
            result = await geocode_one("Berlin", None)

        assert result == (52.52, 13.405)

    async def test_negativ_leere_antwort_liefert_none(self):
        async def fake_get(self, url, params=None, **kw):
            return _mock_response([])

        with patch("httpx.AsyncClient.get", new=fake_get):
            result = await geocode_one("Nirgendwostadt", None)

        assert result is None

    async def test_negativ_leerer_term_wird_nicht_angefragt(self):
        result = await geocode_one("   ", None)
        assert result is None


class TestReverseGeocodeOne:
    async def test_positiv_google_formatted_address(self):
        data = {"status": "OK", "results": [{"formatted_address": "Berlin, Deutschland"}]}

        async def fake_get(self, url, params=None, **kw):
            return _mock_response(data)

        with patch("httpx.AsyncClient.get", new=fake_get):
            result = await reverse_geocode_one(52.52, 13.405, "fake-key")

        assert result == "Berlin, Deutschland"

    async def test_positiv_nominatim_stadt_und_land(self):
        async def fake_get(self, url, params=None, **kw):
            return _mock_response({"address": {"city": "Berlin", "country": "Deutschland"}})

        with patch("httpx.AsyncClient.get", new=fake_get):
            result = await reverse_geocode_one(52.52, 13.405, None)

        assert result == "Berlin, Deutschland"

    async def test_negativ_exception_wird_abgefangen(self):
        async def fake_get(self, url, params=None, **kw):
            raise httpx.ConnectError("kein Netz")

        with patch("httpx.AsyncClient.get", new=fake_get):
            result = await reverse_geocode_one(52.52, 13.405, None)

        assert result is None
