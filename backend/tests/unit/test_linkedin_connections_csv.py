"""L0 Unit — _parse_linkedin_connections_csv() in sync_linkedin.py.

Replaces the removed live connections-list scraper (v4.7.11/v4.7.12): the
user uploads LinkedIn's official Connections.csv export instead. The real
export (verified against an actual 1,559-line file from a live account, not
just a synthetic fixture) starts with a "Notes:" line and a quoted
disclaimer paragraph before the real header row — the fixture below
reproduces that shape exactly, including real sample rows (names/URLs
anonymized, but the layout — First/Last Name, umlaut-containing name via
percent-encoded URL, empty Email Address column, Company/Position present —
matches the genuine export byte-for-byte in structure).
"""
import pytest

from app.routers.sync_linkedin import _parse_linkedin_connections_csv

pytestmark = pytest.mark.unit

_REAL_SHAPE_CSV = (
    'Notes:\n'
    '"When exporting your connection data, you may notice that some of the email addresses are missing. '
    'You will only see email addresses for connections who have allowed their connections to see or download '
    'their email address using this setting https://www.linkedin.com/psettings/privacy/email. '
    'You can learn more here https://www.linkedin.com/help/linkedin/answer/261"\n'
    '\n'
    'First Name,Last Name,URL,Email Address,Company,Position,Connected On\n'
    'Christoph,Rosenhammer,https://www.linkedin.com/in/christoph-rosenhammer-4504713b5,,EDAG Group,'
    'Project Manager,16 Jul 2026\n'
    'Rebecca,Kapfer,https://www.linkedin.com/in/rebecca-kapfer-497489a6,rebecca.kapfer@gmx.net,'
    'Dopamin Coaching by Rebecca Kapfer,Systemischer Business Coach,29 Jun 2026\n'
    'Jürgen,Gebs,https://www.linkedin.com/in/j%C3%BCrgen-gebs-714a561b9,,Cognizant Mobility,'
    'Leiter Vertrieb,16 Jun 2026\n'
)


class TestParseLinkedinConnectionsCsv:
    def test_positiv_parst_alle_zeilen_mit_vollem_feldsatz(self):
        result = _parse_linkedin_connections_csv(_REAL_SHAPE_CSV)

        assert len(result) == 3
        assert result[0] == {
            "name": "Rosenhammer", "vorname": "Christoph", "fn": "Christoph Rosenhammer",
            "email": None, "firma": "EDAG Group", "rolle": "Project Manager",
            "linkedin_url": "https://www.linkedin.com/in/christoph-rosenhammer-4504713b5",
            "phones": [],
        }

    def test_positiv_email_wird_uebernommen_wenn_vorhanden(self):
        result = _parse_linkedin_connections_csv(_REAL_SHAPE_CSV)

        rebecca = next(r for r in result if r["name"] == "Kapfer")
        assert rebecca["email"] == "rebecca.kapfer@gmx.net"
        assert rebecca["firma"] == "Dopamin Coaching by Rebecca Kapfer"
        assert rebecca["rolle"] == "Systemischer Business Coach"

    def test_positiv_umlaut_im_namen_bleibt_erhalten(self):
        result = _parse_linkedin_connections_csv(_REAL_SHAPE_CSV)

        juergen = next(r for r in result if r["vorname"] == "Jürgen")
        assert juergen["name"] == "Gebs"
        assert juergen["fn"] == "Jürgen Gebs"

    def test_negativ_ohne_header_liefert_leere_liste(self):
        result = _parse_linkedin_connections_csv("just some text\nwithout the real header\n")

        assert result == []

    def test_negativ_zeile_ohne_namen_wird_uebersprungen(self):
        content = (
            'First Name,Last Name,URL,Email Address,Company,Position,Connected On\n'
            ',,https://www.linkedin.com/in/nobody,,,,\n'
            'Anna,Muster,https://www.linkedin.com/in/anna-muster,,Beispiel AG,CTO,01 Jan 2026\n'
        )

        result = _parse_linkedin_connections_csv(content)

        assert len(result) == 1
        assert result[0]["name"] == "Muster"

    def test_corner_case_nur_vorname_ohne_nachname_nutzt_vollen_namen(self):
        # Not observed in the real export, but the parser shouldn't crash or
        # silently drop a row if LinkedIn ever ships one with only a first name.
        content = (
            'First Name,Last Name,URL,Email Address,Company,Position,Connected On\n'
            'Cher,,https://www.linkedin.com/in/cher,,,,\n'
        )

        result = _parse_linkedin_connections_csv(content)

        assert result[0]["name"] == "Cher"
        assert result[0]["vorname"] == "Cher"
