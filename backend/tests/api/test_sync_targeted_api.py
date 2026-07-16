"""L2 API — Endpunkte in sync_targeted.py, die ohne externe Mocks testbar sind:
reset, Validierung von sync_for_app, Ergebnis-Abruf, Kandidatenliste (Pool 1+2)
und manuelle Zuweisung (Pool 1/2/3-Validierung). Die eigentlichen externen
Syncs (Gmail/iCloud/Calls) sind in tests/integration bzw. tests/component
abgedeckt.
"""
from datetime import date

import pytest

from app import models
from tests.factories import application_factory, event_factory

pytestmark = pytest.mark.api


class TestResetTargetedSync:
    def test_positiv_loescht_sync_events_und_synced_items(self, client, db_session):
        app = application_factory(db_session)
        event_factory(db_session, app, source="gmail")
        event_factory(db_session, app, source=None, typ="notiz")  # manuell, hat keine source
        db_session.add(models.SyncedItem(source="gmail", external_id="msg-1", user_id=1))
        db_session.commit()

        resp = client.post(f"/api/sync/targeted/{app.id}/reset")

        assert resp.status_code == 200
        assert resp.json()["deleted_events"] == 1
        assert resp.json()["deleted_items"] == 1
        assert db_session.query(models.Event).filter_by(application_id=app.id).count() == 1

    def test_negativ_unbekannte_bewerbung_liefert_404(self, client):
        resp = client.post("/api/sync/targeted/999999/reset")
        assert resp.status_code == 404


class TestSyncForAppValidation:
    def test_negativ_unbekannte_bewerbung_liefert_404(self, client):
        resp = client.post("/api/sync/targeted/999999")
        assert resp.status_code == 404

    def test_negativ_keine_suchbegriffe_liefert_400(self, client, db_session):
        # rolle="" (not the factory's random fake.job() default) — the role
        # is included in _search_terms() too now, which would otherwise
        # randomly give this "no search terms at all" case something to
        # search for and let the sync actually run instead of 400ing.
        app = application_factory(db_session, firma="AB", zielfirma_bei_hh=None, wurde_besetzt_von=None, rolle="")
        resp = client.post(f"/api/sync/targeted/{app.id}")
        assert resp.status_code == 400


class TestGetResult:
    def test_negativ_ohne_vorherigen_sync_liefert_done_false(self, client, db_session):
        app = application_factory(db_session)
        resp = client.get(f"/api/sync/targeted/{app.id}/result")
        assert resp.status_code == 200
        assert resp.json() == {"done": False}

    def test_negativ_unbekannte_bewerbung_liefert_404(self, client):
        resp = client.get("/api/sync/targeted/999999/result")
        assert resp.status_code == 404


class TestListCandidates:
    def test_negativ_unbekannte_bewerbung_liefert_404(self, client):
        resp = client.get("/api/sync/targeted/999999/candidates")
        assert resp.status_code == 404

    def test_positiv_pending_match_nach_suchbegriff_gefiltert(self, client, db_session):
        app = application_factory(db_session, firma="Contoso AG")
        db_session.add(models.PendingMatch(
            source="gmail", external_id="msg-1", confidence=70, titel="Interview bei Contoso",
            extract="Wir laden Sie ein", datum=date.today(), review_status="pending", user_id=1,
        ))
        db_session.add(models.PendingMatch(
            source="gmail", external_id="msg-2", confidence=70, titel="Newsletter",
            extract="Irrelevant", datum=date.today(), review_status="pending", user_id=1,
        ))
        db_session.commit()

        resp = client.get(f"/api/sync/targeted/{app.id}/candidates")

        assert resp.status_code == 200
        titles = [c["titel"] for c in resp.json()]
        assert "Interview bei Contoso" in titles
        assert "Newsletter" not in titles

    def test_positiv_bereits_zugewiesener_review_wird_ignoriert(self, client, db_session):
        app = application_factory(db_session, firma="Contoso AG")
        db_session.add(models.PendingMatch(
            source="gmail", external_id="msg-1", confidence=70, titel="Interview bei Contoso",
            extract="", datum=date.today(), review_status="approved",
        ))
        db_session.commit()

        resp = client.get(f"/api/sync/targeted/{app.id}/candidates")

        assert resp.json() == []

    def test_positiv_event_einer_anderen_bewerbung_ist_kandidat(self, client, db_session):
        app = application_factory(db_session, firma="Contoso AG")
        other_app = application_factory(db_session, firma="Fremdfirma GmbH")
        event_factory(db_session, other_app, titel="Interview bei Contoso", source="gmail", external_id="msg-9")
        db_session.commit()

        resp = client.get(f"/api/sync/targeted/{app.id}/candidates")

        assert resp.status_code == 200
        assert any(c["titel"] == "Interview bei Contoso" for c in resp.json())

    def test_negativ_event_ohne_sync_quelle_ist_kein_kandidat(self, client, db_session):
        app = application_factory(db_session, firma="Contoso AG")
        other_app = application_factory(db_session, firma="Fremdfirma GmbH")
        event_factory(db_session, other_app, titel="Contoso Notiz", source=None)
        db_session.commit()

        resp = client.get(f"/api/sync/targeted/{app.id}/candidates")

        assert resp.json() == []


