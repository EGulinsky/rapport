"""L1 Unit — _trunc() in export_pdf.py. Reine Funktion."""
import pytest

from app.routers.export_pdf import _trunc

pytestmark = pytest.mark.unit


class TestTrunc:
    def test_negativ_kurzer_text_bleibt_unveraendert(self):
        assert _trunc("Kurz", 10) == "Kurz"

    def test_positiv_langer_text_wird_gekuerzt_mit_ellipse(self):
        result = _trunc("Ein sehr langer Firmenname GmbH", 10)
        assert len(result) == 10
        assert result.endswith("…")

    def test_corner_case_exakte_laenge_bleibt_unveraendert(self):
        text = "1234567890"
        assert _trunc(text, 10) == text
