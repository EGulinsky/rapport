"""L2 API — FastAPI TestClient gegen echte Router (applications.py)."""
from datetime import date

import pytest

from tests.factories import application_factory, contact_factory, event_factory
from app import models

pytestmark = pytest.mark.api


class TestCreateApplicationSchedulesPostCreateSync:
    """create_application() schedules _do_post_create_sync() as a background
    task (see applications.py) — TestClient runs background tasks
    synchronously in-process, so we can assert on the call directly rather
    than polling. skip_linkedin is driven by the request's
    created_from_linkedin field (see schemas.ApplicationCreate's docstring
    for why: LinkedInImportModal-prefilled saves set it True, everything
    else defaults to False)."""

    def test_positiv_default_ruft_post_create_sync_mit_skip_linkedin_false_auf(self, client, monkeypatch):
        calls = []

        async def fake_post_create_sync(app_id, skip_linkedin):
            calls.append((app_id, skip_linkedin))

        monkeypatch.setattr("app.routers.sync_targeted._do_post_create_sync", fake_post_create_sync)

        resp = client.post("/api/applications/", json={
            "firma": "Test GmbH", "rolle": "Software Engineer", "main_status": "applied",
        })

        assert resp.status_code == 201
        assert len(calls) == 1
        assert calls[0] == (resp.json()["id"], False)

    def test_positiv_created_from_linkedin_ruft_mit_skip_linkedin_true_auf(self, client, monkeypatch):
        calls = []

        async def fake_post_create_sync(app_id, skip_linkedin):
            calls.append((app_id, skip_linkedin))

        monkeypatch.setattr("app.routers.sync_targeted._do_post_create_sync", fake_post_create_sync)

        resp = client.post("/api/applications/", json={
            "firma": "Test GmbH", "rolle": "Software Engineer", "main_status": "applied",
            "created_from_linkedin": True,
        })

        assert resp.status_code == 201
        assert len(calls) == 1
        assert calls[0] == (resp.json()["id"], True)


