"""L2 API — /api/review/*: PendingMatch approve/reject.

Deckt die 5 destruktiven Code-Pfade in review.py ab (vorher 0 Tests):
- duplicate_contact (löscht dup Contact, merged Apps)
- duplicate_event (löscht dup Event)
- status_only (mutiert app.main_status inkl. pre_rejection_status)
- regular event (erzeugt Event aus PendingMatch)
- reject (setzt review_status, bei company_candidate mit Wikidata-Fallback)

Risk: approve_match() löscht dauerhaft Entitäten (Contact, Event, Application).
review.py hatte vor diesen Tests 0 % Line-Coverage.
"""
import json
from datetime import date

import pytest

from app import models
from tests.factories import application_factory, contact_factory, event_factory

pytestmark = pytest.mark.api


class TestApproveMatch404:
    def test_negativ_unbekannter_match(self, client):
        resp = client.post("/api/review/99999/approve", json={"application_id": None})
        assert resp.status_code == 404

    def test_negativ_fehlende_application_bei_normalem_match(self, client, db_session):
        pm = models.PendingMatch(
            source="gmail", external_id="ext_1", confidence=80,
            event_type="status_change", review_status="pending", user_id=1,
        )
        db_session.add(pm)
        db_session.commit()

        resp = client.post(f"/api/review/{pm.id}/approve", json={"application_id": None})

        assert resp.status_code == 404


class TestApproveMatchDuplicateContact:
    """event_type='duplicate_contact' — löscht dup Contact, merged Apps."""

    def test_positiv_kontakte_werden_zusammengefuehrt_und_dup_geloescht(self, client, db_session):
        keeper = contact_factory(db_session, name="Keeper")
        dup = contact_factory(db_session, name="Duplicate")
        app = application_factory(db_session)
        dup.applications.append(app)
        db_session.commit()

        pm = models.PendingMatch(
            source="cleanup", external_id="cleanup_contact_1",
            confidence=90, event_type="duplicate_contact",
            raw_content=json.dumps({"keeper_contact_id": keeper.id, "dup_contact_id": dup.id}),
            review_status="pending", user_id=1,
        )
        db_session.add(pm)
        db_session.commit()

        resp = client.post(f"/api/review/{pm.id}/approve", json={"application_id": None})

        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"
        db_session.refresh(keeper)
        assert app in keeper.applications
        assert db_session.get(models.Contact, dup.id) is None

    def test_negativ_bei_bestaetigtem_match_wird_kein_zweites_mal_angefasst(self, client, db_session):
        keeper = contact_factory(db_session, name="Keeper")
        dup = contact_factory(db_session, name="Duplicate")
        db_session.commit()

        pm = models.PendingMatch(
            source="cleanup", external_id="cleanup_contact_2",
            confidence=90, event_type="duplicate_contact",
            raw_content=json.dumps({"keeper_contact_id": keeper.id, "dup_contact_id": dup.id}),
            review_status="pending", user_id=1,
        )
        db_session.add(pm)
        db_session.commit()

        resp = client.post(f"/api/review/{pm.id}/approve", json={"application_id": None})
        assert resp.status_code == 200

        # Zweiter Aufruf — dup existiert nicht mehr → klarer Fehler statt
        # stillem "approved" ohne Wirkung (Regression: die alte Fassung
        # markierte den Match immer als approved, auch wenn nichts mehr zu
        # tun war, was einen echten Fehlschlag unsichtbar machte).
        resp2 = client.post(f"/api/review/{pm.id}/approve", json={"application_id": None})
        assert resp2.status_code == 404

    def test_negativ_fehlerhaftes_raw_content_json_liefert_400_statt_stillem_erfolg(self, client, db_session):
        pm = models.PendingMatch(
            source="cleanup", external_id="cleanup_contact_3",
            confidence=90, event_type="duplicate_contact",
            raw_content="kein-json",
            review_status="pending", user_id=1,
        )
        db_session.add(pm)
        db_session.commit()

        resp = client.post(f"/api/review/{pm.id}/approve", json={"application_id": None})
        # Regression: die alte Fassung markierte den Match trotz kaputter/
        # fehlender IDs stillschweigend als "approved" — der Duplikat-Kontakt
        # blieb unangetastet, ohne dass der User das je erfuhr (live
        # gemeldet: mehrfaches "Approve" ohne sichtbare Wirkung).
        assert resp.status_code == 400
        db_session.refresh(pm)
        assert pm.review_status == "pending"


