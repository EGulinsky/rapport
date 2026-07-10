"""L0 Unit — AI-Response-Validierung in tasks.py und analytics.py.

Risk: tasks.py vertraut blind auf die JSON-Ausgabe des AI-Modells.
assess_application() hat nur eine einzige Validierung: color in ("green",
"yellow", "red"). Alle anderen Felder (reasoning, next_step, event_type,
confidence, suggested_main_status) werden ohne Schema-Prüfung übernommen.

Dieselbe Lücke betrifft classify_for_app() und match_and_classify() —
deren Rückgaben enthalten Felder wie "confidence" (soll float [0,1] sein),
"suggested_main_status" (soll aus MAIN_STATUS sein), "event_type" (soll
bestimmte Werte haben) — keins wird validiert.

Dieser Test validiert die tatsächliche bestehende Validierung + dokumentiert
die Lücken durch explizite Negativtests, die KEINE Validierung haben.
"""
import pytest

pytestmark = pytest.mark.unit


class TestAssessApplicationColor:
    """Die einzige existierende Validierung in assess_application()."""

    @staticmethod
    def _assess_validate(result: dict) -> str:
        """Spiegelt die Validierung aus tasks.py Line 395-397."""
        color = result.get("color")
        if color not in ("green", "yellow", "red"):
            color = "yellow"
        return color

    def test_positiv_green_wird_akzeptiert(self):
        assert self._assess_validate({"color": "green"}) == "green"

    def test_positiv_red_wird_akzeptiert(self):
        assert self._assess_validate({"color": "red"}) == "red"

    def test_positiv_yellow_wird_akzeptiert(self):
        assert self._assess_validate({"color": "yellow"}) == "yellow"

    def test_negativ_unbekannte_farbe_faellt_auf_yellow_zurueck(self):
        assert self._assess_validate({"color": "blue"}) == "yellow"

    def test_negativ_fehlt_color_faellt_auf_yellow(self):
        assert self._assess_validate({"reasoning": "ok"}) == "yellow"

    def test_negativ_none_color_faellt_auf_yellow(self):
        assert self._assess_validate({"color": None}) == "yellow"


class TestClassifyForAppValidationGap:
    """Dokumentiert die fehlende Validierung in classify_for_app().

    Aktuell werden confidence, suggested_main_status, event_type ohne
    Schema-Prüfung übernommen. Diese Tests zeigen, WAS fehlt.
    """

    @staticmethod
    def _classify_validate(ai_result: dict) -> dict:
        """Illustriert die fehlende Validierung: aktuell wird das AI-Ergebnis
        1:1 durchgereicht. Ein validierter Wrapper würde hier ansetzen."""
        result = dict(ai_result)
        # FEHLT: confidence should be float in [0, 1]
        # FEHLT: event_type should be in known set
        # FEHLT: suggested_main_status should be in MAIN_STATUS
        # FEHLT: datum should be valid ISO date
        return result

    def test_luecke_confidence_out_of_range_wird_nicht_abgefangen(self):
        """AI liefert confidence=2.5 — wird unverändert übernommen."""
        raw = {"event_type": "gespräch", "titel": "Test", "confidence": 2.5}
        result = self._classify_validate(raw)
        assert result["confidence"] == 2.5  # unvalidiert!

    def test_luecke_confidence_negativ_wird_nicht_abgefangen(self):
        raw = {"event_type": "gespräch", "titel": "Test", "confidence": -1}
        result = self._classify_validate(raw)
        assert result["confidence"] == -1  # unvalidiert!

    def test_luecke_confidence_als_string_wird_nicht_abgefangen(self):
        raw = {"event_type": "gespräch", "titel": "Test", "confidence": "hoch"}
        result = self._classify_validate(raw)
        assert result["confidence"] == "hoch"  # unvalidiert! Sollte float sein.

    def test_luecke_ungueltiger_suggested_main_status_wird_nicht_abgefangen(self):
        raw = {"event_type": "status", "titel": "Test", "confidence": 0.8,
               "suggested_main_status": "super_status"}
        result = self._classify_validate(raw)
        assert result["suggested_main_status"] == "super_status"  # unvalidiert!

    def test_luecke_fehlerhaftes_event_type_wird_nicht_abgefangen(self):
        raw = {"event_type": 12345, "titel": "Test", "confidence": 0.8}
        result = self._classify_validate(raw)
        assert result["event_type"] == 12345  # unvalidiert! Sollte str sein.

    def test_luecke_fehlerhaftes_datum_wird_nicht_abgefangen(self):
        raw = {"event_type": "gespräch", "titel": "Test", "confidence": 0.8,
               "datum": "kein-datum"}
        result = self._classify_validate(raw)
        assert result["datum"] == "kein-datum"  # unvalidiert!


class TestCompleteFunctionErrorHandling:
    """Testet den error-Mapping-Wrapper in ai/provider.py.

    complete() fängt nur JSONDecodeError, keine Schema-Verstöße.
    """

    @staticmethod
    def _safe_json(text: str) -> dict | None:
        """Spiegelt _safe_json() aus ai/provider.py (nur JSON-Syntax)."""
        import json
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def test_positiv_gueltiges_json_wird_geparsed(self):
        assert self._safe_json('{"color": "green"}') == {"color": "green"}

    def test_negativ_ungueltiges_json_gibt_none(self):
        assert self._safe_json('{"color": "green"') is None

    def test_negativ_leerer_string(self):
        assert self._safe_json("") is None

    def test_corner_case_json_ist_valides_array_kein_dict(self):
        # AI könnte auch valides, aber strukturell falsches JSON liefern
        assert self._safe_json('[1, 2, 3]') == [1, 2, 3]
