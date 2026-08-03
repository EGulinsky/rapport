"""L0 Unit — _categories_for_individual_sync() in sync_linkedin.py.

The individual sync ("re-sync this one application") used to search all 6
LinkedIn categories including ARCHIVED (up to 99 pages) sequentially until a
match was found. Now mirrors the batch sync's ARCHIVED-inclusion rule (see
_unaccounted_active_linkedin_apps()): ARCHIVED is only worth searching if the
application actually has a LinkedIn job-posting link to match against —
regardless of its current status, since even a non-rejected application
could theoretically have slipped into Archived on LinkedIn's side without
the tracker knowing yet.
"""
import pytest

from app.routers.sync_linkedin import CATEGORIES, _categories_for_individual_sync
from tests.factories import application_factory

pytestmark = pytest.mark.unit


class TestCategoriesForIndividualSync:
    def test_positiv_ohne_li_link_ueberspringt_archived(self, db_session):
        app = application_factory(db_session, main_status="applied", stellenanzeige_url=None)
        db_session.commit()

        result = _categories_for_individual_sync(app)

        assert "ARCHIVED" not in [c[0] for c in result]
        assert len(result) == len(CATEGORIES) - 1

    def test_positiv_mit_li_link_durchsucht_auch_archived(self, db_session):
        app = application_factory(
            db_session, main_status="applied",
            stellenanzeige_url="https://www.linkedin.com/jobs/view/12345",
        )
        db_session.commit()

        result = _categories_for_individual_sync(app)

        assert "ARCHIVED" in [c[0] for c in result]
        assert result == CATEGORIES

    def test_positiv_abgesagt_aber_ohne_li_link_ueberspringt_trotzdem_archived(self, db_session):
        # Regression guard: status alone (e.g. already "rejected") no longer
        # decides this -- without an actual LinkedIn job link, no scraped
        # Archived job could ever match via _quick_match() anyway.
        app = application_factory(db_session, main_status="rejected", stellenanzeige_url=None)
        db_session.commit()

        result = _categories_for_individual_sync(app)

        assert "ARCHIVED" not in [c[0] for c in result]

    def test_positiv_nicht_linkedin_url_ueberspringt_archived(self, db_session):
        app = application_factory(
            db_session, main_status="applied", stellenanzeige_url="https://example.com/jobs/12345",
        )
        db_session.commit()

        result = _categories_for_individual_sync(app)

        assert "ARCHIVED" not in [c[0] for c in result]

    def test_corner_case_keine_bewerbung_ueberspringt_archived(self):
        result = _categories_for_individual_sync(None)

        assert "ARCHIVED" not in [c[0] for c in result]

    def test_positiv_andere_kategorien_bleiben_unveraendert_und_in_reihenfolge(self, db_session):
        app = application_factory(db_session, main_status="hr", stellenanzeige_url=None)
        db_session.commit()

        result = _categories_for_individual_sync(app)

        expected = [c for c in CATEGORIES if c[0] != "ARCHIVED"]
        assert result == expected