class TestManualAssign:
    def test_negativ_match_id_null_ohne_source_liefert_400(self, client, db_session):
        app = application_factory(db_session)
        resp = client.post(f"/api/sync/targeted/{app.id}/assign", json={"match_id": 0})
        assert resp.status_code == 400

    def test_negativ_gmail_ohne_google_verbindung_liefert_400(self, client, db_session):
        app = application_factory(db_session)
        resp = client.post(
            f"/api/sync/targeted/{app.id}/assign",
            json={"match_id": 0, "external_id": "msg-1", "source": "gmail", "titel": "Betreff"},
        )
        assert resp.status_code == 400

    def test_positiv_live_item_existiert_bereits_kein_konflikt(self, client, db_session):
        app = application_factory(db_session)
        event_factory(db_session, app, source="icloud_notes", external_id="note-1")
        db_session.commit()

        resp = client.post(
            f"/api/sync/targeted/{app.id}/assign",
            json={"match_id": 0, "external_id": "note-1", "source": "icloud_notes", "titel": "Notiz"},
        )

        assert resp.status_code == 200
        assert resp.json()["conflict"] is False

    def test_positiv_icloud_notes_live_zuweisung_ohne_full_fetch(self, client, db_session):
        app = application_factory(db_session)
        resp = client.post(
            f"/api/sync/targeted/{app.id}/assign",
            json={"match_id": 0, "external_id": "note-neu", "source": "icloud_notes", "titel": "Meine Notiz"},
        )
        assert resp.status_code == 200
        ev = db_session.query(models.Event).filter_by(external_id="note-neu").one()
        assert ev.titel == "Meine Notiz"
        assert ev.typ == "notiz"

    def test_positiv_event_umzug_ohne_konflikt_flag_meldet_konflikt(self, client, db_session):
        app = application_factory(db_session)
        other_app = application_factory(db_session, firma="Fremdfirma GmbH")
        ev = event_factory(db_session, other_app, source="gmail", external_id="msg-1")
        db_session.commit()

        resp = client.post(f"/api/sync/targeted/{app.id}/assign", json={"match_id": -ev.id})

        assert resp.status_code == 200
        body = resp.json()
        assert body["conflict"] is True
        assert body["conflict_app_id"] == other_app.id

    def test_positiv_event_umzug_mit_remove_from_other_verschiebt(self, client, db_session):
        app = application_factory(db_session)
        other_app = application_factory(db_session, firma="Fremdfirma GmbH")
        ev = event_factory(db_session, other_app, source="gmail", external_id="msg-1")
        db_session.commit()

        resp = client.post(
            f"/api/sync/targeted/{app.id}/assign",
            json={"match_id": -ev.id, "remove_from_other": True},
        )

        assert resp.status_code == 200
        assert resp.json()["conflict"] is False
        db_session.refresh(ev)
        assert ev.application_id == app.id

    def test_negativ_event_bereits_bei_dieser_bewerbung_kein_konflikt(self, client, db_session):
        app = application_factory(db_session)
        ev = event_factory(db_session, app, source="gmail", external_id="msg-1")
        db_session.commit()

        resp = client.post(f"/api/sync/targeted/{app.id}/assign", json={"match_id": -ev.id})

        assert resp.status_code == 200
        assert resp.json()["conflict"] is False

    def test_negativ_event_nicht_gefunden_liefert_404(self, client, db_session):
        app = application_factory(db_session)
        resp = client.post(f"/api/sync/targeted/{app.id}/assign", json={"match_id": -999999})
        assert resp.status_code == 404

    def test_positiv_pending_match_wird_zu_event_und_approved(self, client, db_session):
        app = application_factory(db_session)
        pm = models.PendingMatch(
            source="gmail", external_id="msg-1", confidence=70, titel="Interview",
            extract="Auszug", datum=date.today(), review_status="pending",
        )
        db_session.add(pm)
        db_session.commit()

        resp = client.post(f"/api/sync/targeted/{app.id}/assign", json={"match_id": pm.id})

        assert resp.status_code == 200
        db_session.refresh(pm)
        assert pm.review_status == "approved"
        ev = db_session.query(models.Event).filter_by(application_id=app.id, external_id="msg-1").one()
        assert ev.titel == "Interview"

    def test_positiv_pending_match_konflikt_mit_anderer_bewerbung(self, client, db_session):
        app = application_factory(db_session)
        other_app = application_factory(db_session, firma="Fremdfirma GmbH")
        event_factory(db_session, other_app, source="gmail", external_id="msg-1")
        pm = models.PendingMatch(
            source="gmail", external_id="msg-1", confidence=70, titel="Interview",
            extract="", datum=date.today(), review_status="pending",
        )
        db_session.add(pm)
        db_session.commit()

        resp = client.post(f"/api/sync/targeted/{app.id}/assign", json={"match_id": pm.id})

        assert resp.status_code == 200
        assert resp.json()["conflict"] is True

    def test_negativ_pending_match_nicht_gefunden_liefert_404(self, client, db_session):
        app = application_factory(db_session)
        resp = client.post(f"/api/sync/targeted/{app.id}/assign", json={"match_id": 999999})
        assert resp.status_code == 404