class TestApproveMatchDuplicateEvent:
    """event_type='duplicate_event' — löscht dup Event."""

    def test_positiv_dup_event_wird_geloescht(self, client, db_session):
        app = application_factory(db_session)
        ev = event_factory(db_session, app, typ="notiz")
        db_session.commit()

        pm = models.PendingMatch(
            source="cleanup", external_id="cleanup_event_1",
            confidence=90, event_type="duplicate_event",
            raw_content=json.dumps({"dup_event_id": ev.id}),
            suggested_app_id=app.id, review_status="pending", user_id=1,
        )
        db_session.add(pm)
        db_session.commit()

        resp = client.post(f"/api/review/{pm.id}/approve", json={"application_id": app.id})

        assert resp.status_code == 200
        assert db_session.get(models.Event, ev.id) is None

    def test_negativ_dup_event_aus_andrem_user_wird_nicht_geloescht(self, client, db_session):
        app = application_factory(db_session)
        ev = event_factory(db_session, app, typ="notiz", user_id=999)
        db_session.commit()

        pm = models.PendingMatch(
            source="cleanup", external_id="cleanup_event_2",
            confidence=90, event_type="duplicate_event",
            raw_content=json.dumps({"dup_event_id": ev.id}),
            suggested_app_id=app.id, review_status="pending", user_id=1,
        )
        db_session.add(pm)
        db_session.commit()

        resp = client.post(f"/api/review/{pm.id}/approve", json={"application_id": app.id})

        assert resp.status_code == 200
        assert db_session.get(models.Event, ev.id) is not None  # fremdes Event bleibt


class TestApproveMatchStatusOnly:
    """status_only=True — mutiert app.main_status, erzeugt Status-Event."""

    def test_positiv_status_aenderung_wird_angewendet(self, client, db_session):
        app = application_factory(db_session, main_status="applied")
        db_session.commit()

        pm = models.PendingMatch(
            source="gmail", external_id="ext_status_1",
            confidence=80, event_type="status_change",
            suggested_app_id=app.id, suggested_main_status="hr",
            status_only=True, review_status="pending", user_id=1,
        )
        db_session.add(pm)
        db_session.commit()

        resp = client.post(f"/api/review/{pm.id}/approve", json={"application_id": app.id})

        assert resp.status_code == 200
        assert resp.json()["event_id"] is not None
        db_session.refresh(app)
        assert app.main_status == "hr"

    def test_positiv_rejected_setzt_pre_rejection_status(self, client, db_session):
        app = application_factory(db_session, main_status="hr", sub_status="1_scheduled")
        db_session.commit()

        pm = models.PendingMatch(
            source="gmail", external_id="ext_status_2",
            confidence=80, event_type="status_change",
            suggested_app_id=app.id, suggested_main_status="rejected",
            status_only=True, review_status="pending", user_id=1,
        )
        db_session.add(pm)
        db_session.commit()

        resp = client.post(f"/api/review/{pm.id}/approve", json={"application_id": app.id})

        assert resp.status_code == 200
        db_session.refresh(app)
        assert app.main_status == "rejected"
        assert app.pre_rejection_status == "hr"
        assert app.sub_status is None  # rejected hat keinen sub_status

    def test_positiv_sub_status_wird_mit_gesetzt_bei_hr_fb(self, client, db_session):
        app = application_factory(db_session, main_status="applied")
        db_session.commit()

        pm = models.PendingMatch(
            source="gmail", external_id="ext_status_3",
            confidence=80, event_type="status_change",
            suggested_app_id=app.id, suggested_main_status="hr",
            suggested_sub_status="2_done",
            status_only=True, review_status="pending", user_id=1,
        )
        db_session.add(pm)
        db_session.commit()

        resp = client.post(f"/api/review/{pm.id}/approve", json={"application_id": app.id})

        assert resp.status_code == 200
        db_session.refresh(app)
        assert app.main_status == "hr"
        assert app.sub_status == "2_done"

    def test_positiv_nicht_hr_fb_setzt_sub_status_auf_none(self, client, db_session):
        app = application_factory(db_session, main_status="negotiating", sub_status=None)
        db_session.commit()

        pm = models.PendingMatch(
            source="gmail", external_id="ext_status_4",
            confidence=80, event_type="status_change",
            suggested_app_id=app.id, suggested_main_status="signed",
            status_only=True, review_status="pending", user_id=1,
        )
        db_session.add(pm)
        db_session.commit()

        resp = client.post(f"/api/review/{pm.id}/approve", json={"application_id": app.id})

        assert resp.status_code == 200
        db_session.refresh(app)
        assert app.main_status == "signed"
        assert app.sub_status is None


