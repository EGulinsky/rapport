"""L0 Unit — _compute_naechster_schritt() in routers/applications.py.
Reine Funktion (kein DB-Zugriff nötig), aber datumsabhängig — daher time-machine
statt echtem date.today(), sonst wird der Test an bestimmten Wochentagen flaky.
"""
from datetime import date
from types import SimpleNamespace

import pytest
import time_machine

from app.routers.applications import _compute_naechster_schritt

pytestmark = pytest.mark.unit

TODAY = date(2026, 7, 1)


def _app(main_status: str, datum_bewerbung: date | None = None):
    return SimpleNamespace(main_status=main_status, datum_bewerbung=datum_bewerbung)


class TestNaechsterSchritt:
    def test_positiv_gespraech_heute(self):
        result = _compute_naechster_schritt(_app("hr"), next_interview=TODAY, last_interview=None, today=TODAY)
        assert "heute" in result

    def test_positiv_gespraech_morgen(self):
        morgen = date(2026, 7, 2)
        result = _compute_naechster_schritt(_app("hr"), next_interview=morgen, last_interview=None, today=TODAY)
        assert "morgen" in result

    def test_positiv_gespraech_in_n_tagen(self):
        in_5_tagen = date(2026, 7, 6)
        result = _compute_naechster_schritt(_app("hr"), next_interview=in_5_tagen, last_interview=None, today=TODAY)
        assert "in 5 Tagen" in result

    def test_negativ_abgesagt_liefert_leeren_string(self):
        # Absagen haben keinen "nächsten Schritt" mehr — auch nicht, wenn zufällig
        # noch ein zukünftiges Gespräch-Event existiert (z.B. nicht abgesagter Termin).
        result = _compute_naechster_schritt(_app("rejected"), next_interview=TODAY, last_interview=None, today=TODAY)
        assert result == ""

    def test_corner_case_signed_ohne_gespraech(self):
        result = _compute_naechster_schritt(_app("signed"), next_interview=None, last_interview=None, today=TODAY)
        assert result == "Onboarding vorbereiten"

    def test_corner_case_ghosting_schwelle(self):
        vor_22_tagen = date(2026, 6, 9)
        result = _compute_naechster_schritt(_app("hr"), next_interview=None, last_interview=vor_22_tagen, today=TODAY)
        assert "Ghosting" in result

    def test_corner_case_knapp_unter_ghosting_schwelle(self):
        vor_21_tagen = date(2026, 6, 10)
        result = _compute_naechster_schritt(_app("hr"), next_interview=None, last_interview=vor_21_tagen, today=TODAY)
        assert "nachfassen" in result

    def test_fehleingabe_applied_ohne_datum_bewerbung(self):
        # datum_bewerbung=None darf nicht crashen (z.B. bei manuell unvollständig angelegten Bewerbungen).
        result = _compute_naechster_schritt(_app("applied", datum_bewerbung=None), next_interview=None, last_interview=None, today=TODAY)
        assert "Warte auf Einladung" in result

    def test_fehleingabe_unbekannter_status(self):
        result = _compute_naechster_schritt(_app("nonexistent_status"), next_interview=None, last_interview=None, today=TODAY)
        assert result == ""

    @time_machine.travel(TODAY)
    def test_zeitkontext_mit_time_machine(self):
        # Beweist, dass time-machine für zukünftige Tests mit date.today() funktioniert.
        assert date.today() == TODAY
