"""L2 API — /api/auth/*: Registrierung mit E-Mail-Bestätigung, Login,
Passwort-Reset per Code, Passwort-Änderung. E-Mail-Versand wird an der
Netzwerkgrenze gemockt (app.routers.auth.send_verification_code), damit kein
echter SMTP-Server nötig ist.
"""
import pytest

pytestmark = pytest.mark.api


@pytest.fixture()
def captured_email(monkeypatch):
    """Fängt jeden 'gesendeten' Bestätigungscode ab, statt echtes SMTP zu nutzen."""
    box: dict = {}

    def fake_send(to_email, code, purpose):
        box["to"] = to_email
        box["code"] = code
        box["purpose"] = purpose

    monkeypatch.setattr("app.routers.auth.send_verification_code", fake_send)
    return box


def _register(real_auth_client, captured_email, email="test@example.com", password="supersecret123"):
    resp = real_auth_client.post("/api/auth/register", json={"email": email, "password": password})
    return resp


class TestRegister:
    def test_positiv_registrierung_sendet_bestaetigungscode(self, real_auth_client, captured_email):
        resp = _register(real_auth_client, captured_email)

        assert resp.status_code == 201
        assert captured_email["to"] == "test@example.com"
        assert captured_email["purpose"] == "verify_email"
        assert len(captured_email["code"]) == 6

    def test_negativ_doppelte_email_liefert_409(self, real_auth_client, captured_email):
        _register(real_auth_client, captured_email)
        resp = _register(real_auth_client, captured_email)
        assert resp.status_code == 409

    def test_negativ_zu_kurzes_passwort_liefert_422(self, real_auth_client, captured_email):
        resp = real_auth_client.post("/api/auth/register", json={"email": "kurz@example.com", "password": "1234567"})
        assert resp.status_code == 422

    def test_negativ_ungueltige_email_liefert_422(self, real_auth_client, captured_email):
        resp = real_auth_client.post("/api/auth/register", json={"email": "keine-email", "password": "supersecret123"})
        assert resp.status_code == 422


class TestVerifyEmail:
    def test_positiv_richtiger_code_aktiviert_konto_und_liefert_token(self, real_auth_client, captured_email):
        _register(real_auth_client, captured_email)

        resp = real_auth_client.post("/api/auth/verify-email", json={"email": "test@example.com", "code": captured_email["code"]})

        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_negativ_falscher_code_wird_abgelehnt(self, real_auth_client, captured_email):
        _register(real_auth_client, captured_email)

        resp = real_auth_client.post("/api/auth/verify-email", json={"email": "test@example.com", "code": "000000"})

        assert resp.status_code == 400

    def test_negativ_bereits_bestaetigtes_konto_kann_nicht_erneut_bestaetigt_werden(self, real_auth_client, captured_email):
        _register(real_auth_client, captured_email)
        code = captured_email["code"]
        real_auth_client.post("/api/auth/verify-email", json={"email": "test@example.com", "code": code})

        resp = real_auth_client.post("/api/auth/verify-email", json={"email": "test@example.com", "code": code})

        assert resp.status_code == 400

    def test_negativ_unbekannte_email_liefert_404(self, real_auth_client):
        resp = real_auth_client.post("/api/auth/verify-email", json={"email": "nichtregistriert@example.com", "code": "123456"})
        assert resp.status_code == 404


class TestLogin:
    def test_positiv_login_nach_verifizierung(self, real_auth_client, captured_email):
        _register(real_auth_client, captured_email)
        real_auth_client.post("/api/auth/verify-email", json={"email": "test@example.com", "code": captured_email["code"]})

        resp = real_auth_client.post("/api/auth/login", json={"email": "test@example.com", "password": "supersecret123"})

        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_negativ_login_vor_verifizierung_wird_abgelehnt(self, real_auth_client, captured_email):
        _register(real_auth_client, captured_email)

        resp = real_auth_client.post("/api/auth/login", json={"email": "test@example.com", "password": "supersecret123"})

        assert resp.status_code == 403

    def test_negativ_falsches_passwort(self, real_auth_client, captured_email):
        _register(real_auth_client, captured_email)
        real_auth_client.post("/api/auth/verify-email", json={"email": "test@example.com", "code": captured_email["code"]})

        resp = real_auth_client.post("/api/auth/login", json={"email": "test@example.com", "password": "falschespasswort"})

        assert resp.status_code == 401

    def test_negativ_unbekannte_email(self, real_auth_client):
        resp = real_auth_client.post("/api/auth/login", json={"email": "niemand@example.com", "password": "irgendwas123"})
        assert resp.status_code == 401


class TestMe:
    def test_positiv_liefert_eigene_daten_mit_gueltigem_token(self, real_auth_client, captured_email):
        _register(real_auth_client, captured_email)
        verify_resp = real_auth_client.post("/api/auth/verify-email", json={"email": "test@example.com", "code": captured_email["code"]})
        token = verify_resp.json()["access_token"]

        resp = real_auth_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

        assert resp.status_code == 200
        assert resp.json()["email"] == "test@example.com"
        assert resp.json()["email_verified"] is True

    def test_negativ_ohne_token_liefert_401(self, real_auth_client):
        resp = real_auth_client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_negativ_kaputtes_token_liefert_401(self, real_auth_client):
        resp = real_auth_client.get("/api/auth/me", headers={"Authorization": "Bearer kein-gueltiges-token"})
        assert resp.status_code == 401


