"""L0 Unit -- _normalize_name() in sync_common.py: canonical name fingerprint
used both by the existing mail-sync name+company fallback match and by the
new LinkedIn message-to-contact matching (sync_linkedin.py).
"""
import unicodedata

import pytest

from app.routers.sync_common import _normalize_name

pytestmark = pytest.mark.unit


class TestNormalizeName:
    def test_positiv_reihenfolge_ist_egal(self):
        assert _normalize_name("Mehra, Malvika") == _normalize_name("Malvika Mehra")

    def test_positiv_umlaut_nfc_und_nfd_sind_gleich(self):
        # A precomposed codepoint (NFC, e.g. u-umlaut as one character) vs a
        # base letter + combining diaeresis U+0308 (NFD) look identical but
        # compare unequal without Unicode normalization -- the exact bug
        # this fix addresses. Built from a plain-ASCII base via unicodedata
        # rather than two umlaut literals in source, since a text editor or
        # UTF-8 pipeline could silently normalize both literals to the same
        # form regardless of what was typed.
        base = "Jörgen Müller"
        nfc = unicodedata.normalize("NFC", base)
        nfd = unicodedata.normalize("NFD", base)
        assert nfc != nfd  # sanity check: really are different byte sequences
        assert _normalize_name(nfc) == _normalize_name(nfd)

    def test_positiv_case_insensitive(self):
        assert _normalize_name("ANNA SCHMIDT") == _normalize_name("anna schmidt")

    def test_negativ_unterschiedliche_namen_bleiben_unterschiedlich(self):
        assert _normalize_name("Anna Schmidt") != _normalize_name("Anna Schmid")

    def test_corner_case_leerstring(self):
        assert _normalize_name("") == ""


class TestNormalizeNameUmlautTransliteration:
    """German umlauts are frequently spelled out as ASCII digraphs (ä→ae,
    ö→oe, ü→ue, ß→ss) when umlaut input isn't available -- e.g. a LinkedIn
    export writing "Hans-Peter Gruenwald" for a contact stored in Rapport
    as "Hans-Peter Grünwald". Both forms must match."""

    def test_positiv_ue_gegen_ü_nachname(self):
        assert _normalize_name("Hans-Peter Grünwald") == _normalize_name("Hans-Peter Gruenwald")

    def test_positiv_ue_gegen_ü_einfacher_nachname(self):
        assert _normalize_name("Müller") == _normalize_name("Mueller")

    def test_positiv_oe_gegen_ö(self):
        assert _normalize_name("Björn Köhler") == _normalize_name("Bjoern Koehler")

    def test_positiv_ae_gegen_ä(self):
        assert _normalize_name("Bärbel Bär") == _normalize_name("Baerbel Baer")

    def test_positiv_ss_gegen_eszett(self):
        assert _normalize_name("Weiß") == _normalize_name("Weiss")

    def test_positiv_gemischte_umlaute_in_einem_namen(self):
        assert _normalize_name("Jürgen Preißler") == _normalize_name("Juergen Preissler")

    def test_positiv_transliteration_kombiniert_mit_reihenfolge(self):
        assert _normalize_name("Grünwald, Hans-Peter") == _normalize_name("Hans-Peter Gruenwald")

    def test_positiv_transliteration_kombiniert_mit_grossschreibung(self):
        assert _normalize_name("HANS-PETER GRÜNWALD") == _normalize_name("hans-peter gruenwald")

    def test_positiv_grossbuchstabe_umlaut(self):
        # Ü/Ö/Ä lowercase to ü/ö/ä (stdlib .lower() handles this), which the
        # translation table then expands the same as the lowercase originals.
        assert _normalize_name("Ünal Öztürk") == _normalize_name("Uenal Oeztuerk")

    def test_negativ_ascii_namen_ohne_umlaut_bleiben_unveraendert(self):
        # Sanity check: transliteration must not accidentally merge unrelated
        # ASCII names that happen to contain "ue"/"oe"/"ae"/"ss" literally.
        assert _normalize_name("Sue Baker") != _normalize_name("Su Baker")
        assert _normalize_name("Bauer") != _normalize_name("Bär")

    def test_negativ_transliteration_verschmilzt_keine_verschiedenen_namen(self):
        assert _normalize_name("Grünwald") != _normalize_name("Schumann")
