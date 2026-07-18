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
