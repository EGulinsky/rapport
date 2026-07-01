"""L0 Unit — routers/analytics.py: Stufen-Konversion, Engpass-Erkennung, Rollen-Kategorisierung."""
import pytest

from app.routers.analytics import _categorize_role, _find_bottleneck, _stage_conversions

pytestmark = pytest.mark.unit


def _funnel_entry(status: str, count: int) -> dict:
    return {"status": status, "label": status, "count": count, "pct": 0.0}


class TestStageConversions:
    def test_positiv_berechnet_stufe_zu_stufe_rate(self):
        funnel = [_funnel_entry("applied", 100), _funnel_entry("hr", 20)]

        result = _stage_conversions(funnel)

        assert len(result) == 1
        assert result[0]["rate"] == 0.2
        assert result[0]["drop_off"] == 80

    def test_corner_case_leere_ausgangsstufe_kein_zerodiv(self):
        funnel = [_funnel_entry("applied", 0), _funnel_entry("hr", 0)]

        result = _stage_conversions(funnel)

        assert result[0]["rate"] == 0.0
        assert result[0]["drop_off"] == 0

    def test_positiv_mehrere_stufen(self):
        funnel = [_funnel_entry("a", 100), _funnel_entry("b", 50), _funnel_entry("c", 25)]

        result = _stage_conversions(funnel)

        assert len(result) == 2
        assert result[0]["rate"] == 0.5
        assert result[1]["rate"] == 0.5


class TestFindBottleneck:
    def test_positiv_groesster_absoluter_verlust_gewinnt_nicht_niedrigste_rate(self):
        # Regressionsfall: eine Stufe mit 0% Rate aber nur 1 verlorener
        # Bewerbung darf nicht als "der" Engpass gelten, wenn eine andere
        # Stufe 138 Bewerbungen verliert (nur 16% Rate, aber der eigentliche
        # Hauptverlust). Absoluter drop_off statt Rate ist robust gegen
        # Rauschen in dünn besetzten späten Pipeline-Stufen.
        conversions = [
            {"from_status": "applied", "to_status": "hr", "rate": 0.16, "drop_off": 138},
            {"from_status": "negotiating", "to_status": "signed", "rate": 0.0, "drop_off": 1},
        ]

        result = _find_bottleneck(conversions)

        assert result["from_status"] == "applied"

    def test_negativ_keine_kandidaten_liefert_none(self):
        conversions = [{"from_status": "a", "to_status": "b", "rate": 1.0, "drop_off": 0}]

        assert _find_bottleneck(conversions) is None

    def test_corner_case_leere_liste(self):
        assert _find_bottleneck([]) is None


class TestCategorizeRole:
    def test_positiv_fuehrung_erkannt(self):
        assert _categorize_role("Head of Engineering") == "Führung"
        assert _categorize_role("Bereichsleitung Software Solutions (m/w/d)") == "Führung"

    def test_positiv_senior_erkannt(self):
        assert _categorize_role("Senior Software Engineer") == "Senior (Fachexperte)"

    def test_negativ_sonstige_als_fallback(self):
        assert _categorize_role("Software Engineer") == "Sonstige"

    def test_fehleingabe_none_crasht_nicht(self):
        assert _categorize_role(None) == "Sonstige"

    def test_fehleingabe_leerer_string(self):
        assert _categorize_role("") == "Sonstige"

    def test_corner_case_kurzes_vp_kuerzel(self):
        assert _categorize_role("VP Engineering") == "Führung"
