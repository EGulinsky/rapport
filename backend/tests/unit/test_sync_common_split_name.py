"""L0 Unit -- _split_name() in sync_common.py.

Regression for a live incident (2026-08-03): the German corporate email
signature convention "NACHNAME Vorname" (all-caps surname first, e.g.
"DIVIVIER Timo", "GOEZ Jana") was parsed with the default "Firstname
Lastname" assumption, silently reversing the name -- vorname ended up holding
the surname instead of the first name, and the contact this produced didn't
match the existing correctly-named contact for the same person (mismatched
tokens), creating a duplicate."""
import pytest

from app.routers.sync_common import _split_name

pytestmark = pytest.mark.unit


class TestSplitName:
    def test_positiv_komma_getrennt(self):
        assert _split_name("Mehra, Malvika") == ("Mehra", "Malvika")

    def test_positiv_vorname_nachname_reihenfolge(self):
        assert _split_name("Malvika Mehra") == ("Mehra", "Malvika")

    def test_positiv_grossgeschriebener_nachname_zuerst(self):
        # The live-incident case: German corporate signature convention.
        assert _split_name("DIVIVIER Timo") == ("DIVIVIER", "Timo")

    def test_positiv_grossgeschriebener_nachname_zuerst_zweites_beispiel(self):
        assert _split_name("GOEZ Jana") == ("GOEZ", "Jana")

    def test_negativ_einzelnes_token(self):
        assert _split_name("Cher") == ("Cher", "")

    def test_negativ_beide_tokens_grossgeschrieben_faellt_auf_default_zurueck(self):
        # No mixed-case token to signal which side is the surname -- keep
        # the existing default (last token = surname) rather than guessing.
        assert _split_name("JOHN SMITH") == ("SMITH", "JOHN")

    def test_corner_case_dreiteiliger_name_mit_grossgeschriebenem_nachname(self):
        # A single-letter leading token (e.g. an initial) doesn't count as a
        # signal -- len(tok) > 1 guards against that.
        assert _split_name("A Meier") == ("Meier", "A")
