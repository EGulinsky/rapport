"""L2 API — Verwaltungs-/Endpunkte in sync_icloud.py.

Deckt Status, Credentials speichern/löschen, Web-Passwort, Verbindungstest,
alle /reset-Endpunkte, die Sync-Auslöser (Mail/Kalender/Erinnerungen/Notizen/
Kontakte/Anrufliste — kicken nur einen BackgroundTask an, die eigentliche
Sync-Logik ist bereits in den jeweiligen tests/integration/test_icloud_*.py
end-to-end abgedeckt) sowie den Kalender-Debug-Endpoint und die
Anrufliste-Status/Settings-Endpunkte ab.

BackgroundTasks laufen im FastAPI-TestClient synchron VOR der Rückgabe der
Response — die Sync-Boundaries (IMAP/CalDAV) werden deshalb auch hier gemockt,
damit der ausgelöste Hintergrundlauf nicht gegen echte Server geht.
"""
from unittest.mock import MagicMock

import pytest

from app import models
from app.ai.provider import encrypt_api_key
from tests.factories import application_factory, contact_factory, icloud_vcard
from tests.integration.conftest import (
    FakeCaldavCalendar, FakeCaldavClient, FakeImapConnection, icloud_calendar_event,
)

pytestmark = pytest.mark.api


def _fake_caldav_client(monkeypatch, calendars=None, error=None):
    """Patcht caldav.DAVClient lokal (die `fake_caldav`-Fixture selbst ist auf
    tests/integration/ gescoped) — nutzt dieselben Test-Doubles wie die
    Integrationstests, nur ohne die Fixture-Indirektion."""
    fc = FakeCaldavClient(calendars, error)
    monkeypatch.setattr("caldav.DAVClient", lambda url, username=None, password=None: fc)
    return fc


def _fake_imap_conn(monkeypatch, msg_ids=None, messages=None):
    conn = FakeImapConnection(" ".join(msg_ids or []).encode(), messages or {})
    monkeypatch.setattr("imaplib.IMAP4_SSL", lambda host, port: conn)
    return conn


def _cfg(db_session, **overrides) -> models.ICloudSync:
    defaults = dict(
        apple_id="test@example.com",
        app_password_enc=encrypt_api_key("test-app-password"),
        user_id=1,
    )
    defaults.update(overrides)
    cfg = models.ICloudSync(**defaults)
    db_session.add(cfg)
    db_session.commit()
    return cfg


class TestIcloudStatus:
    def test_positiv_ohne_konfiguration_liefert_connected_false(self, client):
        resp = client.get("/api/sync/icloud/status")

        assert resp.status_code == 200
        assert resp.json()["connected"] is False

    def test_positiv_mit_konfiguration_liefert_connected_true(self, client, db_session):
        _cfg(db_session, icloud_email="test@icloud.com")

        resp = client.get("/api/sync/icloud/status")

        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is True
        assert body["apple_id"] == "test@example.com"
        assert body["icloud_email"] == "test@icloud.com"


class TestSaveCredentials:
    def test_positiv_legt_neue_konfiguration_an(self, client, db_session):
        resp = client.post("/api/sync/icloud/credentials", json={
            "apple_id": "neu@example.com", "app_password": "geheim",
        })

        assert resp.status_code == 200
        cfg = db_session.query(models.ICloudSync).one()
        assert cfg.apple_id == "neu@example.com"

    def test_positiv_aktualisiert_bestehende_konfiguration(self, client, db_session):
        _cfg(db_session)

        resp = client.post("/api/sync/icloud/credentials", json={
            "apple_id": "neu@example.com", "app_password": "neues-geheimnis",
            "icloud_email": "neu@icloud.com", "web_password": "web-geheimnis",
        })

        assert resp.status_code == 200
        assert db_session.query(models.ICloudSync).count() == 1
        cfg = db_session.query(models.ICloudSync).one()
        assert cfg.apple_id == "neu@example.com"
        assert cfg.icloud_email == "neu@icloud.com"
        assert cfg.web_password_enc is not None


