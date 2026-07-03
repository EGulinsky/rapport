"""L0 Unit — _parse_vcard() Vorname/Nachname-Split in sync_icloud.py.

Live-Regressionsfall: 183 von 184 Kontakten hatten vorname=None und im
name-Feld den vollen Anzeigenamen ("Volker Häussler" statt nur "Häussler"),
weil _parse_vcard nur das FN-Feld (Anzeigename) las und das strukturierte
N:-Feld (Family;Given;;;) der vCard nie auswertete. FN-Reihenfolge ist
uneinheitlich (z.B. "Bayer Sarah" statt "Sarah Bayer"), aber N: ist von
Apple Contacts immer korrekt strukturiert — unabhängig davon, wie FN
formatiert ist.
"""
import pytest

from app.routers.sync_icloud import _parse_vcard

pytestmark = pytest.mark.unit


def _vcard(fn: str, n: tuple[str, str] | None = None, org: str | None = None) -> str:
    lines = ["BEGIN:VCARD", "VERSION:3.0", f"FN:{fn}"]
    if n:
        lines.append(f"N:{n[0]};{n[1]};;;")
    if org:
        lines.append(f"ORG:{org}")
    lines.append("END:VCARD")
    return "\r\n".join(lines)


class TestParseVcardNameSplit:
    def test_positiv_strukturiertes_n_feld_wird_verwendet(self):
        card = _vcard("Volker Häussler", n=("Häussler", "Volker"))
        parsed = _parse_vcard(card)
        assert parsed["name"] == "Häussler"
        assert parsed["vorname"] == "Volker"
        assert parsed["fn"] == "Volker Häussler"

    def test_positiv_n_feld_zuverlaessig_auch_bei_ungewoehnlicher_fn_reihenfolge(self):
        # Live beobachtet: FN "Bayer Sarah" (Nachname zuerst, kein Komma) —
        # aus dem FN-Text allein nicht zuverlässig zu splitten, aber N: ist
        # trotzdem korrekt strukturiert.
        card = _vcard("Bayer Sarah", n=("Bayer", "Sarah"))
        parsed = _parse_vcard(card)
        assert parsed["name"] == "Bayer"
        assert parsed["vorname"] == "Sarah"

    def test_negativ_firma_ohne_n_feld_wird_nicht_gesplittet(self):
        # Firmen-vCards haben ein leeres N:-Feld (";;;;") — kein Rate-Split
        # für Firmennamen wie "Rivada Space Networks GmbH".
        card = _vcard("Rivada Space Networks GmbH", n=("", ""))
        parsed = _parse_vcard(card)
        assert parsed["name"] == "Rivada Space Networks GmbH"
        assert parsed["vorname"] is None

    def test_negativ_kein_n_feld_ueberhaupt_faellt_auf_fn_zurueck(self):
        card = _vcard("CONET")
        parsed = _parse_vcard(card)
        assert parsed["name"] == "CONET"
        assert parsed["vorname"] is None
        assert parsed["fn"] == "CONET"

    def test_negativ_n_feld_ohne_family_faellt_auf_fn_zurueck(self):
        card = _vcard("Nur Vorname Firma", n=("", "Irgendwas"))
        parsed = _parse_vcard(card)
        assert parsed["name"] == "Nur Vorname Firma"
        assert parsed["vorname"] is None