class TestApproveMatchRegularEvent:
    """Normaler Event-Typ — erzeugt Event aus PendingMatch-Daten."""

    def test_positiv_event_wird_aus_match_daten_erzeugt(self, client, db_session):
        app = application_factory(db_session)
        db_session.commit()

        pm = models.PendingMatch(
            source="gmail", external_id="ext_event_1",
            confidence=70, event_type="gespräch",
            titel="Interview Termin", extract="Morgen um 10 Uhr",
            datum=date.today(),
            suggested_app_id=app.id, review_status="pending", user_id=1,
        )
        db_session.add(pm)
        db_session.commit()

        resp = client.post(f"/api/review/{pm.id}/approve", json={
            "application_id": app.id, "event_type": "gespräch",
            "datum": str(date.today()), "titel": "Bestätigtes Interview",
        })

        assert resp.status_code == 200
        assert resp.json()["event_id"] is not None
        event = db_session.query(models.Event).filter_by(application_id=app.id).first()
        assert event is not None
        assert event.typ == "gespräch"
        assert event.notiz == "Morgen um 10 Uhr"

    def test_positiv_body_datum_wird_gegen_bewerbungsdatum_gekappt(self, client, db_session):
        app = application_factory(db_session, datum_bewerbung=date(2024, 6, 1))
        db_session.commit()

        pm = models.PendingMatch(
            source="gmail", external_id="ext_event_2",
            confidence=70, event_type="gespräch",
            titel="Altes Event", extract="",
            datum=date(2024, 1, 1),
            suggested_app_id=app.id, review_status="pending", user_id=1,
        )
        db_session.add(pm)
        db_session.commit()

        resp = client.post(f"/api/review/{pm.id}/approve", json={
            "application_id": app.id,
            "datum": str(date(2024, 1, 1)),
            "titel": "Altes Event",
        })

        assert resp.status_code == 200
        event = db_session.query(models.Event).filter_by(application_id=app.id).first()
        assert event is not None
        assert event.datum == date(2024, 6, 1)  # auf datum_bewerbung gekappt


class TestRejectMatch:
    def test_positiv_match_wird_zurueckgewiesen(self, client, db_session):
        pm = models.PendingMatch(
            source="gmail", external_id="ext_reject_1",
            confidence=70, event_type="gespräch",
            titel="Zu ignorieren",
            review_status="pending", user_id=1,
        )
        db_session.add(pm)
        db_session.commit()

        resp = client.delete(f"/api/review/{pm.id}")

        assert resp.status_code == 200
        db_session.refresh(pm)
        assert pm.review_status == "rejected"

    def test_negativ_unbekannter_match(self, client):
        resp = client.delete("/api/review/99999")
        assert resp.status_code == 404


class TestCleanupCalendarStatus:
    def test_positiv_calender_status_vorschlaege_werden_zurueckgewiesen(self, client, db_session):
        for source in ("gcal", "icloud_cal"):
            pm = models.PendingMatch(
                source=source, external_id=f"ext_cal_{source}",
                confidence=80, event_type="status_change",
                suggested_app_id=1, suggested_main_status="rejected",
                status_only=True, review_status="pending", user_id=1,
            )
            db_session.add(pm)
        # Nicht-Kalender-Match bleibt pending
        non_cal = models.PendingMatch(
            source="gmail", external_id="ext_non_cal",
            confidence=80, event_type="status_change",
            suggested_app_id=1, suggested_main_status="rejected",
            status_only=True, review_status="pending", user_id=1,
        )
        db_session.add(non_cal)
        db_session.commit()

        resp = client.post("/api/review/cleanup-calendar-status")

        assert resp.status_code == 200
        assert resp.json()["cleaned"] == 2  # 2 Kalender-Matches rejected
        db_session.refresh(non_cal)
        assert non_cal.review_status == "pending"  # Nicht-Kalender bleibt

    def test_negativ_keine_pending_calendar_matches(self, client, db_session):
        resp = client.post("/api/review/cleanup-calendar-status")
        assert resp.status_code == 200
        assert resp.json()["cleaned"] == 0
