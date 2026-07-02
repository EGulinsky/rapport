"""L2 API — /api/settings/maps: Google Maps API-Key wird verschlüsselt gespeichert,
nie im Klartext zurückgegeben (nur has_key)."""
import pytest

pytestmark = pytest.mark.api


class TestMapsSettings:
    def test_positiv_ohne_gespeicherten_key(self, client):
        resp = client.get("/api/settings/maps")

        assert resp.status_code == 200
        assert resp.json() == {"has_key": False}

    def test_positiv_key_speichern_setzt_has_key(self, client):
        resp = client.post("/api/settings/maps", json={"api_key": "AIzaTestKey123"})

        assert resp.status_code == 200
        assert resp.json() == {"has_key": True}

        # Der Klartext-Key darf in keiner Antwort auftauchen.
        get_resp = client.get("/api/settings/maps")
        assert "AIzaTestKey123" not in get_resp.text

    def test_positiv_key_loeschen(self, client):
        client.post("/api/settings/maps", json={"api_key": "AIzaTestKey123"})

        resp = client.delete("/api/settings/maps/key")

        assert resp.status_code == 200
        assert resp.json() == {"has_key": False}

    def test_negativ_leerer_key_wird_wie_kein_key_behandelt(self, client):
        resp = client.post("/api/settings/maps", json={"api_key": "  "})

        assert resp.status_code == 200
        assert resp.json() == {"has_key": False}
