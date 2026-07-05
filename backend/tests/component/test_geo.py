"""L1 Component — geo.py Ortsautocomplete: wählt Google Places (falls ein
Maps-API-Key hinterlegt ist) oder fällt auf Nominatim zurück. HTTP-Aufrufe
gemockt, DB-Zugriff (MapsSettings) läuft gegen die echte Test-DB.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.ai.provider import encrypt_api_key
from app.routers.geo import search_location
from app import models

pytestmark = pytest.mark.component

_NOMINATIM_RESPONSE = [
    {
        "name": "München",
        "display_name": "München, Bayern, Deutschland",
        "address": {"city": "München", "state": "Bayern", "country": "Deutschland"},
    },
]

_GOOGLE_RESPONSE = {
    "status": "OK",
    "predictions": [
        {"description": "Contoso AG, Musterstraße 1, München, Deutschland", "place_id": "abc"},
        {"description": "München, Deutschland", "place_id": "def"},
    ],
}


def _mock_response(json_data):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


def _with_maps_key(db, key="AIzaTestKey"):
    db.add(models.MapsSettings(api_key_enc=encrypt_api_key(key)))
    db.commit()


class TestSearchLocationRouting:
    async def test_positiv_ohne_key_faellt_auf_nominatim_zurueck(self, db_session):
        with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=_mock_response(_NOMINATIM_RESPONSE))):
            results = await search_location(q="München", db=db_session)

        assert results == [{"label": "München, Deutschland"}]

    async def test_positiv_mit_key_nutzt_google_places_und_liefert_pois(self, db_session):
        # Regressionsziel dieses Features: Google Places liefert auch konkrete POIs
        # (hier ein Firmenstandort), nicht nur Städtenamen wie Nominatim.
        _with_maps_key(db_session)

        with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=_mock_response(_GOOGLE_RESPONSE))):
            results = await search_location(q="Contoso München", db=db_session)

        assert results == [
            {"label": "Contoso AG, Musterstraße 1, München, Deutschland"},
            {"label": "München, Deutschland"},
        ]

    async def test_negativ_leere_suche_ruft_keine_api_auf(self, db_session):
        with patch("httpx.AsyncClient.get", new=AsyncMock()) as mock_get:
            results = await search_location(q="  ", db=db_session)

        assert results == []
        mock_get.assert_not_called()

    async def test_negativ_google_http_fehler_liefert_leere_liste(self, db_session):
        _with_maps_key(db_session)

        with patch("httpx.AsyncClient.get", new=AsyncMock(side_effect=httpx.ConnectError("down"))):
            results = await search_location(q="Berlin", db=db_session)

        assert results == []

    async def test_corner_case_google_zero_results_liefert_leere_liste(self, db_session):
        _with_maps_key(db_session)
        data = {"status": "ZERO_RESULTS", "predictions": []}

        with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=_mock_response(data))):
            results = await search_location(q="Xyzxyzxyz", db=db_session)

        assert results == []

    async def test_corner_case_kaputter_gespeicherter_key_faellt_auf_nominatim_zurueck(self, db_session):
        # Ein nicht entschlüsselbarer Key (z.B. nach Fernet-Secret-Rotation) darf die
        # Ortssuche nicht komplett brechen — Fallback auf Nominatim statt 500er.
        db_session.add(models.MapsSettings(api_key_enc="not-a-valid-fernet-token"))
        db_session.commit()

        with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=_mock_response(_NOMINATIM_RESPONSE))):
            results = await search_location(q="München", db=db_session)

        assert results == [{"label": "München, Deutschland"}]
