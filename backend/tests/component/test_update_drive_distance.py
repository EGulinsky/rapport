"""L1 Component — _update_drive_distance() in routers/applications.py.
Caches the car-navigation distance/duration from the account's home
location to an application's ort (see Application.drive_distance_km's
docstring in models.py) -- needs a real DB session for _get_maps_api_key()
(queries MapsSettings), so this is component- rather than unit-level;
driving_route() itself is mocked at the module boundary.
"""
import pytest

from app import models
from app.routers.applications import _update_drive_distance

pytestmark = pytest.mark.component


def _app(ort_lat=None, ort_lng=None):
    return models.Application(firma="Test GmbH", rolle="Engineer", ort_lat=ort_lat, ort_lng=ort_lng)


def _user(db_session, home_lat=None, home_lng=None):
    user = models.User(email="test@example.com", password_hash="x", email_verified=True,
                        home_lat=home_lat, home_lng=home_lng)
    db_session.add(user)
    db_session.flush()
    return user


class TestUpdateDriveDistance:
    async def test_positiv_beide_koordinaten_gesetzt_cached_route(self, db_session, monkeypatch):
        app = _app(48.1351, 11.5820)
        user = _user(db_session, 52.5200, 13.4050)

        async def fake_driving_route(lat1, lng1, lat2, lng2, api_key):
            assert (lat1, lng1) == (52.5200, 13.4050)
            assert (lat2, lng2) == (48.1351, 11.5820)
            return (504.0, 312.0)
        monkeypatch.setattr("app.routers.applications.driving_route", fake_driving_route)

        await _update_drive_distance(db_session, app, user)

        assert app.drive_distance_km == 504.0
        assert app.drive_duration_min == 312.0

    async def test_negativ_kein_ort_koordinaten_setzt_none(self, db_session, monkeypatch):
        app = _app(None, None)
        user = _user(db_session, 52.52, 13.405)
        called = False

        async def fake_driving_route(*a, **kw):
            nonlocal called
            called = True
            return (1.0, 1.0)
        monkeypatch.setattr("app.routers.applications.driving_route", fake_driving_route)

        await _update_drive_distance(db_session, app, user)

        assert app.drive_distance_km is None
        assert app.drive_duration_min is None
        assert called is False

    async def test_negativ_kein_home_location_setzt_none(self, db_session, monkeypatch):
        app = _app(48.1351, 11.5820)
        user = _user(db_session, None, None)

        await _update_drive_distance(db_session, app, user)

        assert app.drive_distance_km is None
        assert app.drive_duration_min is None

    async def test_negativ_nur_lat_ohne_lng_gilt_als_fehlend(self, db_session, monkeypatch):
        app = _app(48.1351, None)
        user = _user(db_session, 52.52, 13.405)

        await _update_drive_distance(db_session, app, user)

        assert app.drive_distance_km is None
        assert app.drive_duration_min is None

    async def test_negativ_routing_fehlschlag_laesst_koordinaten_leer(self, db_session, monkeypatch):
        app = _app(48.1351, 11.5820)
        app.drive_distance_km = 999.0  # stale value from a previous run
        user = _user(db_session, 52.52, 13.405)

        async def fake_driving_route(*a, **kw):
            return None
        monkeypatch.setattr("app.routers.applications.driving_route", fake_driving_route)

        await _update_drive_distance(db_session, app, user)

        assert app.drive_distance_km is None
        assert app.drive_duration_min is None
