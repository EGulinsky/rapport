"""L0 Unit — Application.salary_mismatch.

"Best-case overlap check": a mismatch is flagged only when the best possible
budget (its max if a range was given, else its single value) is still below
the lowest amount the applicant would accept. Any missing value, or ranges
that could plausibly overlap, must not be flagged.
"""
from app import models

import pytest

pytestmark = pytest.mark.unit


class TestSalaryMismatch:
    def test_positiv_single_vs_single_budget_unter_erwartung(self):
        app = models.Application(salary_expectation_min=70000, salary_budget_min=60000)
        assert app.salary_mismatch is True

    def test_negativ_single_vs_single_budget_ueber_erwartung(self):
        app = models.Application(salary_expectation_min=70000, salary_budget_min=80000)
        assert app.salary_mismatch is False

    def test_positiv_range_vs_range_kein_ueberlapp(self):
        app = models.Application(
            salary_expectation_min=70000, salary_expectation_max=80000,
            salary_budget_min=50000, salary_budget_max=60000,
        )
        assert app.salary_mismatch is True

    def test_negativ_range_vs_range_moeglicher_ueberlapp(self):
        app = models.Application(
            salary_expectation_min=70000, salary_expectation_max=80000,
            salary_budget_min=75000, salary_budget_max=90000,
        )
        assert app.salary_mismatch is False

    def test_negativ_single_erwartung_vs_range_budget_bestmoeglich_reicht(self):
        app = models.Application(
            salary_expectation_min=70000,
            salary_budget_min=60000, salary_budget_max=75000,
        )
        assert app.salary_mismatch is False

    def test_positiv_single_erwartung_vs_range_budget_bestmoeglich_reicht_nicht(self):
        app = models.Application(
            salary_expectation_min=70000,
            salary_budget_min=50000, salary_budget_max=65000,
        )
        assert app.salary_mismatch is True

    def test_negativ_keine_erwartung_gesetzt(self):
        app = models.Application(salary_budget_min=10000)
        assert app.salary_mismatch is False

    def test_negativ_kein_budget_gesetzt(self):
        app = models.Application(salary_expectation_min=70000)
        assert app.salary_mismatch is False

    def test_negativ_weder_erwartung_noch_budget(self):
        app = models.Application()
        assert app.salary_mismatch is False
