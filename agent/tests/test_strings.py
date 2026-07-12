"""L0 — strings.py: menu bar i18n lookup helper."""
from agent.strings import _STRINGS, t


class TestT:
    def test_positiv_deutsch_ist_default_bei_unbekannter_sprache(self):
        assert t("copy_token", "fr") == t("copy_token", "de")

    def test_positiv_englisch_liefert_englischen_text(self):
        assert t("copy_token", "en") == "Copy token"

    def test_positiv_interpolation_mit_kwargs(self):
        assert t("running_on_port", "de", port=9996) == "Läuft auf Port 9996"
        assert t("running_on_port", "en", port=9996) == "Running on port 9996"

    def test_corner_case_unbekannter_key_faellt_auf_den_key_selbst_zurueck(self):
        assert t("nonexistent_key", "de") == "nonexistent_key"

    def test_positiv_de_und_en_haben_dieselben_keys(self):
        assert set(_STRINGS["de"].keys()) == set(_STRINGS["en"].keys())
