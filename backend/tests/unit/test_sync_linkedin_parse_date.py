"""L0 Unit — _parse_date() in sync_linkedin.py: wandelt LinkedIn-Datumstexte
("Applied 3d ago", "Posted 2 weeks ago", "1/15/2025") in ein ISO-Datum
(YYYY-MM-DD) um. Das ist das Bewerbungsdatum (datum_bewerbung), das beim
LinkedIn-Import direkt in _find_or_create_application() übernommen wird —
ein Parsing-Fehler hier verfälscht die komplette Bewerbungs-Chronologie.
"""
from datetime import datetime, timedelta

import pytest

from app.routers.sync_linkedin import _parse_date

pytestmark = pytest.mark.unit


def _days_ago(n: int) -> str:
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")


class TestParseDateKurzform:
    def test_positiv_tage_kurzform(self):
        assert _parse_date("Applied 3d ago") == _days_ago(3)

    def test_positiv_wochen_kurzform(self):
        assert _parse_date("Applied 2w ago") == _days_ago(14)

    def test_positiv_monate_kurzform_mo(self):
        assert _parse_date("Applied 3mo ago") == _days_ago(90)

    def test_positiv_monate_kurzform_bare_m(self):
        # "2m ago" (ohne 'mo') muss ebenfalls als Monate interpretiert werden —
        # eigener Fallback-Zweig, da "mo"-Muster hier nicht matcht.
        assert _parse_date("Applied 2m ago") == _days_ago(60)

    def test_corner_case_mo_hat_vorrang_vor_bare_m(self):
        # "3mo" darf nicht als "3 Minuten/bare-m" fehlinterpretiert werden — das
        # \b nach "m" in der bare-m-Regel verhindert einen Treffer auf "3mo".
        assert _parse_date("Applied 1mo ago") == _days_ago(30)


class TestParseDateFrischeBewerbung:
    def test_positiv_just_now_liefert_heute(self):
        assert _parse_date("Applied just now") == datetime.now().strftime("%Y-%m-%d")

    def test_positiv_today_liefert_heute(self):
        assert _parse_date("Applied today") == datetime.now().strftime("%Y-%m-%d")

    def test_positiv_stunden_kurzform(self):
        assert _parse_date("Applied 3h ago") == (datetime.now() - timedelta(hours=3)).strftime("%Y-%m-%d")


class TestParseDateLangform:
    def test_positiv_tage_langform(self):
        assert _parse_date("Applied 3 days ago") == _days_ago(3)

    def test_positiv_wochen_langform(self):
        assert _parse_date("Applied 2 weeks ago") == _days_ago(14)

    def test_positiv_monate_langform(self):
        assert _parse_date("Applied 1 month ago") == _days_ago(30)


class TestParseDateAbsolut:
    def test_positiv_us_datumsformat_wird_zu_iso(self):
        assert _parse_date("Applied on 1/15/2025") == "2025-01-15"

    def test_positiv_us_datumsformat_ohne_fuehrende_null(self):
        assert _parse_date("3/5/2025") == "2025-03-05"

    def test_corner_case_zweistelliger_tag_und_monat(self):
        assert _parse_date("12/31/2024") == "2024-12-31"


class TestParseDateFehlerfaelle:
    def test_negativ_unparsebarer_text_liefert_none(self):
        assert _parse_date("Bewerbung eingereicht") is None

    def test_negativ_leerstring_liefert_none(self):
        assert _parse_date("") is None

    def test_negativ_nur_zahl_ohne_einheit_liefert_none(self):
        assert _parse_date("Applied 42") is None