class TestCreateApplication:
    def test_positiv_bewerbung_anlegen(self, client):
        resp = client.post("/api/applications/", json={
            "firma": "Test GmbH",
            "rolle": "Software Engineer",
            "main_status": "applied",
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["firma"] == "Test GmbH"
        assert body["id"] is not None
        # Beim Anlegen wird automatisch ein Event typ="bewerbung" erstellt.
        assert any(e["typ"] == "bewerbung" for e in body["events"])

    def test_negativ_fehlende_pflichtfelder(self, client):
        resp = client.post("/api/applications/", json={"quelle": "LinkedIn"})
        assert resp.status_code == 422

    def test_fehleingabe_falscher_datentyp(self, client):
        resp = client.post("/api/applications/", json={
            "firma": "Test GmbH",
            "rolle": "Engineer",
            "main_status": 12345,  # muss ein String sein
        })
        assert resp.status_code == 422

    def test_corner_case_sehr_langer_kommentar(self, client):
        resp = client.post("/api/applications/", json={
            "firma": "Test GmbH",
            "rolle": "Engineer",
            "kommentar": "x" * 20_000,
        })
        assert resp.status_code == 201

    def test_positiv_ort_ist_optional_und_wird_gespeichert(self, client):
        resp = client.post("/api/applications/", json={
            "firma": "Test GmbH",
            "rolle": "Engineer",
            "ort": "München, Deutschland",
        })
        assert resp.status_code == 201
        assert resp.json()["ort"] == "München, Deutschland"

    def test_negativ_ort_ist_kein_pflichtfeld(self, client):
        resp = client.post("/api/applications/", json={
            "firma": "Test GmbH",
            "rolle": "Engineer",
        })
        assert resp.status_code == 201
        assert resp.json()["ort"] is None


class TestListApplicationsSearch:
    def test_positiv_suche_matcht_firma(self, client, db_session):
        application_factory(db_session, firma="Contoso AG")
        application_factory(db_session, firma="Andere Firma GmbH")
        db_session.commit()

        resp = client.get("/api/applications/", params={"search": "Contoso"})

        assert resp.status_code == 200
        assert [a["firma"] for a in resp.json()] == ["Contoso AG"]

    def test_positiv_suche_matcht_zielfirma_bei_headhunter(self, client, db_session):
        # Regressionsfall: die entfernte "Firmenfilter"-UI matchte zusätzlich zur
        # firma auch die zielfirma_bei_hh (Kunde eines Headhunters). Damit die
        # normale Textsuche diese Funktion vollständig übernehmen kann, muss das
        # Suchfeld dasselbe Feld ebenfalls durchsuchen.
        application_factory(
            db_session, firma="Headhunter XY", is_headhunter=True, zielfirma_bei_hh="Zielfirma GmbH",
        )
        db_session.commit()

        resp = client.get("/api/applications/", params={"search": "Zielfirma"})

        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["zielfirma_bei_hh"] == "Zielfirma GmbH"

    def test_negativ_suche_ohne_treffer(self, client, db_session):
        application_factory(db_session, firma="Contoso AG")
        db_session.commit()

        resp = client.get("/api/applications/", params={"search": "Nichts Passendes"})

        assert resp.status_code == 200
        assert resp.json() == []

    def test_positiv_ort_ist_in_der_liste_enthalten(self, client, db_session):
        # Regressionsfall: ApplicationListItem (Response-Schema der Listen-Route, die
        # auch die Kanban-Karten befüllt) deklarierte "ort" nicht — Pydantic hat das
        # Feld deshalb aus der Antwort gefiltert, obwohl es in der DB gesetzt war.
        # Live-verifiziert: Ort war im Modal sichtbar, aber nicht auf der Kanban-Karte.
        application_factory(db_session, firma="Contoso AG", ort="Berlin, Deutschland")
        db_session.commit()

        resp = client.get("/api/applications/")

        assert resp.status_code == 200
        assert resp.json()[0]["ort"] == "Berlin, Deutschland"


class TestGetApplication:
    def test_positiv_bewerbung_abrufen(self, client, db_session):
        app = application_factory(db_session, firma="Abruf GmbH")
        db_session.commit()

        resp = client.get(f"/api/applications/{app.id}")

        assert resp.status_code == 200
        assert resp.json()["firma"] == "Abruf GmbH"

    def test_negativ_nicht_existierende_id(self, client):
        resp = client.get("/api/applications/999999")
        assert resp.status_code == 404
        assert resp.json()["detail"]["error_key"] == "application.not_found"

    def test_fehleingabe_ungueltige_id(self, client):
        resp = client.get("/api/applications/not-a-number")
        assert resp.status_code == 422


class TestUpdateApplication:
    def test_positiv_status_rejected_setzt_abgesagt(self, client, db_session):
        app = application_factory(db_session, main_status="applied")
        db_session.commit()

        resp = client.patch(f"/api/applications/{app.id}", json={"main_status": "rejected"})

        assert resp.status_code == 200
        assert resp.json()["abgesagt"] is True

    def test_corner_case_sub_status_wird_bei_statuswechsel_zurueckgesetzt(self, client, db_session):
        app = application_factory(db_session, main_status="hr", sub_status="1_scheduled")
        db_session.commit()

        resp = client.patch(f"/api/applications/{app.id}", json={"main_status": "waiting"})

        assert resp.status_code == 200
        assert resp.json()["sub_status"] is None

    def test_negativ_update_nicht_existierender_bewerbung(self, client):
        resp = client.patch("/api/applications/999999", json={"main_status": "applied"})
        assert resp.status_code == 404
        assert resp.json()["detail"]["error_key"] == "application.not_found"

    def test_positiv_ort_kann_nachtraeglich_gesetzt_werden(self, client, db_session):
        app = application_factory(db_session, ort=None)
        db_session.commit()

        resp = client.patch(f"/api/applications/{app.id}", json={"ort": "Berlin, Deutschland"})

        assert resp.status_code == 200
        assert resp.json()["ort"] == "Berlin, Deutschland"


class TestBulkDeleteEvents:
    def test_positiv_mehrere_events_werden_geloescht(self, client, db_session):
        app = application_factory(db_session)
        ev1 = event_factory(db_session, app, typ="notiz", titel="Notiz 1")
        ev2 = event_factory(db_session, app, typ="notiz", titel="Notiz 2")
        keep = event_factory(db_session, app, typ="notiz", titel="Bleibt")
        db_session.commit()

        resp = client.request("DELETE", f"/api/applications/{app.id}/events/bulk", json={"ids": [ev1.id, ev2.id]})

        assert resp.status_code == 200
        assert resp.json()["deleted"] == 2
        assert db_session.get(models.Event, ev1.id) is None
        assert db_session.get(models.Event, ev2.id) is None
        assert db_session.get(models.Event, keep.id) is not None

    def test_positiv_loeschen_von_bewerbung_event_setzt_datum_bewerbung_neu(self, client, db_session):
        app = application_factory(db_session, datum_bewerbung=None)
        older = event_factory(db_session, app, typ="bewerbung", datum=date(2026, 1, 1))
        newer = event_factory(db_session, app, typ="bewerbung", datum=date(2026, 2, 1))
        app.datum_bewerbung = older.datum
        db_session.commit()

        resp = client.request("DELETE", f"/api/applications/{app.id}/events/bulk", json={"ids": [older.id]})

        assert resp.status_code == 200
        db_session.refresh(app)
        assert app.datum_bewerbung == newer.datum

    def test_positiv_ignoriert_ids_aus_anderer_bewerbung(self, client, db_session):
        app = application_factory(db_session)
        other_app = application_factory(db_session)
        foreign_event = event_factory(db_session, other_app, typ="notiz")
        db_session.commit()

        resp = client.request("DELETE", f"/api/applications/{app.id}/events/bulk", json={"ids": [foreign_event.id]})

        assert resp.status_code == 200
        assert resp.json()["deleted"] == 0
        assert db_session.get(models.Event, foreign_event.id) is not None

    def test_positiv_audit_log_wird_pro_event_geschrieben(self, client, db_session):
        app = application_factory(db_session)
        ev = event_factory(db_session, app, typ="notiz", titel="Zu löschen")
        db_session.commit()

        resp = client.request("DELETE", f"/api/applications/{app.id}/events/bulk", json={"ids": [ev.id]})

        assert resp.status_code == 200
        audit = db_session.query(models.AuditLog).filter_by(event_id=ev.id, action="delete").first()
        assert audit is not None
        assert audit.old_value == "Zu löschen"


class TestBulkDeleteAppContacts:
    def test_positiv_einziger_link_loescht_kontakt_ganz(self, client, db_session):
        app = application_factory(db_session)
        contact = contact_factory(db_session, name="Nur hier verknüpft")
        app.contacts.append(contact)
        db_session.commit()

        resp = client.request("DELETE", f"/api/applications/{app.id}/contacts/bulk", json={"ids": [contact.id]})

        assert resp.status_code == 200
        assert resp.json()["deleted"] == 1
        assert db_session.get(models.Contact, contact.id) is None

    def test_positiv_kontakt_mit_zweiter_bewerbung_wird_nur_entknuepft(self, client, db_session):
        app1 = application_factory(db_session)
        app2 = application_factory(db_session)
        contact = contact_factory(db_session, name="Zwei Bewerbungen")
        app1.contacts.append(contact)
        app2.contacts.append(contact)
        db_session.commit()

        resp = client.request("DELETE", f"/api/applications/{app1.id}/contacts/bulk", json={"ids": [contact.id]})

        assert resp.status_code == 200
        assert resp.json()["deleted"] == 1
        still_there = db_session.get(models.Contact, contact.id)
        assert still_there is not None
        assert app2 in still_there.applications

    def test_positiv_mehrere_kontakte_gemischt(self, client, db_session):
        app = application_factory(db_session)
        c1 = contact_factory(db_session, name="Kontakt 1")
        c2 = contact_factory(db_session, name="Kontakt 2")
        app.contacts.append(c1)
        app.contacts.append(c2)
        db_session.commit()

        resp = client.request("DELETE", f"/api/applications/{app.id}/contacts/bulk", json={"ids": [c1.id, c2.id]})

        assert resp.status_code == 200
        assert resp.json()["deleted"] == 2

    def test_negativ_unbekannte_bewerbung_liefert_404(self, client):
        resp = client.request("DELETE", "/api/applications/999999/contacts/bulk", json={"ids": [1]})
        assert resp.status_code == 404
        assert resp.json()["detail"]["error_key"] == "application.not_found"

    def test_corner_case_unbekannte_kontakt_id_wird_uebersprungen(self, client, db_session):
        app = application_factory(db_session)
        db_session.commit()

        resp = client.request("DELETE", f"/api/applications/{app.id}/contacts/bulk", json={"ids": [999999]})

        assert resp.status_code == 200
        assert resp.json()["deleted"] == 0
