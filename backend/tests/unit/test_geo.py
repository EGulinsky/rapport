"""L0 Unit — geo.py Ortsautocomplete: nutzt Photon (komoot), einen
kostenlosen, schlüssellosen Geocoder auf OpenStreetMap-Basis. HTTP-Aufrufe
gemockt; kein DB-Zugriff mehr nötig (im Unterschied zur früheren
Google-Places-Variante, die pro Request einen Maps-API-Key aus der DB
gelesen hat)."""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.routers.geo import search_location
from app import models

pytestmark = pytest.mark.unit

_FAKE_USER = models.User(id=1, email="test-geo@example.com", password_hash="x", email_verified=True, ui_language="de")

_PHOTON_RESPONSE_POI = {
    "features": [
        {
            "properties": {
                "name": "Contoso AG", "street": "Musterstraße", "housenumber": "1",
                "city": "München", "country": "Deutschland",
            },
            "geometry": {"coordinates": [11.5820, 48.1351]},
        },
        {
            "properties": {"name": "München", "state": "Bayern", "country": "Deutschland"},
            "geometry": {"coordinates": [11.5820, 48.1351]},
        },
    ],
}

_PHOTON_RESPONSE_CITY_ONLY = {
    "features": [
        {
            "properties": {"name": "München", "state": "Bayern", "country": "Deutschland"},
            "geometry": {"coordinates": [11.5820, 48.1351]},
        },
    ],
}


def _mock_response(json_data):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


class TestSearchLocationPhoton:
    async def test_positiv_liefert_poi_und_stadt(self):
        # Regression target for this feature: Photon returns concrete POIs
        # (here a company address), not just city names like the previous
        # Nominatim-only implementation did.
        with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=_mock_response(_PHOTON_RESPONSE_POI))):
            results = await search_location(q="Contoso München", current_user=_FAKE_USER)

        assert results == [
            {"label": "Contoso AG, Musterstraße 1, München, Deutschland"},
            {"label": "München, Deutschland"},
        ]

    async def test_positiv_reine_stadtsuche_liefert_stadt_und_land(self):
        with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=_mock_response(_PHOTON_RESPONSE_CITY_ONLY))):
            results = await search_location(q="München", current_user=_FAKE_USER)

        assert results == [{"label": "München, Deutschland"}]

    async def test_negativ_leere_suche_ruft_keine_api_auf(self):
        with patch("httpx.AsyncClient.get", new=AsyncMock()) as mock_get:
            results = await search_location(q="  ", current_user=_FAKE_USER)

        assert results == []
        mock_get.assert_not_called()

    async def test_negativ_http_fehler_liefert_leere_liste(self):
        with patch("httpx.AsyncClient.get", new=AsyncMock(side_effect=httpx.ConnectError("down"))):
            results = await search_location(q="Berlin", current_user=_FAKE_USER)

        assert results == []

    async def test_corner_case_keine_treffer_liefert_leere_liste(self):
        with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=_mock_response({"features": []}))):
            results = await search_location(q="Xyzxyzxyz", current_user=_FAKE_USER)

        assert results == []

    async def test_positiv_englische_ui_sprache_wird_an_photon_durchgereicht(self):
        captured = {}

        async def fake_get(self, url, params=None, **kw):
            captured.update(params or {})
            return _mock_response(_PHOTON_RESPONSE_CITY_ONLY)

        en_user = models.User(id=1, email="test-geo@example.com", password_hash="x", email_verified=True, ui_language="en")
        with patch("httpx.AsyncClient.get", new=fake_get):
            await search_location(q="Munich", current_user=en_user)

        assert captured["lang"] == "en"
