"""L0 Unit — _li_job_id_from_url()/_quick_match() in sync_linkedin.py.

Beide sind reine Lese-Funktionen (kein DB-Zugriff, nur Attribut-Zugriff auf
ein übergebenes Application-Objekt) — für _quick_match() reicht daher eine
nicht persistierte models.Application()-Instanz statt einer echten DB-Session.
"""
import pytest

from app import models
from app.routers.sync_linkedin import _li_job_id_from_url, _quick_match

pytestmark = pytest.mark.unit


class TestLiJobIdFromUrl:
    def test_positiv_extrahiert_id_aus_jobs_view_url(self):
        url = "https://www.linkedin.com/jobs/view/1234567890/"
        assert _li_job_id_from_url(url) == "1234567890"

    def test_positiv_funktioniert_auch_mit_query_string(self):
        url = "https://www.linkedin.com/jobs/view/1234567890/?refId=abc&trackingId=xyz"
        assert _li_job_id_from_url(url) == "1234567890"

    def test_negativ_nicht_linkedin_url_liefert_none(self):
        assert _li_job_id_from_url("https://example.com/jobs/view/1234567890/") is None

    def test_negativ_linkedin_url_ohne_jobs_view_liefert_none(self):
        assert _li_job_id_from_url("https://www.linkedin.com/in/erika-musterfrau/") is None

    def test_negativ_leerstring_liefert_none(self):
        assert _li_job_id_from_url("") is None

    def test_negativ_none_liefert_none(self):
        assert _li_job_id_from_url(None) is None


def _job(**overrides) -> dict:
    base = dict(id="", title="Backend Engineer", company="Contoso AG", stellenanzeige_url=None)
    base.update(overrides)
    return base


class TestQuickMatch:
    def test_positiv_matcht_ueber_gleiche_li_job_id(self):
        app = models.Application(firma="Andere Schreibweise AG", rolle="Andere Rolle", linkedin_job_id="1234567890")
        assert _quick_match(_job(id="1234567890"), app) is True

    def test_positiv_matcht_ueber_li_job_id_aus_stellenanzeige_url_des_jobs(self):
        app = models.Application(firma="Andere Schreibweise AG", rolle="Andere Rolle", linkedin_job_id="1234567890")
        job = _job(id="", stellenanzeige_url="https://www.linkedin.com/jobs/view/1234567890/")
        assert _quick_match(job, app) is True

    def test_positiv_matcht_ueber_li_job_id_aus_stellenanzeige_url_der_bewerbung(self):
        app = models.Application(
            firma="Andere Schreibweise AG", rolle="Andere Rolle", linkedin_job_id=None,
            stellenanzeige_url="https://www.linkedin.com/jobs/view/1234567890/",
        )
        assert _quick_match(_job(id="1234567890"), app) is True

    def test_positiv_matcht_ueber_normalisierten_firma_und_rolle_vergleich(self):
        app = models.Application(firma="Contoso AG", rolle="Backend Engineer", linkedin_job_id=None)
        assert _quick_match(_job(id=""), app) is True

    def test_positiv_matcht_ueber_zielfirma_bei_headhunter_bewerbung(self):
        app = models.Application(
            firma="Headhunter GmbH", zielfirma_bei_hh="Contoso AG", rolle="Backend Engineer", linkedin_job_id=None,
        )
        assert _quick_match(_job(id=""), app) is True

    def test_corner_case_abweichende_li_job_id_faellt_auf_firma_rolle_match_zurueck(self):
        # Eine nicht übereinstimmende li_job_id führt NICHT zu einem sofortigen
        # False — die Funktion prüft im Anschluss trotzdem noch Firma+Rolle.
        app = models.Application(firma="Contoso AG", rolle="Backend Engineer", linkedin_job_id="999")
        assert _quick_match(_job(id="111"), app) is True

    def test_negativ_abweichende_li_job_id_und_kein_firma_rolle_match(self):
        app = models.Application(firma="Fremdfirma GmbH", rolle="Andere Rolle", linkedin_job_id="999")
        assert _quick_match(_job(id="111"), app) is False

    def test_negativ_ohne_jede_uebereinstimmung(self):
        app = models.Application(firma="Fremdfirma GmbH", rolle="Andere Rolle", linkedin_job_id=None)
        assert _quick_match(_job(id=""), app) is False

    def test_negativ_firma_matcht_aber_rolle_nicht(self):
        app = models.Application(firma="Contoso AG", rolle="Frontend Engineer", linkedin_job_id=None)
        assert _quick_match(_job(id="", title="Backend Engineer", company="Contoso AG"), app) is False
