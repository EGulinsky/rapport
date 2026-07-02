"""Ortsautocomplete für das Bewerbungsfeld 'Ort' — Proxy zur Nominatim-API
(OpenStreetMap), da diese ohne API-Key nutzbar ist. Erfordert laut Nominatim-
Nutzungsrichtlinie einen aussagekräftigen User-Agent und maßvolle Anfragerate;
für eine Einzelnutzer-Anwendung mit debounced Suche unproblematisch.
"""
import httpx
from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/geo", tags=["geo"])

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "JobTracker/1.0 (personal single-user job application tracker)"


@router.get("/search")
async def search_location(q: str = Query(..., min_length=2)) -> list[dict]:
    term = q.strip()
    if not term:
        return []

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
