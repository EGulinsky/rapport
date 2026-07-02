"""L0 Unit — geo.py Ortsautocomplete (Nominatim-Proxy), HTTP-Aufruf gemockt."""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.routers.geo import search_location

pytestmark = pytest.mark.unit

_NOMINATIM_RESPONSE = [
    {
        "name": "München",
        "display_name": "München, Bayern, Deutschland",
        "address": {"city": "München", "state": "Bayern", "country": "Deutschland"},
    },
    {
        "name": "München",
        "display_name": "München (Kreis), Bayern, Deutschland",
        "address": {"city": "München", "state": "Bayern", "country": "Deutschland"},
    },
]


def _mock_response(json_data, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


class TestSearchLocation:
    async def test_positiv_ergebnisse_werden_zu_label_gemappt(self):
        with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=_mock_response(_NOMINATIM_RESPONSE))):
            results = await search_location(q="München")

        assert results == [{"label": "München, Deutschland"}]

    async def test_positiv_duplikate_werden_entfernt(self):
        # Beide Nominatim-Treffer oben mappen auf dasselbe Label "München, Deutschland" —
        # ohne Dedup würde die Autocomplete-Liste denselben Ort doppelt anzeigen.
        with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=_mock_response(_NOMINATIM_RESPONSE))):
            results = await search_location(q="München")

        assert len(results) == 1

    async def test_negativ_leere_suche_ruft_api_nicht_auf(self):
        with patch("httpx.AsyncClient.get", new=AsyncMock()) as mock_get:
            results = await search_location(q="  ")

        assert results == []
        mock_get.assert_not_called()

    async def test_negativ_http_fehler_liefert_leere_liste(self):
        with patch("httpx.AsyncClient.get", new=AsyncMock(side_effect=httpx.ConnectError("down"))):
            results = await search_location(q="Berlin")

        assert results == []

    async def test_corner_case_eintrag_ohne_stadt_wird_uebersprungen(self):
        data = [{"display_name": "Irgendwo im Nirgendwo", "address": {}}]
        with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=_mock_response(data))):
            results = await search_location(q="Nirgendwo")

        assert results == []
