"""L0 Unit — _extract_jobs_from_text() in sync_linkedin.py, mit Fokus auf
Firmenname- und Bewerbungsdatum-Extraktion beim Import mehrerer Stellen-
ausschreibungen von einer LinkedIn-"My Jobs"-Seite. Die Ort-Extraktion ist
bereits in test_sync_linkedin_ort.py abgedeckt; dieser Testfall konzentriert
sich auf Firma, Bewerbungsdatum, Mehrfach-Einträge, Dedup und Status-Hinweise.
"""
import pytest

from app.routers.sync_linkedin import _extract_jobs_from_text

pytestmark = pytest.mark.unit


class TestFirmennameExtraktion:
    def test_positiv_firmenname_mit_rechtsform_wird_vollstaendig_uebernommen(self):
        text = "\n".join([
            "Senior Backend Engineer",
            "Contoso Deutschland GmbH & Co. KG · Berlin",
            "Applied 2d ago",
        ])

        jobs, _ = _extract_jobs_from_text(text, seen_keys=set(), default_status="applied")

        assert len(jobs) == 1
        assert jobs[0]["company"] == "Contoso Deutschland GmbH & Co. KG"

    def test_positiv_firmenname_wird_getrimmt(self):
        text = "\n".join([
            "Backend Engineer",
            "   Contoso AG   ·   Berlin  ",
            "Applied 1d ago",
        ])

        jobs, _ = _extract_jobs_from_text(text, seen_keys=set(), default_status="applied")

        assert jobs[0]["company"] == "Contoso AG"

    def test_negativ_zu_kurzer_firmenname_wird_nicht_als_anker_erkannt(self):
        # "AG · Berlin" hat < 3 Zeichen vor dem Trennzeichen — kein valider Anker.
        text = "\n".join([
            "Backend Engineer",
            "AG · Berlin",
            "Applied 1d ago",
        ])

        jobs, _ = _extract_jobs_from_text(text, seen_keys=set(), default_status="applied")

        assert jobs == []


class TestBewerbungsdatumExtraktion:
    def test_positiv_bewerbungsdatum_wird_aus_applied_zeile_geparst(self):
        text = "\n".join([
            "Backend Engineer",
            "Contoso AG · Berlin",
            "Applied 3d ago",
        ])

        jobs, _ = _extract_jobs_from_text(text, seen_keys=set(), default_status="applied")

        from datetime import datetime, timedelta
        expected = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
        assert jobs[0]["applied_date"] == expected

    def test_negativ_ohne_applied_zeile_bleibt_datum_leer(self):
        text = "\n".join([
            "Backend Engineer",
            "Contoso AG · Berlin",
            "Add note",
        ])

        jobs, _ = _extract_jobs_from_text(text, seen_keys=set(), default_status="prospecting")

        assert jobs[0]["applied_date"] is None

    def test_negativ_applied_zeile_muss_am_zeilenanfang_stehen(self):
        # "Reapplied X ago" o.ä. darf nicht fälschlich als "Applied"-Zeile gelten —
        # re.match verankert am Zeilenanfang, nicht irgendwo im Text.
        text = "\n".join([
            "Backend Engineer",
            "Contoso AG · Berlin",
            "You reapplied 2d ago",
        ])

        jobs, _ = _extract_jobs_from_text(text, seen_keys=set(), default_status="applied")

        assert jobs[0]["applied_date"] is None


class TestMehrfacheEintraege:
    def test_positiv_zwei_jobs_werden_jeweils_korrekt_getrennt(self):
        text = "\n".join([
            "Backend Engineer",
            "Contoso AG · Berlin",
            "Applied 5d ago",
            "Frontend Engineer",
            "Fremdfirma GmbH · München",
            "Applied 1d ago",
        ])

        jobs, anchor_count = _extract_jobs_from_text(text, seen_keys=set(), default_status="applied")

        assert anchor_count == 2
        assert len(jobs) == 2
        assert jobs[0]["company"] == "Contoso AG"
        assert jobs[0]["title"] == "Backend Engineer"
        assert jobs[1]["company"] == "Fremdfirma GmbH"
        assert jobs[1]["title"] == "Frontend Engineer"

    def test_positiv_stellenanzeige_urls_werden_positionsbasiert_zugeordnet(self):
        text = "\n".join([
            "Backend Engineer",
            "Contoso AG · Berlin",
            "Applied 5d ago",
            "Frontend Engineer",
            "Fremdfirma GmbH · München",
            "Applied 1d ago",
        ])
        urls = [
            "https://www.linkedin.com/jobs/view/111/",
            "https://www.linkedin.com/jobs/view/222/",
        ]

        jobs, _ = _extract_jobs_from_text(text, seen_keys=set(), default_status="applied", job_urls=urls)

        assert jobs[0]["stellenanzeige_url"] == urls[0]
        assert jobs[1]["stellenanzeige_url"] == urls[1]

    def test_negativ_dedup_ueber_seen_keys_ueberspringt_bekannten_job(self):
        from app.dedup import dedup_key
        text = "\n".join([
            "Backend Engineer",
            "Contoso AG · Berlin",
            "Applied 5d ago",
        ])
        already_seen = {dedup_key("Contoso AG", "Backend Engineer")}

        jobs, anchor_count = _extract_jobs_from_text(text, seen_keys=already_seen, default_status="applied")

        assert anchor_count == 1  # der Anker wird gezählt...
        assert jobs == []          # ...aber als Job übersprungen (Dedup)

    def test_negativ_navigations_pille_wird_nicht_als_job_gezaehlt(self):
        text = "\n".join([
            "Applied · 10",
            "Saved · 3",
            "Backend Engineer",
            "Contoso AG · Berlin",
            "Applied 1d ago",
        ])

        jobs, anchor_count = _extract_jobs_from_text(text, seen_keys=set(), default_status="applied")

        assert anchor_count == 1
        assert len(jobs) == 1
        assert jobs[0]["company"] == "Contoso AG"


class TestStatusHinweisMapping:
    def test_positiv_interview_hinweis_wird_auf_hr_gemappt(self):
        text = "\n".join([
            "Backend Engineer",
            "Contoso AG · Berlin",
            "Applied 5d ago",
            "Interview scheduled",
        ])

        jobs, _ = _extract_jobs_from_text(text, seen_keys=set(), default_status="applied")

        assert jobs[0]["status_hint"] == ("hr", "1_scheduled")
        assert jobs[0]["hinweis"] == "Interview scheduled"

    def test_positiv_absage_hinweis_wird_nicht_automatisch_gemappt(self):
        # "not moving forward" ist zwar in _HINT_KW (löst hinweis-Erkennung aus),
        # aber NICHT in _STATUS_MAP — kein automatischer Statuswechsel.
        text = "\n".join([
            "Backend Engineer",
            "Contoso AG · Berlin",
            "Applied 5d ago",
            "We've decided not moving forward with your application",
        ])

        jobs, _ = _extract_jobs_from_text(text, seen_keys=set(), default_status="applied")

        assert jobs[0]["status_hint"] is None
        assert "not moving forward" in jobs[0]["hinweis"].lower()

    def test_negativ_ohne_erkennbaren_hinweis_bleibt_hinweis_leer(self):
        text = "\n".join([
            "Backend Engineer",
            "Contoso AG · Berlin",
            "Applied 5d ago",
        ])

        jobs, _ = _extract_jobs_from_text(text, seen_keys=set(), default_status="applied")

        assert jobs[0]["hinweis"] == ""