class TestSaveWebPassword:
    def test_positiv_aktualisiert_web_passwort(self, client, db_session):
        cfg = _cfg(db_session)

        resp = client.post("/api/sync/icloud/web-password", json={"code": "mein-apple-id-passwort"})

        assert resp.status_code == 204
        db_session.refresh(cfg)
        assert cfg.web_password_enc is not None

    def test_negativ_ohne_konfiguration_liefert_400(self, client, db_session):
        resp = client.post("/api/sync/icloud/web-password", json={"code": "x"})

        assert resp.status_code == 400


class TestConnectionTest:
    def test_negativ_ohne_konfiguration_liefert_400(self, client, db_session):
        resp = client.post("/api/sync/icloud/test")

        assert resp.status_code == 400

    def test_negativ_falsche_mail_domain_liefert_400(self, client, db_session):
        _cfg(db_session, icloud_email="nicht-icloud@gmail.com")

        resp = client.post("/api/sync/icloud/test")

        assert resp.status_code == 400
        assert "Mail-Sync benötigt" in resp.json()["detail"]

    def test_positiv_erfolgreiche_imap_verbindung(self, client, db_session, monkeypatch):
        _cfg(db_session, icloud_email="test@icloud.com")
        _fake_imap_conn(monkeypatch)

        resp = client.post("/api/sync/icloud/test")

        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_negativ_imap_fehler_liefert_400(self, client, db_session, monkeypatch):
        import imaplib

        _cfg(db_session, icloud_email="test@icloud.com")

        def _raise(host, port):
            raise imaplib.IMAP4.error("Login failed")

        monkeypatch.setattr("imaplib.IMAP4_SSL", _raise)

        resp = client.post("/api/sync/icloud/test")

        assert resp.status_code == 400
        assert "IMAP-Fehler" in resp.json()["detail"]

    def test_negativ_sonstiger_verbindungsfehler_liefert_502(self, client, db_session, monkeypatch):
        _cfg(db_session, icloud_email="test@icloud.com")

        def _raise(host, port):
            raise ConnectionError("DNS-Fehler")

        monkeypatch.setattr("imaplib.IMAP4_SSL", _raise)

        resp = client.post("/api/sync/icloud/test")

        assert resp.status_code == 502
        assert "Verbindungsfehler" in resp.json()["detail"]


class TestDeleteCredentials:
    def test_positiv_loescht_konfiguration(self, client, db_session):
        _cfg(db_session)

        resp = client.delete("/api/sync/icloud")

        assert resp.status_code == 204
        assert db_session.query(models.ICloudSync).count() == 0

    def test_negativ_ohne_konfiguration_ist_no_op(self, client, db_session):
        resp = client.delete("/api/sync/icloud")

        assert resp.status_code == 204


class TestResetEndpoints:
    @pytest.mark.parametrize("path,field", [
        ("/api/sync/icloud/mail/reset", "mail_last_sync"),
        ("/api/sync/icloud/notes/reset", "notes_last_sync"),
        ("/api/sync/icloud/calendar/reset", "calendar_last_sync"),
        ("/api/sync/icloud/reminders/reset", "reminders_last_sync"),
        ("/api/sync/icloud/contacts/reset", "contacts_last_sync"),
    ])
    def test_positiv_reset_setzt_last_sync_zurueck(self, client, db_session, path, field):
        from datetime import datetime, timezone
        cfg = _cfg(db_session, **{field: datetime.now(timezone.utc)})

        resp = client.post(path)

        assert resp.status_code == 204
        db_session.refresh(cfg)
        assert getattr(cfg, field) is None

    @pytest.mark.parametrize("path", [
        "/api/sync/icloud/mail/reset",
        "/api/sync/icloud/notes/reset",
        "/api/sync/icloud/calendar/reset",
        "/api/sync/icloud/reminders/reset",
        "/api/sync/icloud/contacts/reset",
    ])
    def test_negativ_reset_ohne_konfiguration_ist_no_op(self, client, db_session, path):
        resp = client.post(path)

        assert resp.status_code == 204

    def test_positiv_calls_reset_loescht_synced_items_und_events(self, client, db_session):
        app = application_factory(db_session)
        db_session.add(models.Event(
            application_id=app.id, typ="anruf", titel="Anruf", source="icloud_calls",
            external_id="icloud_calls:1", user_id=1,
        ))
        db_session.add(models.CallsConfig(enabled=True, user_id=1))
        db_session.commit()

        resp = client.post("/api/sync/icloud/calls/reset")

        assert resp.status_code == 204
        assert db_session.query(models.Event).filter_by(source="icloud_calls").count() == 0


