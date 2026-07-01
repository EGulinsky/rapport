"""L0 Unit — app/dedup.py. Reine Funktionen, keine DB/Netzwerk."""
import pytest

from app.dedup import dedup_key, norm_firma, norm_rolle

pytestmark = pytest.mark.unit


class TestNormFirma:
    def test_positiv_einfacher_name(self):
        assert norm_firma("Siemens") == "siemens"

    def test_positiv_gross_klein_ignoriert(self):
        assert norm_firma("SIEMENS") == norm_firma("siemens")

    def test_positiv_rechtsform_wird_entfernt(self):
        # Rechtsformen wie "AG"/"GmbH" dürfen den Match nicht verhindern —
        # sonst würden "Siemens" und "Siemens AG" als unterschiedliche Firmen gelten.
        assert norm_firma("Siemens AG") == norm_firma("Siemens")

    def test_corner_case_mehrfaches_leerzeichen(self):
        assert norm_firma("Siemens   Digital") == norm_firma("Siemens Digital")

    def test_negativ_unterschiedliche_firmen_bleiben_unterschiedlich(self):
        assert norm_firma("Siemens") != norm_firma("Bosch")

    def test_fehleingabe_leerer_string(self):
        # Darf nicht crashen — leerer String ist eine gültige (wenn auch nutzlose) Eingabe.
        assert norm_firma("") == ""

    def test_fehleingabe_nur_whitespace(self):
        assert norm_firma("   ") == ""


class TestNormRolle:
    def test_positiv_gender_stern_wird_entfernt(self):
        # "(m/w/d)"-artige Suffixe dürfen den Rollen-Vergleich nicht verfälschen.
        assert norm_rolle("Entwickler (m/w/d)") == norm_rolle("Entwickler")

    def test_negativ_unterschiedliche_rollen_bleiben_unterschiedlich(self):
        assert norm_rolle("Entwickler") != norm_rolle("Manager")


class TestDedupKey:
    def test_positiv_gleiche_bewerbung_gleicher_key(self):
        assert dedup_key("Siemens AG", "Entwickler (m/w/d)") == dedup_key("Siemens", "Entwickler")

    def test_negativ_andere_rolle_anderer_key(self):
        assert dedup_key("Siemens", "Entwickler") != dedup_key("Siemens", "Manager")

    def test_corner_case_gleiche_firma_leere_rolle(self):
        # Muss deterministisch bleiben, nicht crashen.
        k1 = dedup_key("Siemens", "")
        k2 = dedup_key("Siemens", "")
        assert k1 == k2
