"""L0 Unit — Contact.display_name.

Most contact-creation paths store only the surname in "name" (structured
N:-field split from vCard imports); one path (mail-signature upsert,
sync_common.py) instead stores the already-full name in "name" and
redundantly duplicates the first name into "vorname". display_name() must
produce a correct combined name in both cases.
"""
import pytest

from app import models

pytestmark = pytest.mark.unit


class TestDisplayName:
    def test_positiv_ohne_vorname_liefert_name(self):
        c = models.Contact(name="Zoch")
        assert c.display_name == "Zoch"

    def test_positiv_vorname_und_nachname_getrennt_werden_kombiniert(self):
        c = models.Contact(name="Zoch", vorname="Niklas")
        assert c.display_name == "Niklas Zoch"

    def test_negativ_voller_name_mit_redundantem_vorname_wird_nicht_verdoppelt(self):
        # sync_common.py's _upsert_contact stores the full name in "name" AND
        # separately sets "vorname" — display_name must not double it up.
        c = models.Contact(name="Niklas Zoch", vorname="Niklas")
        assert c.display_name == "Niklas Zoch"

    def test_positiv_leerer_vorname_string_liefert_name(self):
        c = models.Contact(name="Zoch", vorname="")
        assert c.display_name == "Zoch"

    def test_corner_case_vorname_gross_klein_schreibung_wird_erkannt(self):
        c = models.Contact(name="niklas zoch", vorname="Niklas")
        assert c.display_name == "niklas zoch"