class TestSyncTrigger:
    def test_negativ_mail_ohne_konfiguration_liefert_400(self, client, db_session):
        resp = client.post("/api/sync/icloud/mail")
        assert resp.status_code == 400

    def test_positiv_mail_mit_konfiguration_startet_hintergrundlauf(self, client, db_session, monkeypatch):
        _cfg(db_session)
        _fake_imap_conn(monkeypatch)

        resp = client.post("/api/sync/icloud/mail")

        assert resp.status_code == 200
        body = resp.json()
        assert body["processed"] == 0
        assert body["created"] == 0

    def test_negativ_calendar_ohne_konfiguration_liefert_400(self, client, db_session):
        resp = client.post("/api/sync/icloud/calendar")
        assert resp.status_code == 400

    def test_positiv_calendar_mit_konfiguration_startet_hintergrundlauf(self, client, db_session, monkeypatch):
        _cfg(db_session)
        _fake_caldav_client(monkeypatch, [FakeCaldavCalendar("Kalender")])

        resp = client.post("/api/sync/icloud/calendar")

        assert resp.status_code == 200

    def test_negativ_reminders_ohne_konfiguration_liefert_400(self, client, db_session):
        resp = client.post("/api/sync/icloud/reminders")
        assert resp.status_code == 400

    def test_positiv_reminders_mit_konfiguration_startet_hintergrundlauf(self, client, db_session, monkeypatch):
        _cfg(db_session)
        _fake_caldav_client(monkeypatch, [FakeCaldavCalendar("Erinnerungen")])

        resp = client.post("/api/sync/icloud/reminders")

        assert resp.status_code == 200

    def test_negativ_notes_ohne_konfiguration_liefert_400(self, client, db_session):
        resp = client.post("/api/sync/icloud/notes")
        assert resp.status_code == 400

    def test_positiv_notes_mit_konfiguration_startet_hintergrundlauf(self, client, db_session, monkeypatch):
        _cfg(db_session)

        async def fake_get(self, url, **kw):
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = []
            return resp

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        resp = client.post("/api/sync/icloud/notes")

        assert resp.status_code == 200

    def test_negativ_contacts_ohne_konfiguration_liefert_400(self, client, db_session):
        resp = client.post("/api/sync/icloud/contacts")
        assert resp.status_code == 400

    def test_positiv_contacts_mit_konfiguration_importiert_und_verlinkt_bestandskontakte(
        self, client, db_session, monkeypatch
    ):
        _cfg(db_session)
        # "Erika Musterfrau" existiert bereits (z.B. aus einem früheren Sync),
        # ist aber noch NICHT mit der Bewerbung verlinkt, obwohl sie im
        # Kommentartext erwähnt wird — der Sync muss diese Lücke per Backfill
        # schließen. Der neue vCard-Kontakt "Neuer Kontakt" landet zusätzlich
        # als frischer Import (Firmenname-Match), unabhängig vom Backfill.
        app = application_factory(db_session, firma="Contoso AG", kommentar="Telefonat mit Erika Musterfrau.")
        existing = contact_factory(db_session, name="Musterfrau", vorname="Erika", email="erika-bereits-da@example.com")
        db_session.commit()
        vcards = [icloud_vcard("Neuer Kontakt", family="Kontakt", given="Neuer", email="neu@contoso.com", org="Contoso AG")]

        async def fake_fetch(cfg_arg):
            return vcards

        monkeypatch.setattr("app.routers.sync_icloud.fetch_all_vcards", fake_fetch)

        resp = client.post("/api/sync/icloud/contacts")

        assert resp.status_code == 200
        body = resp.json()
        assert body["created"] == 1
        db_session.refresh(existing)
        assert app in existing.applications

    def test_negativ_calls_deaktiviert_liefert_sofortigen_hinweis(self, client, db_session):
        db_session.add(models.CallsConfig(enabled=False, user_id=1))
        db_session.commit()

        resp = client.post("/api/sync/icloud/calls")

        assert resp.status_code == 200
        assert resp.json()["errors"] == ["Anrufliste-Sync deaktiviert"]

    def test_positiv_calls_aktiviert_startet_hintergrundlauf(self, client, db_session, monkeypatch):
        db_session.add(models.CallsConfig(enabled=True, user_id=1))
        db_session.commit()

        async def fake_get(self, url, **kw):
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = []
            resp.raise_for_status = MagicMock()
            return resp

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        resp = client.post("/api/sync/icloud/calls")

        assert resp.status_code == 200


