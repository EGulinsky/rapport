"""L0 Unit — ai/historical_outcomes.py::compute_stage_outcomes().

"Comparable" was defined (user's explicit choice) as "reached at least the
same pipeline stage" -- see ai/tasks.py::_build_history_block()."""
import pytest

from app.ai.historical_outcomes import compute_stage_outcomes
from tests.factories import application_factory

pytestmark = pytest.mark.unit


class TestComputeStageOutcomes:
    def test_negativ_keine_anderen_bewerbungen_gibt_none(self, db_session):
        current = application_factory(db_session, main_status="hr")
        db_session.commit()

        assert compute_stage_outcomes(db_session, user_id=1, current_app=current) is None

    def test_negativ_nur_ein_vergleichbarer_eintrag_gibt_none(self, db_session):
        current = application_factory(db_session, main_status="hr")
        application_factory(db_session, main_status="signed")
        db_session.commit()

        assert compute_stage_outcomes(db_session, user_id=1, current_app=current) is None

    def test_positiv_signed_bewerbungen_zaehlen_immer_als_erreicht(self, db_session):
        current = application_factory(db_session, main_status="hr")
        application_factory(db_session, main_status="signed")
        application_factory(db_session, main_status="signed")
        db_session.commit()

        stats = compute_stage_outcomes(db_session, user_id=1, current_app=current)

        assert stats == {"total": 2, "signed": 2, "rejected": 0, "stage_label": "Gespräch HR/HH"}

    def test_positiv_rejected_mit_gleicher_oder_weiterer_phase_zaehlt(self, db_session):
        current = application_factory(db_session, main_status="hr")
        # Reached fb (further than hr) before rejection -> comparable.
        application_factory(db_session, main_status="rejected", pre_rejection_status="fb")
        # Reached exactly hr before rejection -> comparable.
        application_factory(db_session, main_status="rejected", pre_rejection_status="hr")
        db_session.commit()

        stats = compute_stage_outcomes(db_session, user_id=1, current_app=current)

        assert stats["total"] == 2
        assert stats["rejected"] == 2
        assert stats["signed"] == 0

    def test_negativ_rejected_mit_frueherer_phase_wird_ausgeschlossen(self, db_session):
        current = application_factory(db_session, main_status="hr")
        # Only reached "applied" before rejection -- not as far as "hr".
        application_factory(db_session, main_status="rejected", pre_rejection_status="applied")
        application_factory(db_session, main_status="signed")
        db_session.commit()

        stats = compute_stage_outcomes(db_session, user_id=1, current_app=current)

        # Only the signed one counts -- still below the 2-comparable minimum
        # once the too-early rejection is excluded... add one more signed to
        # cross the threshold and confirm the excluded one never appears.
        assert stats is None

    def test_negativ_rejected_ohne_pre_rejection_status_wird_ausgeschlossen(self, db_session):
        current = application_factory(db_session, main_status="hr")
        application_factory(db_session, main_status="rejected", pre_rejection_status=None)
        application_factory(db_session, main_status="signed")
        db_session.commit()

        # Same as above: the None-stage rejection can't be judged, so it's
        # excluded rather than guessed, leaving only 1 comparable entry.
        assert compute_stage_outcomes(db_session, user_id=1, current_app=current) is None

    def test_negativ_eigene_bewerbung_wird_nicht_mit_sich_selbst_verglichen(self, db_session):
        current = application_factory(db_session, main_status="rejected", pre_rejection_status="hr")
        application_factory(db_session, main_status="signed")
        db_session.commit()

        stats = compute_stage_outcomes(db_session, user_id=1, current_app=current)

        # Only the other signed application counts; current itself excluded
        # -- still below the minimum of 2.
        assert stats is None

    def test_positiv_nur_bewerbungen_aktiver_users_werden_beruecksichtigt(self, db_session):
        current = application_factory(db_session, main_status="hr", user_id=1)
        application_factory(db_session, main_status="signed", user_id=1)
        application_factory(db_session, main_status="signed", user_id=2)  # other tenant
        db_session.commit()

        stats = compute_stage_outcomes(db_session, user_id=1, current_app=current)

        # Cross the 2-minimum with a second same-tenant signed application.
        application_factory(db_session, main_status="signed", user_id=1)
        db_session.commit()
        stats = compute_stage_outcomes(db_session, user_id=1, current_app=current)

        assert stats["total"] == 2  # not 3 -- the other tenant's row excluded
