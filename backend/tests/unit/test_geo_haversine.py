"""L1 Unit — haversine_km() + geocode_one()/reverse_geocode_one() in geo.py.

The distance-to-job feature (KanbanBoard/ApplicationModal) needs a one-time
forward geocode of Application.ort and User.home_location, and a reverse
geocode for the "use my location" button in Settings. Mocks httpx at the
network boundary (same pattern as test_sync_company.py's Wikidata tests),
never hitting the real Nominatim/Google APIs.
"""
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.routers.geo import geocode_one, haversine_km, reverse_geocode_one

pytestmark = pytest.mark.unit


def _mock_response(json_data, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    resp.json.return_value = json_data
    return resp


class TestHaversineKm:
    def test_positiv_bekannte_distanz_berlin_muenchen(self):
        # Berlin (52.5200, 13.4050) -> Munich (48.1351, 11.5820), ~504 km great-circle.
        km = haversine_km(52.5200, 13.4050, 48.1351, 11.5820)
        assert 490 < km < 520

    def test_positiv_gleicher_punkt_ist_null(self):
        assert haversine_km(52.5, 13.4, 52.5, 13.4) == pytest.approx(0.0, abs=1e-9)

    def test_positiv_ist_symmetrisch(self):
        a = haversine_km(52.5200, 13.4050, 48.1351, 11.5820)
        b = haversine_km(48.1351, 11.5820, 52.5200, 13.4050)
        assert a == pytest.approx(b)


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
