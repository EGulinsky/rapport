"""L0 Unit — _parse_vcard() in sync_icloud.py. Reine Parsing-Logik, echte
vCards über vobject serialisiert (tests/factories.py::icloud_vcard), keine
Netzwerk-/DB-Abhängigkeit.
"""
import pytest

from app.routers.sync_icloud import _parse_vcard
from tests.factories import icloud_vcard

pytestmark = pytest.mark.unit


class TestParseVcard:
    def test_positiv_vollstaendige_vcard_wird_korrekt_geparst(self):
        raw = icloud_vcard(
            "Erika Musterfrau", family="Musterfrau", given="Erika",
            email="erika@contoso.com", org="Contoso AG", title="Recruiter",
            tel="+491701234567", tel_type="CELL", linkedin_url="https://linkedin.com/in/erika",
        )
        parsed = _parse_vcard(raw)

        assert parsed["name"] == "Musterfrau"
        assert parsed["vorname"] == "Erika"
        assert parsed["fn"] == "Erika Musterfrau"
        assert parsed["email"] == "erika@contoso.com"
        assert parsed["phones"] == [{"number": "+491701234567", "type": "mobile"}]
        assert parsed["firma"] == "Contoso AG"
        assert parsed["rolle"] == "Recruiter"
        assert parsed["linkedin_url"] == "https://linkedin.com/in/erika"

    def test_positiv_firmenkarte_ohne_n_feld_behaelt_vollen_anzeigenamen(self):
        raw = icloud_vcard("Contoso AG Empfang", org="Contoso AG")
        parsed = _parse_vcard(raw)

        assert parsed["name"] == "Contoso AG Empfang"
        assert parsed["vorname"] is None

    def test_positiv_alle_telefonnummern_mit_typ_werden_zurueckgegeben(self):
        """vCards can carry several typed TEL entries (HOME/WORK/CELL/...) —
        all of them are kept (with a mapped type), not just one."""
        import vobject
        card = vobject.vCard()
        card.add("fn").value = "Erika Musterfrau"
        festnetz = card.add("tel")
        festnetz.value = "+49301234567"
        festnetz.type_param = "WORK"
        mobil = card.add("tel")
        mobil.value = "+491701234567"
        mobil.type_param = "CELL"

        parsed = _parse_vcard(card.serialize())

        assert parsed["phones"] == [
            {"number": "+49301234567", "type": "work"},
            {"number": "+491701234567", "type": "mobile"},
        ]

    def test_negativ_leere_vcard_ohne_fn_liefert_none(self):
        raw = "BEGIN:VCARD\nVERSION:3.0\nEMAIL:x@y.de\nEND:VCARD\n"
        assert _parse_vcard(raw) is None

    def test_negativ_unparsebare_vcard_liefert_none(self):
        assert _parse_vcard("das ist keine vcard") is None

    def test_negativ_nicht_linkedin_url_wird_ignoriert(self):
        raw = icloud_vcard("Erika Musterfrau", linkedin_url="https://example.com/erika")
        parsed = _parse_vcard(raw)
        assert parsed["linkedin_url"] is None
