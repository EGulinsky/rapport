"""Der aggregierte /health-Endpoint muss den Ausfall eines einzelnen Moduls
melden, ohne dass die anderen Module oder der Endpoint selbst mitreißen —
genau das Verhalten, das die drei alten Einzel-Bridges nicht hatten (ein
Absturz von notes_bridge.py sagte nichts über files_bridge.py aus)."""


class TestHealth:
    def test_positiv_alle_module_gesund(self, client):
        resp = client.get("/health")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["platform"] == "Darwin" or body["platform"] == "Windows" or body["platform"] == "Linux"
        assert body["modules"]["files"]["ok"] is True
        assert body["modules"]["notes"]["ok"] is True
        assert body["modules"]["calls"]["ok"] is True

    def test_negativ_ausfall_eines_moduls_reisst_andere_nicht_mit(
        self, test_config, fake_files_provider, fake_calls_provider
    ):
        from fastapi.testclient import TestClient

        from agent.main import create_app
        from agent.tests.conftest import FakeNotesProvider

        broken_notes = FakeNotesProvider(healthy=False)
        app = create_app(test_config, fake_files_provider, broken_notes, fake_calls_provider)
        client = TestClient(app)

        resp = client.get("/health")

        assert resp.status_code == 200
        body = resp.json()
        assert body["modules"]["notes"]["ok"] is False
        assert body["modules"]["files"]["ok"] is True
        assert body["modules"]["calls"]["ok"] is True

    def test_positiv_health_meldet_version(self, client):
        from agent.version import __version__

        resp = client.get("/health")
        assert resp.json()["version"] == __version__
