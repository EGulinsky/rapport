"""L0 Unit -- _to_naive_utc() and _berlin_naive_to_utc_naive() in
sync_common.py: normalize datetimes for Event.datum_zeit so later comparisons
(same-day timeline sort) never risk a naive/aware TypeError.
"""
from datetime import datetime, timezone, timedelta

import pytest

from app.routers.sync_common import _to_naive_utc, _berlin_naive_to_utc_naive

pytestmark = pytest.mark.unit


class TestToNaiveUtc:
    def test_corner_case_none_bleibt_none(self):
        assert _to_naive_utc(None) is None

    def test_positiv_naive_datetime_bleibt_unveraendert(self):
        dt = datetime(2026, 6, 1, 14, 30, 0)
        result = _to_naive_utc(dt)
        assert result == dt
        assert result.tzinfo is None

    def test_positiv_aware_utc_wird_naiv(self):
        dt = datetime(2026, 6, 1, 14, 30, 0, tzinfo=timezone.utc)
        result = _to_naive_utc(dt)
        assert result == datetime(2026, 6, 1, 14, 30, 0)
        assert result.tzinfo is None

    def test_positiv_aware_nicht_utc_wird_nach_utc_konvertiert_und_naiv(self):
        # UTC+2 -> subtract 2h when converting to UTC.
        tz = timezone(timedelta(hours=2))
        dt = datetime(2026, 6, 1, 16, 30, 0, tzinfo=tz)
        result = _to_naive_utc(dt)
        assert result == datetime(2026, 6, 1, 14, 30, 0)
        assert result.tzinfo is None


class TestBerlinNaiveToUtcNaive:
    """Manually-entered Event.datum_zeit (timeline event edit form) is
    treated as an Europe/Berlin wall-clock reading, not UTC -- the opposite
    direction from _to_naive_utc(), which assumes UTC semantics for
    sync-derived timestamps."""

    def test_corner_case_none_bleibt_none(self):
        assert _berlin_naive_to_utc_naive(None) is None

    def test_positiv_sommerzeit_cest_ist_utc_plus_2(self):
        dt = datetime(2026, 7, 19, 14, 30, 0)
        result = _berlin_naive_to_utc_naive(dt)
        assert result == datetime(2026, 7, 19, 12, 30, 0)
        assert result.tzinfo is None

    def test_positiv_winterzeit_cet_ist_utc_plus_1(self):
        dt = datetime(2026, 1, 19, 14, 30, 0)
        result = _berlin_naive_to_utc_naive(dt)
        assert result == datetime(2026, 1, 19, 13, 30, 0)
        assert result.tzinfo is None

    def test_positiv_vorhandenes_tzinfo_wird_verworfen_und_als_berlin_interpretiert(self):
        # A client shouldn't send tzinfo, but if it did, treat the wall-clock
        # numbers as Berlin local time rather than trusting the tzinfo.
        dt = datetime(2026, 7, 19, 14, 30, 0, tzinfo=timezone.utc)
        result = _berlin_naive_to_utc_naive(dt)
        assert result == datetime(2026, 7, 19, 12, 30, 0)
