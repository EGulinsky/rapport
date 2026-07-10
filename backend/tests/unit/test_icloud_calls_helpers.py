"""L0 Unit — reine Hilfsfunktionen des Anrufliste-Sync in sync_icloud.py.

_normalize_phone/_phones_match/_name_tokens sind reine Funktionen ohne DB/
Netzwerk-Zugriff — decken die Telefonnummer-Normalisierung (verschiedene
deutsche Schreibweisen) und die Namens-Tokenisierung ab, die _do_icloud_calls()
und _match_contacts_by_name() zum Kontakt-Matching nutzen.
"""
import pytest

from app.routers.sync_icloud import _name_tokens, _normalize_phone, _phones_match

pytestmark = pytest.mark.unit


class TestNormalizePhone:
    def test_positiv_leere_eingabe_liefert_leeren_string(self):
        assert _normalize_phone("") == ""

    def test_positiv_nummer_mit_plus_bleibt_erhalten(self):
        assert _normalize_phone("+49 172 1234567") == "+491721234567"

    def test_positiv_nationale_null_wird_zu_plus49(self):
        assert _normalize_phone("0172 1234567") == "+491721234567"

    def test_positiv_doppelnull_praefix_wird_zu_plus(self):
        assert _normalize_phone("0049 172 1234567") == "+491721234567"

    def test_positiv_klammer_null_formatierung_wird_bereinigt(self):
        # "+49 (0) 172 …" ist ein häufiges Formatierungs-Artefakt.
        assert _normalize_phone("+49 (0) 172 1234567") == "+491721234567"

    def test_negativ_nur_nicht_ziffern_liefert_leeren_string(self):
        assert _normalize_phone("abc") == ""

    def test_corner_case_nummer_ohne_fuehrende_null_oder_plus_bleibt_ziffernfolge(self):
        assert _normalize_phone("1721234567") == "1721234567"


class TestPhonesMatch:
    def test_positiv_identische_normalisierte_nummern_matchen(self):
        assert _phones_match("+49 172 1234567", "0172 1234567") is True

    def test_positiv_suffix_match_bei_kurzen_nummern(self):
        # Eine lokale Nummer ohne Landesvorwahl-Präfix matcht per Suffix-
        # Vergleich gegen dieselbe Nummer mit vollständiger Vorwahl.
        assert _phones_match("99887766", "+4915199887766") is True

    def test_negativ_unterschiedliche_nummern_matchen_nicht(self):
        assert _phones_match("0151 11111111", "0151 22222222") is False

    def test_negativ_leere_nummer_matcht_nicht(self):
        assert _phones_match("", "0151 11111111") is False


class TestNameTokens:
    def test_positiv_vor_und_nachname_werden_als_tokens_erkannt(self):
        tokens = _name_tokens("Erika Musterfrau")
        assert "erika" in tokens
        assert "musterfrau" in tokens

    def test_negativ_honorifikum_wird_ausgefiltert(self):
        # "Prof" ist trotz Länge >= 4 als Honorifikum in der Stop-Liste und
        # muss trotzdem herausgefiltert werden.
        tokens = _name_tokens("Prof. Erika Musterfrau")
        assert "prof" not in tokens
        assert tokens == {"erika", "musterfrau"}

    def test_negativ_kurze_woerter_unter_vier_zeichen_werden_ausgefiltert(self):
        tokens = _name_tokens("Ana Xi")
        assert tokens == set()

    def test_corner_case_leerer_name_liefert_leeres_set(self):
        assert _name_tokens("") == set()
