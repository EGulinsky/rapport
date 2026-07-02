"""L1 Component — _find_or_create_application() setzt/befüllt das Ort-Feld aus dem
LinkedIn-Sync, ohne einen bereits manuell gepflegten Ort zu überschreiben.
"""
import pytest

from app.routers.sync_linkedin import _find_or_create_application
from tests.factories import application_factory

pytestmark = pytest.mark.component


def _job(**overrides):
    base = dict(
        id="", title="Backend Engineer", company="Contoso AG", ort="München, Deutschland",
        applied_date=None, default_status="applied", status_hint=None, hinweis="",
        stellenanzeige_url=None,
    )
    base.update(overrides)
    return base


class TestFindOrCreateApplicationOrt:
    def test_positiv_neue_bewerbung_uebernimmt_ort_aus_linkedin(self, db_session):
        app, created, _pending, _dbg = _find_or_create_application(db_session, _job())

        assert created is True
        assert app.ort == "München, Deutschland"

    def test_positiv_bestehende_bewerbung_ohne_ort_wird_befuellt(self, db_session):
        existing = application_factory(db_session, firma="Contoso AG", rolle="Backend Engineer", ort=None)
        db_session.commit()

        app, created, _pending, _dbg = _find_or_create_application(db_session, _job())

        assert created is False
        assert app.id == existing.id
        assert app.ort == "München, Deutschland"

    def test_negativ_vorhandener_ort_wird_nicht_ueberschrieben(self, db_session):
        # Ein manuell gepflegter Ort ist eine bewusste Nutzereingabe und darf durch
        # einen nachfolgenden LinkedIn-Sync nicht stillschweigend ersetzt werden.
        existing = application_factory(db_session, firma="Contoso AG", rolle="Backend Engineer", ort="Manuell: Remote")
        db_session.commit()

        app, created, _pending, _dbg = _find_or_create_application(db_session, _job(ort="Hamburg, Deutschland"))

        assert created is False
        assert app.id == existing.id
        assert app.ort == "Manuell: Remote"

    def test_corner_case_leerer_ort_aus_linkedin_setzt_nichts(self, db_session):
        app, created, _pending, _dbg = _find_or_create_application(db_session, _job(ort=""))

        assert created is True
        assert app.ort is None
