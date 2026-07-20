"""Ortsautocomplete für das Bewerbungsfeld 'Ort'.

Bevorzugt Google Places Autocomplete (liefert auch POIs/Firmenstandorte, nicht
nur Städte), sofern ein API-Key hinterlegt ist (Einstellungen → Karten). Der
Key bleibt serverseitig — das Frontend ruft ausschließlich diesen Proxy auf.
Ohne konfigurierten Key fällt die Suche auf Nominatim (OpenStreetMap) zurück,
das ohne API-Key nutzbar ist, aber keine POIs liefert.
"""
import math

import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.ai.provider import decrypt_api_key
from app.database import get_db
from app import models
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/api/geo", tags=["geo"])

GOOGLE_PLACES_AUTOCOMPLETE_URL = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
GOOGLE_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "rapport/1.0 (personal single-user job application tracker)"


_EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle (straight-line) distance in km -- not driving distance,
    which would need a Distance Matrix API call (and its own quota/cost) per
    application rather than a one-time geocode reused for every calculation."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return _EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _get_maps_api_key(db: Session, user_id: int) -> str | None:
    cfg = db.query(models.MapsSettings).filter_by(user_id=user_id).first()
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
async def search_location(
    q: str = Query(..., min_length=2),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> list[dict]:
    term = q.strip()
    if not term:
        return []

    api_key = _get_maps_api_key(db, current_user.id)
    if api_key:
        return await _search_google_places(term, api_key)
    return await _search_nominatim(term)


async def geocode_one(term: str, api_key: str | None) -> tuple[float, float] | None:
    """Forward-geocode a single free-text location to (lat, lng), for the
    distance-to-job feature (Application.ort_lat/lng, User.home_lat/lng).
    Best-effort: returns None on any failure or zero results rather than
    raising, since a location a user can already type/pick via the
    autocomplete (search_location above) should never block saving just
    because geocoding it failed."""
    term = term.strip()
    if not term:
        return None

    if api_key:
        async with httpx.AsyncClient(timeout=5) as client:
            try:
                resp = await client.get(
                    GOOGLE_GEOCODE_URL, params={"address": term, "key": api_key},
                )
                resp.raise_for_status()
                data = resp.json()
            except (httpx.HTTPError, ValueError):
                return None
        if data.get("status") != "OK":
            return None
        results = data.get("results") or []
        if not results:
            return None
        loc = results[0].get("geometry", {}).get("location") or {}
        if loc.get("lat") is None or loc.get("lng") is None:
            return None
        return (loc["lat"], loc["lng"])

    async with httpx.AsyncClient(timeout=5) as client:
        try:
            resp = await client.get(
                NOMINATIM_URL,
                params={"q": term, "format": "jsonv2", "limit": 1},
                headers={"User-Agent": USER_AGENT},
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            return None
    if not data:
        return None
    try:
        return (float(data[0]["lat"]), float(data[0]["lon"]))
    except (KeyError, ValueError, TypeError):
        return None


async def reverse_geocode_one(lat: float, lng: float, api_key: str | None) -> str | None:
    """Reverse-geocode a lat/lng pair (from the browser's own geolocation) to
    a human-readable label, for the "use my location" button in Settings."""
    if api_key:
        async with httpx.AsyncClient(timeout=5) as client:
            try:
                resp = await client.get(
                    GOOGLE_GEOCODE_URL, params={"latlng": f"{lat},{lng}", "key": api_key},
                )
                resp.raise_for_status()
                data = resp.json()
            except (httpx.HTTPError, ValueError):
                return None
        if data.get("status") != "OK":
            return None
        results = data.get("results") or []
        return results[0]["formatted_address"] if results and results[0].get("formatted_address") else None

    async with httpx.AsyncClient(timeout=5) as client:
        try:
            resp = await client.get(
                NOMINATIM_REVERSE_URL,
                params={"lat": lat, "lon": lng, "format": "jsonv2"},
                headers={"User-Agent": USER_AGENT},
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            return None
    address = data.get("address") or {}
    city = (
        address.get("city") or address.get("town") or address.get("village")
        or address.get("municipality")
    )
    country = address.get("country")
    if city and country:
        return f"{city}, {country}"
    return data.get("display_name")


@router.get("/reverse")
async def reverse_geocode(
    lat: float = Query(...),
    lng: float = Query(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> dict:
    api_key = _get_maps_api_key(db, current_user.id)
    label = await reverse_geocode_one(lat, lng, api_key)
    return {"label": label}