class TestCalendarDebug:
    def test_negativ_ohne_konfiguration_liefert_400(self, client, db_session):
        resp = client.get("/api/sync/icloud/calendar/debug")
        assert resp.status_code == 400

    def test_positiv_liefert_rohe_termine_sortiert_nach_datum(self, client, db_session, monkeypatch):
        _cfg(db_session)
        application_factory(db_session, firma="Contoso AG")
        db_session.commit()
        from datetime import datetime, timezone
        ev = icloud_calendar_event("evt-1", "Interview bei Contoso AG", datetime.now(timezone.utc))
        _fake_caldav_client(monkeypatch, [FakeCaldavCalendar("Kalender", events=[ev])])

        resp = client.get("/api/sync/icloud/calendar/debug")

        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 1
        assert results[0]["summary"] == "Interview bei Contoso AG"
        assert results[0]["has_keyword"] is True

    def test_negativ_caldav_fehler_liefert_502(self, client, db_session, monkeypatch):
        _cfg(db_session)
        _fake_caldav_client(monkeypatch, error=RuntimeError("401 Unauthorized"))

        resp = client.get("/api/sync/icloud/calendar/debug")

        assert resp.status_code == 502

    def test_negativ_caldav_bibliothek_fehlt_liefert_500(self, client, db_session, monkeypatch):
        import sys
        _cfg(db_session)
        monkeypatch.setitem(sys.modules, "caldav", None)

        resp = client.get("/api/sync/icloud/calendar/debug")

        assert resp.status_code == 500

    def test_negativ_kaputter_kalender_wird_still_uebersprungen(self, client, db_session, monkeypatch):
        _cfg(db_session)
        application_factory(db_session, firma="Contoso AG")
        db_session.commit()
        broken_cal = FakeCaldavCalendar("Kaputt", date_search_error=RuntimeError("500 Server Error"))
        _fake_caldav_client(monkeypatch, [broken_cal])

        resp = client.get("/api/sync/icloud/calendar/debug")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_negativ_kaputtes_event_wird_still_uebersprungen(self, client, db_session, monkeypatch):
        _cfg(db_session)
        application_factory(db_session, firma="Contoso AG")
        db_session.commit()

        class _BrokenEvent:
            url = "https://caldav.icloud.com/broken.ics"
            vobject_instance = object()  # kein .vevent-Attribut -> AttributeError

        _fake_caldav_client(monkeypatch, [FakeCaldavCalendar("Kalender", events=[_BrokenEvent()])])

        resp = client.get("/api/sync/icloud/calendar/debug")

        assert resp.status_code == 200
        assert resp.json() == []


class TestCallsStatusUndSettings:
    def test_positiv_status_liefert_konfiguration(self, client, db_session, monkeypatch):
        async def fake_get(self, url, **kw):
            resp = MagicMock()
            resp.status_code = 200
            return resp

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        resp = client.get("/api/sync/icloud/calls/status")

        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is True
        assert body["bridge_reachable"] is True

    def test_positiv_status_meldet_nicht_erreichbaren_agenten(self, client, db_session, monkeypatch):
        async def fake_get(self, url, **kw):
            raise ConnectionError("kein Agent")

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        resp = client.get("/api/sync/icloud/calls/status")

        assert resp.status_code == 200
        assert resp.json()["bridge_reachable"] is False

    def test_positiv_settings_deaktiviert_anrufliste_sync(self, client, db_session, monkeypatch):
        db_session.add(models.CallsConfig(enabled=True, user_id=1))
        db_session.commit()

        async def fake_get(self, url, **kw):
            raise ConnectionError("kein Agent")

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        resp = client.post("/api/sync/icloud/calls/settings", json={"enabled": False})

        assert resp.status_code == 200
        assert resp.json()["enabled"] is False
        cfg = db_session.query(models.CallsConfig).one()
        assert cfg.enabled is False
