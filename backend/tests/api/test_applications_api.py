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
