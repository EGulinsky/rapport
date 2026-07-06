"""L1 Component — _find_or_create_application() in sync_linkedin.py: Firmenname
und Bewerbungsdatum (datum_bewerbung) beim Anlegen einer neuen Bewerbung aus
einem LinkedIn-Job-Dict, inkl. der internen _to_date()-Konvertierung von
job["applied_date"] (ISO-String von _parse_date()) in ein echtes date-Objekt.
"""
from datetime import date

import pytest

from app.routers.sync_linkedin import _find_or_create_application
from tests.factories import application_factory

pytestmark = pytest.mark.component


def _job(**overrides) -> dict:
    base = dict(
        id="", title="Backend Engineer", company="Contoso AG", ort=None,
        applied_date=None, default_status="applied", status_hint=None, hinweis="",
        stellenanzeige_url=None,
    )
    base.update(overrides)
    return base


class TestNeueBewerbungFirmaUndDatum:
    def test_positiv_firmenname_wird_uebernommen(self, db_session):
        app, created, _pending, _dbg = _find_or_create_application(
            db_session, _job(company="Contoso Deutschland GmbH"),
        )
        assert created is True
        assert app.firma == "Contoso Deutschland GmbH"

    def test_positiv_iso_datumsstring_wird_zu_date_objekt(self, db_session):
        app, created, _pending, _dbg = _find_or_create_application(
            db_session, _job(applied_date="2025-03-14"),
        )
        assert created is True
        assert app.datum_bewerbung == date(2025, 3, 14)
        assert app.letztes_update == date(2025, 3, 14)

    def test_negativ_fehlendes_datum_bleibt_none(self, db_session):
        app, created, _pending, _dbg = _find_or_create_application(
            db_session, _job(applied_date=None),
        )
        assert created is True
        assert app.datum_bewerbung is None

    def test_negativ_unparsebares_datum_wird_ohne_absturz_zu_none(self, db_session):
        # _to_date() fängt ValueError bei date.fromisoformat() ab — ein
        # kaputtes Datum darf das Anlegen der Bewerbung nicht verhindern.
        app, created, _pending, _dbg = _find_or_create_application(
            db_session, _job(applied_date="nicht-geparst"),
        )
        assert created is True
        assert app.datum_bewerbung is None

    def test_positiv_bereits_date_objekt_wird_direkt_uebernommen(self, db_session):
        app, created, _pending, _dbg = _find_or_create_application(
            db_session, _job(applied_date=date(2024, 11, 1)),
        )
        assert created is True
        assert app.datum_bewerbung == date(2024, 11, 1)

    def test_positiv_quelle_wird_auf_linkedin_gesetzt(self, db_session):
        app, created, _pending, _dbg = _find_or_create_application(db_session, _job())
        assert app.quelle == "LinkedIn"


class TestBestehendeBewerbungWirdNichtUeberschrieben:
    def test_negativ_firma_und_datum_bleiben_bei_bestehendem_match_unveraendert(self, db_session):
        # Firma+Rolle-Match auf eine bestehende Bewerbung darf weder den
        # Firmennamen noch das ursprüngliche Bewerbungsdatum überschreiben —
        # nur ort/linkedin_job_id/rolle-Bereinigung werden nachgetragen.
        existing = application_factory(
            db_session, firma="Contoso AG", rolle="Backend Engineer",
            datum_bewerbung=date(2024, 1, 1),
        )
        db_session.commit()

        app, created, _pending, dbg = _find_or_create_application(
            db_session, _job(company="Contoso AG", applied_date="2026-01-01"),
        )

        assert created is False
        assert app.id == existing.id
        assert app.firma == "Contoso AG"
        assert app.datum_bewerbung == date(2024, 1, 1)
        assert "firma+rolle" in dbg