class TestChangePassword:
    def _token(self, real_auth_client, captured_email):
        _register(real_auth_client, captured_email)
        r = real_auth_client.post("/api/auth/verify-email", json={"email": "test@example.com", "code": captured_email["code"]})
        return r.json()["access_token"]

    def test_positiv_passwort_aendern_und_neu_einloggen(self, real_auth_client, captured_email):
        token = self._token(real_auth_client, captured_email)

        resp = real_auth_client.post(
            "/api/auth/change-password",
            json={"old_password": "supersecret123", "new_password": "neuespasswort456"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

        login_resp = real_auth_client.post("/api/auth/login", json={"email": "test@example.com", "password": "neuespasswort456"})
        assert login_resp.status_code == 200

    def test_negativ_falsches_altes_passwort(self, real_auth_client, captured_email):
        token = self._token(real_auth_client, captured_email)

        resp = real_auth_client.post(
            "/api/auth/change-password",
            json={"old_password": "falsch", "new_password": "neuespasswort456"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 401


class TestForgotUndResetPassword:
    def test_positiv_voller_reset_fluss(self, real_auth_client, captured_email):
        _register(real_auth_client, captured_email)
        real_auth_client.post("/api/auth/verify-email", json={"email": "test@example.com", "code": captured_email["code"]})

        resp = real_auth_client.post("/api/auth/forgot-password", json={"email": "test@example.com"})
        assert resp.status_code == 200
        reset_code = captured_email["code"]
        assert captured_email["purpose"] == "reset_password"

        resp = real_auth_client.post(
            "/api/auth/reset-password",
            json={"email": "test@example.com", "code": reset_code, "new_password": "brandneu789"},
        )
        assert resp.status_code == 200

        login_resp = real_auth_client.post("/api/auth/login", json={"email": "test@example.com", "password": "brandneu789"})
        assert login_resp.status_code == 200

    def test_negativ_unbekannte_email_liefert_trotzdem_200(self, real_auth_client):
        # Verhindert User-Enumeration: keine unterschiedliche Antwort je nachdem,
        # ob die E-Mail-Adresse existiert.
        resp = real_auth_client.post("/api/auth/forgot-password", json={"email": "existiert-nicht@example.com"})
        assert resp.status_code == 200

    def test_negativ_falscher_reset_code_wird_abgelehnt(self, real_auth_client, captured_email):
        _register(real_auth_client, captured_email)
        real_auth_client.post("/api/auth/verify-email", json={"email": "test@example.com", "code": captured_email["code"]})
        real_auth_client.post("/api/auth/forgot-password", json={"email": "test@example.com"})

        resp = real_auth_client.post(
            "/api/auth/reset-password",
            json={"email": "test@example.com", "code": "000000", "new_password": "brandneu789"},
        )

        assert resp.status_code == 400

    def test_negativ_verify_code_kann_nicht_fuer_reset_missbraucht_werden(self, real_auth_client, captured_email):
        # Codes sind zweckgebunden (purpose) — ein noch gültiger Verifizierungs-Code
        # darf nicht als Passwort-Reset-Code akzeptiert werden.
        _register(real_auth_client, captured_email)
        verify_code = captured_email["code"]

        resp = real_auth_client.post(
            "/api/auth/reset-password",
            json={"email": "test@example.com", "code": verify_code, "new_password": "brandneu789"},
        )

        assert resp.status_code == 400


class TestClaimOnFirstVerify:
    def test_positiv_erstes_bestaetigtes_konto_erbt_bisherigen_datenbestand(self, real_auth_client, captured_email, db_session):
        from app import models
        from tests.factories import application_factory

        app = application_factory(db_session, user_id=None)
        db_session.commit()

        _register(real_auth_client, captured_email, email="first@example.com")
        resp = real_auth_client.post("/api/auth/verify-email", json={"email": "first@example.com", "code": captured_email["code"]})
        assert resp.status_code == 200

        user = db_session.query(models.User).filter_by(email="first@example.com").one()
        db_session.refresh(app)
        assert app.user_id == user.id

    def test_negativ_zweites_konto_erbt_nichts(self, real_auth_client, captured_email, db_session):
        from app import models
        from tests.factories import application_factory

        app = application_factory(db_session, user_id=None)
        db_session.commit()

        _register(real_auth_client, captured_email, email="first@example.com")
        real_auth_client.post("/api/auth/verify-email", json={"email": "first@example.com", "code": captured_email["code"]})
        first_user = db_session.query(models.User).filter_by(email="first@example.com").one()

        _register(real_auth_client, captured_email, email="second@example.com")
        real_auth_client.post("/api/auth/verify-email", json={"email": "second@example.com", "code": captured_email["code"]})

        db_session.refresh(app)
        assert app.user_id == first_user.id  # unverändert, gehört weiterhin dem ersten Konto
