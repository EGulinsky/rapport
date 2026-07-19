"""L0 Unit -- _to_naive_utc() in sync_common.py: normalizes a possibly-aware
datetime into a naive UTC datetime for Event.datum_zeit, so later comparisons
(same-day timeline sort) never risk a naive/aware TypeError.
"""
from datetime import datetime, timezone, timedelta

import pytest

from app.routers.sync_common import _to_naive_utc

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
