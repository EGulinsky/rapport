"""L1 Unit — _li_dedup_key() and _unaccounted_active_linkedin_apps() in
sync_linkedin.py. Pure functions extracted from the batch-sync ARCHIVED-skip
optimization: scraping the ARCHIVED category is the slowest part of a batch
LinkedIn sync (largest, most-paginated tab), so it's only scraped if some
active (non-rejected) application with a LinkedIn job-posting URL didn't
already turn up in the other categories -- otherwise there's nothing new it
could tell us. Tested here without any Playwright/DB machinery, since the
surrounding _async_sync() is an untested (documented gap) async Playwright
orchestration function."""
from types import SimpleNamespace

import pytest

from app.routers.sync_linkedin import _li_dedup_key, _unaccounted_active_linkedin_apps

pytestmark = pytest.mark.unit


def _app(firma: str | None, rolle: str | None):
    return SimpleNamespace(firma=firma, rolle=rolle)


class TestLiDedupKey:
    def test_positiv_normalisiert_gross_klein_und_leerzeichen(self):
        assert _li_dedup_key("Contoso AG", "Backend Engineer ") == _li_dedup_key("contoso ag ", " Backend Engineer")

    def test_negativ_none_wird_zu_leerstring(self):
        assert _li_dedup_key(None, None) == " | "


class TestUnaccountedActiveLinkedinApps:
    def test_positiv_app_fehlt_in_gescrapten_kategorien_ist_unaccounted(self):
        apps = [_app("Contoso AG", "Backend Engineer")]
        scraped = {}  # nothing scraped yet in the non-archived categories

        result = _unaccounted_active_linkedin_apps(apps, scraped)

        assert result == apps

    def test_negativ_app_bereits_in_gescrapten_kategorien_ist_nicht_unaccounted(self):
        apps = [_app("Contoso AG", "Backend Engineer")]
        scraped = {_li_dedup_key("Contoso AG", "Backend Engineer"): {"company": "Contoso AG", "title": "Backend Engineer"}}

        result = _unaccounted_active_linkedin_apps(apps, scraped)

        assert result == []

    def test_positiv_gemischt_nur_der_fehlende_wird_zurueckgegeben(self):
        found_app = _app("Contoso AG", "Backend Engineer")
        missing_app = _app("Acme GmbH", "Frontend Engineer")
        scraped = {_li_dedup_key("Contoso AG", "Backend Engineer"): {}}

        result = _unaccounted_active_linkedin_apps([found_app, missing_app], scraped)

        assert result == [missing_app]

    def test_negativ_leere_app_liste_liefert_leere_liste(self):
        assert _unaccounted_active_linkedin_apps([], {"x": {}}) == []
