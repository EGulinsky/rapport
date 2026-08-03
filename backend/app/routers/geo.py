"""Ortsautocomplete für das Bewerbungsfeld 'Ort'.

Nutzt Photon (komoot, https://photon.komoot.io) — einen kostenlosen,
schlüssellosen Geocoder auf Basis von OpenStreetMap-Daten, der ausdrücklich
für Autocomplete-/Search-as-you-type-Anwendungsfälle gebaut ist (im
Gegensatz zu Nominatim, dessen eigene Nutzungsrichtlinie von genau diesem
Anfragemuster abrät und Photon als Alternative empfiehlt). Anders als die
vorherige Nominatim-Anbindung wird das Ergebnis nicht auf Stadt+Land
zusammengekürzt, sondern liefert volle Adressen und POIs (Firmenstandorte,
Sehenswürdigkeiten etc.) — genau die Fähigkeit, die zuvor einen optionalen,
kostenpflichtigen Google-Places-Zweig nötig gemacht hätte. Der wurde deshalb
komplett entfernt, inkl. MapsSettings/Einstellungen → Karten.
"""
import httpx
from fastapi import APIRouter, Depends, Query

from app import models
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/api/geo", tags=["geo"])

PHOTON_URL = "https://photon.komoot.io/api/"
PHOTON_REVERSE_URL = "https://photon.komoot.io/reverse"
OSRM_ROUTE_URL = "https://router.project-osrm.org/route/v1/driving"


def _build_photon_label(props: dict) -> str | None:
    """Build a human-readable label from a Photon feature's `properties`
    dict, aiming for the same level of detail Google Places used to provide:
    a POI gets "Name, Street Housenumber, City, Country"; a plain address
    gets "Street Housenumber, City, Country"; a city/town result (where
    Photon's own "name" already equals the city) collapses to just
    "City, Country" -- matching the previous Nominatim-only behavior for
    that case. Returns None if there isn't enough data to build any label."""
    name = props.get("name")
    street = props.get("street")
    housenumber = props.get("housenumber")
    city = props.get("city") or props.get("town") or props.get("village") or props.get("locality")
    country = props.get("country")

    parts: list[str] = []
    if name and name != city and name != street:
        parts.append(name)
    if street:
        parts.append(f"{street} {housenumber}" if housenumber else street)
    if city:
        parts.append(city)
    if country:
        parts.append(country)

    label = ", ".join(parts)
    return label or name or city or None


async def driving_route(lat1: float, lng1: float, lat2: float, lng2: float) -> tuple[float, float] | None:
    """Car-navigation distance (km) and duration (minutes) between two
    points, for the distance-to-job feature (Application.drive_distance_km/
    drive_duration_min). Uses OSRM's free public routing server -- no API
    key needed. Best-effort: returns None on any failure, same philosophy as
    geocode_one() below -- a routing hiccup should just leave the cached
    value unset rather than raise. Note OSRM's coordinate order is lng,lat,
    opposite of every other API used in this file."""
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


async def _search_photon(term: str, lang: str = "de") -> list[dict]:
    async with httpx.AsyncClient(timeout=5) as client:
        try:
            resp = await client.get(
                PHOTON_URL,
                params={"q": term, "limit": 8, "lang": lang},
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            return []

    results: list[dict] = []
    seen: set[str] = set()
    for feature in data.get("features") or []:
        label = _build_photon_label(feature.get("properties") or {})
        if not label or label in seen:
            continue
        seen.add(label)
        results.append({"label": label})

    return results


@router.get("/search")
async def search_location(
    q: str = Query(..., min_length=2),
    current_user: models.User = Depends(get_current_user),
) -> list[dict]:
    term = q.strip()
    if not term:
        return []
    lang = current_user.ui_language if current_user.ui_language in ("de", "en") else "de"
    return await _search_photon(term, lang)


async def geocode_one(term: str) -> tuple[float, float] | None:
    """Forward-geocode a single free-text location to (lat, lng), for the
    distance-to-job feature (Application.ort_lat/lng, User.home_lat/lng).
    Best-effort: returns None on any failure or zero results rather than
    raising, since a location a user can already type/pick via the
    autocomplete (search_location above) should never block saving just
    because geocoding it failed."""
    term = term.strip()
    if not term:
        return None

    async with httpx.AsyncClient(timeout=5) as client:
        try:
            resp = await client.get(PHOTON_URL, params={"q": term, "limit": 1})
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            return None

    features = data.get("features") or []
    if not features:
        return None
    coords = features[0].get("geometry", {}).get("coordinates")
    if not coords or len(coords) != 2:
        return None
    lng, lat = coords  # GeoJSON coordinate order is lng,lat
    return (lat, lng)


async def reverse_geocode_one(lat: float, lng: float) -> str | None:
    """Reverse-geocode a lat/lng pair (from the browser's own geolocation) to
    a human-readable label, for the "use my location" button in Settings."""
    async with httpx.AsyncClient(timeout=5) as client:
        try:
            resp = await client.get(PHOTON_REVERSE_URL, params={"lat": lat, "lon": lng})
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            return None

    features = data.get("features") or []
    if not features:
        return None
    return _build_photon_label(features[0].get("properties") or {})


@router.get("/reverse")
async def reverse_geocode(
    lat: float = Query(...),
    lng: float = Query(...),
    current_user: models.User = Depends(get_current_user),
) -> dict:
    label = await reverse_geocode_one(lat, lng)
    return {"label": label}
