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
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/api/geo", tags=["geo"])

GOOGLE_PLACES_AUTOCOMPLETE_URL = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
GOOGLE_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
GOOGLE_DISTANCE_MATRIX_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"
OSRM_ROUTE_URL = "https://router.project-osrm.org/route/v1/driving"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "rapport/1.0 (personal single-user job application tracker)"


async def driving_route(lat1: float, lng1: float, lat2: float, lng2: float, api_key: str | None) -> tuple[float, float] | None:
    """Car-navigation distance (km) and duration (minutes) between two
    points, for the distance-to-job feature (Application.drive_distance_km/
    drive_duration_min). Replaces an earlier straight-line/haversine
    calculation, which understated real commute distance and gave no time
    estimate at all. Best-effort: returns None on any failure, same
    philosophy as geocode_one() below -- a routing hiccup should just leave
    the cached value unset rather than raise."""
    if api_key:
        async with httpx.AsyncClient(timeout=8) as client:
            try:
                resp = await client.get(
                    GOOGLE_DISTANCE_MATRIX_URL,
                    params={
                        "origins": f"{lat1},{lng1}",
                        "destinations": f"{lat2},{lng2}",
                        "mode": "driving",
                        "key": api_key,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            except (httpx.HTTPError, ValueError):
                return None
        if data.get("status") != "OK":
            return None
        rows = data.get("rows") or []
        elements = rows[0].get("elements") if rows else []
        if not elements or elements[0].get("status") != "OK":
            return None
        distance_m = elements[0].get("distance", {}).get("value")
        duration_s = elements[0].get("duration", {}).get("value")
        if distance_m is None or duration_s is None:
            return None
        return (distance_m / 1000, duration_s / 60)

    # Free fallback: OSRM's public routing server -- no API key needed, same
    # spirit as Nominatim for geocoding. Note OSRM's coordinate order is
    # lng,lat (opposite of every other API used in this file).
    async with httpx.AsyncClient(timeout=8) as client:
        try:
            resp = await client.get(
                f"{OSRM_ROUTE_URL}/{lng1},{lat1};{lng2},{lat2}",
                params={"overview": "false"},
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            return None
    if data.get("code") != "Ok":
        return None
    routes = data.get("routes") or []
    if not routes:
        return None
    distance_m = routes[0].get("distance")
    duration_s = routes[0].get("duration")
    if distance_m is None or duration_s is None:
        return None
    return (distance_m / 1000, duration_s / 60)


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
