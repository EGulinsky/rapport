"""L0 Unit — "In Progress"-Jobs (Draft / Clicked apply) in sync_linkedin.py.

Live-Regressionsfall: ein Job im LinkedIn-Tab "In Progress" wurde beim Sync
komplett übersprungen (0 Treffer). Ursache: "In Progress" ist im LinkedIn-SPA
nur eine client-seitige Aggregat-Ansicht zweier echter Unterkategorien
("draft" und "clicked_apply") — die URL jobs-tracker/?stage=in-progress
rendert dauerhaft eine leere Seite, unabhängig von Wartezeit. Die echten,
funktionierenden ?stage=-Werte sind "draft" und "clicked_apply" (mit
Unterstrich). Beide werden erwartungsgemäß auf "prospecting" (Anbahnung)
gemappt, nicht auf "applied" — LinkedIn selbst fragt bei "Clicked apply"
per "Did you finish applying?", ob die Bewerbung überhaupt abgeschlossen
wurde.
"""
import pytest

from app.routers.sync_linkedin import CATEGORIES, _extract_jobs_from_text

pytestmark = pytest.mark.unit


class TestCategoriesInProgressSplit:
    def test_positiv_draft_und_clicked_apply_nutzen_eigene_funktionierende_urls(self):
        by_type = {c[0]: c for c in CATEGORIES}
        assert "IN_PROGRESS" not in by_type

        draft = by_type["DRAFT"]
        assert draft[4].endswith("?stage=draft")
        assert draft[2] == "prospecting"

        clicked = by_type["CLICKED_APPLY"]
        assert clicked[4].endswith("?stage=clicked_apply")
        assert clicked[2] == "prospecting"

    def test_negativ_keine_kategorie_nutzt_die_kaputte_in_progress_url(self):
        # ?stage=in-progress rendert bei LinkedIn dauerhaft eine leere Seite.
        assert not any(c[4].endswith("stage=in-progress") for c in CATEGORIES)


class TestExtractClickedApplyJob:
    def test_positiv_clicked_apply_karte_ohne_applied_zeile_wird_erkannt(self):
        # Live beobachtet auf ?stage=clicked_apply: kein "Applied X ago", sondern
        # "Posted X ago" + "Did you finish applying? / Yes / No".
        text = "\n".join([
            "Vice President Professional Services (m/f/d)",
            "DocuWare · Germering",
            "Posted 1d ago",
            "Add note",
            "Did you finish applying?",
            "Yes",
            "No",
        ])

        jobs, _ = _extract_jobs_from_text(text, seen_keys=set(), default_status="prospecting")

        assert len(jobs) == 1
        job = jobs[0]
        assert job["company"] == "DocuWare"
        assert job["title"] == "Vice President Professional Services (m/f/d)"
        assert job["default_status"] == "prospecting"
        assert job["status_hint"] is None
        assert job["applied_date"] is None
