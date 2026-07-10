"""L2 API — HTTP-Endpunkte in sync_google.py.

Deckt die OAuth-/Verwaltungs-Endpunkte ab (Status, Credentials speichern,
Auth-URL, Callback, Trennen, Progress/Batch-Results, Reset), die von den
_do_gmail()/_do_gcal()-Integrationstests nicht erreicht werden. Mockt
google_auth_oauthlib.flow.Flow an der Netzwerkgrenze für Auth-URL/Callback,
googleapiclient.discovery.build für den Debug-Endpoint.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from google_auth_oauthlib.flow import Flow

from app import models
from app.ai.provider import encrypt_api_key

pytestmark = pytest.mark.api


def _cfg(db_session, **overrides) -> models.GoogleSync:
    defaults = dict(
        client_id="test-client-id",
        client_secret_enc=encrypt_api_key("test-secret"),
        user_id=1,
    )
    defaults.update(overrides)
    cfg = models.GoogleSync(**defaults)
    db_session.add(cfg)
    db_session.commit()
    return cfg


class TestGoogleStatus:
    def test_positiv_ohne_konfiguration_liefert_connected_false(self, client):
        resp = client.get("/api/sync/google/status")

        assert resp.status_code == 200
        assert resp.json()["connected"] is False

    def test_positiv_mit_refresh_token_liefert_connected_true(self, client, db_session):
        _cfg(db_session, refresh_token_enc=encrypt_api_key("rt"))

        resp = client.get("/api/sync/google/status")

        assert resp.json()["connected"] is True
        assert resp.json()["client_id"] == "test-client-id"


class TestSaveCredentials:
    def test_positiv_legt_neue_konfiguration_an(self, client, db_session):
        resp = client.post("/api/sync/google/credentials", json={"client_id": "cid", "client_secret": "csecret"})

        assert resp.status_code == 200
        cfg = db_session.query(models.GoogleSync).one()
        assert cfg.client_id == "cid"

    def test_positiv_aktualisiert_bestehende_konfiguration(self, client, db_session):
        _cfg(db_session)

        resp = client.post("/api/sync/google/credentials", json={"client_id": "neu", "client_secret": "neu-secret"})

        assert resp.status_code == 200
        assert db_session.query(models.GoogleSync).count() == 1
        assert db_session.query(models.GoogleSync).one().client_id == "neu"


class TestGoogleAuthUrl:
    def test_negativ_ohne_credentials_liefert_400(self, client):
        resp = client.get("/api/sync/google/auth")

        assert resp.status_code == 400

    def test_positiv_liefert_auth_url(self, client, db_session):
        _cfg(db_session)

        with patch.object(Flow, "authorization_url", return_value=("https://accounts.google.com/fake-auth", "state")):
            resp = client.get("/api/sync/google/auth")

        assert resp.status_code == 200
        assert resp.json()["url"] == "https://accounts.google.com/fake-auth"


class TestGoogleCallback:
    def test_negativ_ohne_konfiguration_liefert_fehlerseite(self, client, db_session):
        # Kein Konto verifiziert -> get_first_user_id() liefert None, set_session_user() wird übersprungen.
        resp = client.get("/api/sync/google/callback", params={"code": "abc"})

        assert resp.status_code == 400
        assert "Keine Konfiguration" in resp.text

    def test_negativ_falscher_state_wird_abgelehnt(self, client, db_session):
        cfg = _cfg(db_session)
        cfg.oauth_state = "expected-state"
        db_session.commit()

        resp = client.get("/api/sync/google/callback", params={"code": "abc", "state": "wrong-state"})

        assert resp.status_code == 400
        assert "Ungültiger OAuth-State" in resp.text

    def test_positiv_erfolgreicher_callback_speichert_tokens(self, client, db_session):
        cfg = _cfg(db_session)
        cfg.oauth_state = "expected-state"
        db_session.commit()

        fake_creds = type("Creds", (), {
            "token": "new-access-token",
            "refresh_token": "new-refresh-token",
            "expiry": datetime.now(timezone.utc) + timedelta(hours=1),
        })()

        with patch.object(Flow, "fetch_token", return_value=None), \
             patch.object(Flow, "credentials", fake_creds, create=True):
            resp = client.get("/api/sync/google/callback", params={"code": "abc", "state": "expected-state"})

        assert resp.status_code == 200
        assert "verbunden" in resp.text
        db_session.refresh(cfg)
        assert cfg.access_token_enc is not None
        assert cfg.oauth_state is None


class TestGoogleDisconnect:
    def test_positiv_loescht_tokens(self, client, db_session):
        cfg = _cfg(db_session, refresh_token_enc=encrypt_api_key("rt"), access_token_enc=encrypt_api_key("at"))

        resp = client.delete("/api/sync/google")

        assert resp.status_code == 204
        db_session.refresh(cfg)
        assert cfg.refresh_token_enc is None
        assert cfg.access_token_enc is None

    def test_negativ_ohne_konfiguration_ist_no_op(self, client):
        resp = client.delete("/api/sync/google")

        assert resp.status_code == 204


class TestProgressUndBatchResults:
    def test_positiv_progress_liefert_dict(self, client):
        resp = client.get("/api/sync/google/progress")
        assert resp.status_code == 200
        assert isinstance(resp.json(), dict)

    def test_positiv_batch_results_liefert_dict(self, client):
        resp = client.get("/api/sync/google/batch/results")
        assert resp.status_code == 200
        assert isinstance(resp.json(), dict)


class TestResetGmailSync:
    def test_positiv_setzt_last_sync_zurueck(self, client, db_session):
        cfg = _cfg(db_session, gmail_last_sync=datetime.now(timezone.utc))

        resp = client.post("/api/sync/google/gmail/reset")

        assert resp.status_code == 204
        db_session.refresh(cfg)
        assert cfg.gmail_last_sync is None

    def test_negativ_ohne_konfiguration_ist_no_op(self, client):
        resp = client.post("/api/sync/google/gmail/reset")
        assert resp.status_code == 204


class TestResetCalendarSync:
    def test_positiv_setzt_last_sync_zurueck(self, client, db_session):
        cfg = _cfg(db_session, gcal_last_sync=datetime.now(timezone.utc))

        resp = client.post("/api/sync/google/calendar/reset")

        assert resp.status_code == 204
        db_session.refresh(cfg)
        assert cfg.gcal_last_sync is None


class TestSyncGmailEndpoint:
    def test_negativ_ohne_verbindung_liefert_400(self, client, db_session):
        _cfg(db_session)  # kein refresh_token

        resp = client.post("/api/sync/google/gmail")

        assert resp.status_code == 400

    def test_positiv_startet_hintergrund_sync(self, client, db_session):
        _cfg(db_session, refresh_token_enc=encrypt_api_key("rt"), access_token_enc=encrypt_api_key("at"),
             token_expiry=datetime.now(timezone.utc) + timedelta(hours=1))

        with patch("googleapiclient.discovery.build") as mock_build:
            mock_build.return_value.users.return_value.messages.return_value.list.return_value.execute.return_value = {"messages": []}
            resp = client.post("/api/sync/google/gmail")

        assert resp.status_code == 200
        assert resp.json()["processed"] == 0


class TestSyncCalendarEndpoint:
    def test_negativ_ohne_verbindung_liefert_400(self, client, db_session):
        _cfg(db_session)

        resp = client.post("/api/sync/google/calendar")

        assert resp.status_code == 400

    def test_positiv_startet_hintergrund_sync(self, client, db_session):
        _cfg(db_session, refresh_token_enc=encrypt_api_key("rt"), access_token_enc=encrypt_api_key("at"),
             token_expiry=datetime.now(timezone.utc) + timedelta(hours=1))

        with patch("googleapiclient.discovery.build") as mock_build:
            mock_build.return_value.events.return_value.list.return_value.execute.return_value = {"items": []}
            resp = client.post("/api/sync/google/calendar")

        assert resp.status_code == 200
        assert resp.json()["processed"] == 0


class TestDebugGcalEvents:
    def test_negativ_ohne_verbindung_liefert_400(self, client, db_session):
        _cfg(db_session)

        resp = client.get("/api/sync/google/calendar/debug")

        assert resp.status_code == 400

    def test_positiv_liefert_liste_mit_matched_firms(self, client, db_session):
        from tests.factories import application_factory, contact_factory

        app = application_factory(db_session, firma="Contoso AG")
        contact = contact_factory(db_session, email="recruiterin@contoso.com")
        app.contacts.append(contact)
        _cfg(db_session, refresh_token_enc=encrypt_api_key("rt"), access_token_enc=encrypt_api_key("at"),
             token_expiry=datetime.now(timezone.utc) + timedelta(hours=1))
        db_session.commit()

        cal_event = {
            "id": "evt-1", "summary": "Interview", "start": {"dateTime": "2026-08-01T10:00:00Z"},
            "organizer": {"email": "recruiterin@contoso.com"}, "attendees": [],
        }
        with patch("googleapiclient.discovery.build") as mock_build:
            mock_build.return_value.events.return_value.list.return_value.execute.return_value = {"items": [cal_event]}
            resp = client.get("/api/sync/google/calendar/debug")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert "Contoso AG" in body[0]["matched_firms"]
