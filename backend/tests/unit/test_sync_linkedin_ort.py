"""L0 Unit — Ort-Extraktion aus LinkedIn-Kartentext (_extract_jobs_from_text)."""
import pytest

from app.routers.sync_linkedin import _extract_jobs_from_text

pytestmark = pytest.mark.unit


class TestExtractJobsOrt:
    def test_positiv_ort_wird_aus_firma_ort_zeile_extrahiert(self):
        text = "\n".join([
            "Senior Backend Engineer",
            "Contoso AG · München, Bayern, Deutschland",
            "Applied 3d ago",
        ])

        jobs, _ = _extract_jobs_from_text(text, seen_keys=set(), default_status="applied")

        assert len(jobs) == 1
        assert jobs[0]["ort"] == "München, Bayern, Deutschland"
        assert jobs[0]["company"] == "Contoso AG"

    def test_corner_case_kein_ort_nach_trennzeichen_liefert_leeren_string(self):
        text = "\n".join([
            "Backend Engineer",
            "Contoso AG ·",
            "Applied 1d ago",
        ])

        jobs, _ = _extract_jobs_from_text(text, seen_keys=set(), default_status="applied")

        assert len(jobs) == 1
        assert jobs[0]["ort"] == ""

    def test_negativ_nav_tab_pille_wird_nicht_als_ort_eintrag_erkannt(self):
        # "Applied · 10" ist eine Navigations-Pille (Zähler), keine Firma·Ort-Zeile.
        text = "\n".join([
            "Applied · 10",
            "Saved · 3",
        ])

        jobs, _ = _extract_jobs_from_text(text, seen_keys=set(), default_status="applied")

        assert jobs == []
