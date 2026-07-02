"""Ortsautocomplete für das Bewerbungsfeld 'Ort'.

Bevorzugt Google Places Autocomplete (liefert auch POIs/Firmenstandorte, nicht
nur Städte), sofern ein API-Key hinterlegt ist (Einstellungen → Karten). Der
Key bleibt serverseitig — das Frontend ruft ausschließlich diesen Proxy auf.
Ohne konfigurierten Key fällt die Suche auf Nominatim (OpenStreetMap) zurück,
das ohne API-Key nutzbar ist, aber keine POIs liefert.
"""
import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.ai.provider import decrypt_api_key
from app.database import get_db
from app import models

router = APIRouter(prefix="/api/geo", tags=["geo"])

GOOGLE_PLACES_AUTOCOMPLETE_URL = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "JobTracker/1.0 (personal single-user job application tracker)"


def _get_maps_api_key(db: Session) -> str | None:
    cfg = db.query(models.MapsSettings).first()
    if not cfg or not cfg.api_key_enc:
        return None
    try:
        return decrypt_api_key(cfg.api_key_enc)
    except Exception:
        return None


async def _search_google_places(term: str, api_key: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=5) as client:
        try:
            resp = await client.get(
                GOOGLE_PLACES_AUTOCOMPLETE_URL,
                params={"input": term, "key": api_key, "language": "de"},
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            return []

    if data.get("status") not in ("OK", "ZERO_RESULTS"):
        return []

    return [{"label": p["description"]} for p in data.get("predictions", []) if p.get("description")]


async def _search_nominatim(term: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=5) as client:
        try:
            resp = await client.get(
                NOMINATIM_URL,
                params={"q": term, "format": "jsonv2", "addressdetails": 1, "limit": 8},
                headers={"User-Agent": USER_AGENT},
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            return []

    results: list[dict] = []
    seen: set[str] = set()
    for item in data:
        address = item.get("address") or {}
        city = (
            address.get("city") or address.get("town") or address.get("village")
            or address.get("municipality") or item.get("name")
        )
        if not city:
            continue
        country = address.get("country")
        label = f"{city}, {country}" if country else city
        if label in seen:
            continue
        seen.add(label)
        results.append({"label": label})

    return results


@router.get("/search")
async def search_location(q: str = Query(..., min_length=2), db: Session = Depends(get_db)) -> list[dict]:
    term = q.strip()
    if not term:
        return []

    api_key = _get_maps_api_key(db)
    if api_key:
        return await _search_google_places(term, api_key)
    return await _search_nominatim(term)
