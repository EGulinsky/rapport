"""L0 Unit — _categories_for_individual_sync() in sync_linkedin.py.

Der Einzelsync ("diese eine Bewerbung neu synchronisieren") durchsuchte bisher
alle 6 LinkedIn-Kategorien inkl. ARCHIVED (bis zu 99 Seiten) sequenziell, bis
ein Match gefunden wurde — für eine gezielt neu gesyncte, nicht abgesagte
Bewerbung unnötig langsam, da sie praktisch nie im Archiv liegt.
"""
import pytest

from app.routers.sync_linkedin import CATEGORIES, _categories_for_individual_sync
from tests.factories import application_factory

pytestmark = pytest.mark.unit


class TestCategoriesForIndividualSync:
    def test_positiv_nicht_abgesagte_bewerbung_ueberspringt_archived(self, db_session):
        app = application_factory(db_session, main_status="applied")
        db_session.commit()

        result = _categories_for_individual_sync(app)

        assert "ARCHIVED" not in [c[0] for c in result]
        assert len(result) == len(CATEGORIES) - 1

    def test_negativ_abgesagte_bewerbung_durchsucht_auch_archived(self, db_session):
        app = application_factory(db_session, main_status="rejected")
        db_session.commit()

        result = _categories_for_individual_sync(app)

        assert "ARCHIVED" in [c[0] for c in result]
        assert result == CATEGORIES

    def test_corner_case_keine_bewerbung_ueberspringt_archived(self):
        result = _categories_for_individual_sync(None)

        assert "ARCHIVED" not in [c[0] for c in result]

    def test_positiv_andere_kategorien_bleiben_unveraendert_und_in_reihenfolge(self, db_session):
        app = application_factory(db_session, main_status="hr")
        db_session.commit()

        result = _categories_for_individual_sync(app)

        expected = [c for c in CATEGORIES if c[0] != "ARCHIVED"]
        assert result == expected
