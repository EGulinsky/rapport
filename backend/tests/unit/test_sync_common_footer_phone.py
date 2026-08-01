"""L0 -- _extract_footer_info()'s phone-number extraction in sync_common.py.

Production incident (2026-08): a Contact ended up with a ContactPhone row
`number="07/29/2026", type="other"` -- _PHONE_RE's bare single-letter labels
("M.", "T.") plus its permissive separator character class (which allows
"/") happily captured a date that appeared right after a "T:"/"M:" footer
line meaning something unrelated (a target/meeting date), since the only
prior acceptance check was a pure digit-count (>= 7). _looks_like_date() now
rejects any candidate that both has the shape of a slash/dot/dash-separated
date AND actually parses as a real calendar date via datetime.strptime."""
import pytest

from app.routers.sync_common import _extract_footer_info, _looks_like_date

pytestmark = pytest.mark.unit


class TestLooksLikeDate:
    def test_positiv_datum_mit_slash_erkannt(self):
        assert _looks_like_date("07/29/2026") is True

    def test_positiv_datum_mit_punkt_erkannt(self):
        assert _looks_like_date("29.07.2026") is True

    def test_positiv_datum_mit_zweistelligem_jahr_erkannt(self):
        assert _looks_like_date("07/29/26") is True

    def test_positiv_iso_datum_erkannt(self):
        assert _looks_like_date("2026/07/29") is True

    def test_negativ_echte_telefonnummer_nicht_als_datum_erkannt(self):
        assert _looks_like_date("089/123-4567") is False

    def test_negativ_kurze_telefonnummer_ohne_drei_gruppen_nicht_erkannt(self):
        assert _looks_like_date("0171/12345678") is False

    def test_negativ_ungueltiges_scheindatum_nicht_erkannt(self):
        # Shaped like a date (three same-separator groups) but month=88 isn't
        # a real calendar date -- must not be over-eagerly rejected just
        # because it looks date-shaped.
        assert _looks_like_date("88/88/2026") is False

    def test_negativ_gemischte_trennzeichen_nicht_erkannt(self):
        assert _looks_like_date("07/29-2026") is False


class TestExtractFooterInfoPhone:
    def test_negativ_datum_nach_t_label_wird_nicht_als_telefon_uebernommen(self):
        body = "Viele Grüße\nT: 07/29/2026\nMax Mustermann"
        info = _extract_footer_info(body, "Max Mustermann")
        assert 'telefon' not in info

    def test_negativ_datum_nach_m_label_wird_nicht_als_telefon_uebernommen(self):
        body = "Viele Grüße\nM: 07/29/2026\nMax Mustermann"
        info = _extract_footer_info(body, "Max Mustermann")
        assert 'telefon' not in info

    def test_negativ_datum_nach_fon_label_wird_nicht_als_telefon_uebernommen(self):
        body = "Viele Grüße\nFon: 07/29/2026\nMax Mustermann"
        info = _extract_footer_info(body, "Max Mustermann")
        assert 'telefon' not in info

    def test_positiv_echte_telefonnummer_nach_tel_label_wird_uebernommen(self):
        body = "Viele Grüße\nTel.: +49 89 12345678\nMax Mustermann"
        info = _extract_footer_info(body, "Max Mustermann")
        assert info['telefon'] == '+49 89 12345678'

    def test_positiv_echte_telefonnummer_nach_bare_t_label_wird_uebernommen(self):
        body = "Viele Grüße\nT: +49 171 1234567\nMax Mustermann"
        info = _extract_footer_info(body, "Max Mustermann")
        assert info['telefon'] == '+49 171 1234567'

    def test_positiv_echte_telefonnummer_nach_mobile_label_wird_uebernommen(self):
        body = "Viele Grüße\nMobile: 0171/12345678\nMax Mustermann"
        info = _extract_footer_info(body, "Max Mustermann")
        assert info['telefon'] == '0171/12345678'
