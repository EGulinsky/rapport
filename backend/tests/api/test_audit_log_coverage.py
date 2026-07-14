"""L2 API — Vollständigkeit des Audit-Logs.

Deckt Lücken ab, bei denen Bewerbungsfelder geändert wurden, aber (vor dem
zugehörigen Fix) kein AuditLog-Eintrag entstand: PATCH-Felder außerhalb des
alten AUDIT_FIELDS-Sets, Firmenzuordnung, sub_status-Änderungen, KI-Bewertung,
automatischer Datum-Backfill, LinkedIn-Sync-Backfills, Merge-Feld-Overrides,
Firmen-Merge pro Bewerbung, sowie automatisches Löschen von Duplikaten beim
Cleanup. `add_audit()` verwirft "update"-Einträge im Log-Level "normal" —
Tests, die solche Einträge prüfen, schalten vorher auf "verbose".
"""
from datetime import date

import pytest

from tests.factories import application_factory, company_profile_factory
from app import models

pytestmark = pytest.mark.api


def _make_verbose(db_session):
    db_session.add(models.SyncSettings(user_id=1, audit_log_level="verbose"))
    db_session.commit()


class TestPatchAuditVollstaendigkeit:
    def test_positiv_vorher_unerfasstes_feld_wird_jetzt_protokolliert(self, client, db_session):
        _make_verbose(db_session)
        app = application_factory(db_session, ort="Berlin")
        db_session.commit()

        resp = client.patch(f"/api/applications/{app.id}", json={"ort": "München"})

        assert resp.status_code == 200
        audit = db_session.query(models.AuditLog).filter_by(app_id=app.id, field="ort").first()
        assert audit is not None
        assert audit.old_value == "Berlin"
        assert audit.new_value == "München"

    def test_positiv_firmenzuordnung_wird_protokolliert(self, client, db_session):
        _make_verbose(db_session)
        app = application_factory(db_session, firma="Alt GmbH")
        cp = company_profile_factory(db_session, name_display="Neu AG")
        db_session.commit()

        resp = client.patch(f"/api/applications/{app.id}", json={"company_profile_id": cp.id})

        assert resp.status_code == 200
        audit = db_session.query(models.AuditLog).filter_by(app_id=app.id, field="firma").first()
        assert audit is not None
        assert audit.new_value == "Neu AG"

    def test_positiv_sub_status_aenderung_wird_mit_korrektem_wert_protokolliert(self, client, db_session):
        app = application_factory(db_session, main_status="hr", sub_status="interview_1")
        db_session.commit()

        resp = client.patch(f"/api/applications/{app.id}", json={"sub_status": "interview_2"})

        assert resp.status_code == 200
        audit = db_session.query(models.AuditLog).filter_by(app_id=app.id, field="sub_status").first()
        assert audit is not None
        assert audit.old_value == "interview_1"
        assert audit.new_value == "interview_2"


class TestAiAssessAudit:
    def test_positiv_geaenderte_ki_einschaetzung_wird_protokolliert(self, client, db_session, monkeypatch):
        _make_verbose(db_session)
        app = application_factory(db_session, ai_color="yellow")
        db_session.commit()

        async def fake_assess(db, application, lang="de", cv_text=None, linkedin_text=None):
            return {"color": "green", "next_step": "Nachfassen", "reasoning": "..."}

        monkeypatch.setattr("app.ai.tasks.assess_application", fake_assess)

        resp = client.post(f"/api/applications/{app.id}/ai-assess")

        assert resp.status_code == 200
        audit = db_session.query(models.AuditLog).filter_by(app_id=app.id, field="ai_color").first()
        assert audit is not None
        assert audit.old_value == "yellow"
        assert audit.new_value == "green"

    def test_negativ_unveraenderte_einschaetzung_wird_nicht_protokolliert(self, client, db_session, monkeypatch):
        _make_verbose(db_session)
        app = application_factory(db_session, ai_color="green")
        db_session.commit()

        async def fake_assess(db, application, lang="de", cv_text=None, linkedin_text=None):
            return {"color": "green", "next_step": "Warten", "reasoning": "..."}

        monkeypatch.setattr("app.ai.tasks.assess_application", fake_assess)

        client.post(f"/api/applications/{app.id}/ai-assess")

        audit = db_session.query(models.AuditLog).filter_by(app_id=app.id, field="ai_color").first()
        assert audit is None


class TestListApplicationsBackfillAudit:
    def test_positiv_automatischer_datum_backfill_wird_protokolliert(self, client, db_session):
        _make_verbose(db_session)
        app = application_factory(db_session, datum_bewerbung=None)
        db_session.add(models.Event(
            application_id=app.id, typ="bewerbung", datum=date(2026, 1, 15),
            titel="Bewerbung eingereicht", user_id=1,
        ))
        db_session.commit()

        resp = client.get("/api/applications/")

        assert resp.status_code == 200
        audit = db_session.query(models.AuditLog).filter_by(app_id=app.id, field="datum_bewerbung").first()
        assert audit is not None
        assert audit.source == "system"


class TestMergeAuditVollstaendigkeit:
    def test_positiv_nicht_status_feld_override_wird_jetzt_protokolliert(self, client, db_session):
        _make_verbose(db_session)
        winner = application_factory(db_session, firma="Contoso AG", kommentar="alt")
        loser = application_factory(db_session, firma="Contoso AG", kommentar="besserer Kommentar")
        db_session.commit()

        client.post("/api/merge/applications", json={
            "winner_id": winner.id, "loser_ids": [loser.id],
            "field_overrides": {"kommentar": loser.id},
        })

        audit = db_session.query(models.AuditLog).filter_by(app_id=winner.id, field="kommentar").first()
        assert audit is not None
        assert audit.old_value == "alt"
        assert audit.new_value == "besserer Kommentar"

    def test_positiv_firmenmerge_protokolliert_pro_bewerbung(self, client, db_session):
        _make_verbose(db_session)
        winner = company_profile_factory(db_session, name_display="Contoso AG")
        loser = company_profile_factory(db_session, name_display="Contoso Old AG")
        app = application_factory(db_session, company_profile_id=loser.id, firma="Contoso Old AG")
        db_session.commit()

        client.post("/api/merge/companies", json={
            "winner_id": winner.id, "loser_ids": [loser.id], "field_overrides": {},
        })

        audit = db_session.query(models.AuditLog).filter_by(app_id=app.id, field="firma").first()
        assert audit is not None
        assert audit.new_value == "Contoso AG"


class TestCleanupAuditVollstaendigkeit:
    def test_positiv_automatisch_geloeschtes_duplikat_wird_protokolliert(self, client, db_session):
        # keeper braucht genug "filled"-Bonusfelder, um den Score-Vergleich deterministisch
        # zu gewinnen (siehe _app_score in cleanup.py, gleiches Muster wie test_cleanup_api.py).
        keeper = application_factory(
            db_session, firma="Contoso AG", rolle="Engineer",
            quelle="LinkedIn", kommentar="voll", wurde_besetzt_von="y", zielfirma_bei_hh="z",
            gespraech_1="a", gespraech_2="b",
        )
        dup = application_factory(db_session, firma="Contoso AG", rolle="Engineer")
        db_session.commit()

        resp = client.post("/api/cleanup/run", params={"scope": "applications"})

        assert resp.status_code == 200
        assert db_session.get(models.Application, dup.id) is None
        audit = db_session.query(models.AuditLog).filter_by(app_id=keeper.id, action="delete").first()
        assert audit is not None
        assert str(dup.id) in audit.old_value
