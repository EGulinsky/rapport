"""Bearer-Token schützt jeden Endpoint außer /health — das ist die einzige
Sicherheitsgrenze des Agenten (siehe auth.py Docstring)."""


class TestAuth:
    def test_positiv_health_ohne_token_erreichbar(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_negativ_geschuetzter_endpoint_ohne_token_401(self, client):
        resp = client.get("/notes")
        assert resp.status_code == 401

    def test_negativ_falscher_token_401(self, client):
        resp = client.get("/notes", headers={"Authorization": "Bearer falscher-token"})
        assert resp.status_code == 401

    def test_positiv_korrekter_token_200(self, client, auth_headers):
        resp = client.get("/notes", headers=auth_headers)
        assert resp.status_code == 200

    def test_corner_case_token_ohne_bearer_praefix_401(self, client, test_config):
        resp = client.get("/notes", headers={"Authorization": test_config.token})
        assert resp.status_code == 401
