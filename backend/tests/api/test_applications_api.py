"""L2 API — FastAPI TestClient gegen echte Router (applications.py)."""
import pytest

from tests.factories import application_factory

pytestmark = pytest.mark.api


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

    def test_positiv_ort_kann_nachtraeglich_gesetzt_werden(self, client, db_session):
        app = application_factory(db_session, ort=None)
        db_session.commit()

        resp = client.patch(f"/api/applications/{app.id}", json={"ort": "Berlin, Deutschland"})

        assert resp.status_code == 200
        assert resp.json()["ort"] == "Berlin, Deutschland"
