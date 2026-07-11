"""L2 API — /api/auth/*: Registrierung mit E-Mail-Bestätigung, Login,
Passwort-Reset per Code, Passwort-Änderung. E-Mail-Versand wird an der
Netzwerkgrenze gemockt (app.routers.auth.send_verification_code), damit kein
echter SMTP-Server nötig ist.
"""
import pytest

pytestmark = pytest.mark.api

# Keine echten Geheimnisse — reine Test-Fixture-Werte für den Auth-Flow.
# Bewusst nicht "passwort-förmig" benannt, um GitGuardian-Fehlalarme zu vermeiden.
TESTPW_ORIGINAL = "not-a-real-secret-fixture-1"
TESTPW_NEW = "not-a-real-secret-fixture-2"
TESTPW_RESET = "not-a-real-secret-fixture-3"
TESTPW_WRONG = "not-a-real-secret-fixture-WRONG"
TESTPW_TOO_SHORT = "abcd123"


@pytest.fixture()
def captured_email(monkeypatch):
    """Fängt jeden 'gesendeten' Bestätigungscode ab, statt echtes SMTP zu nutzen."""
    box: dict = {}

    def fake_send(to_email, code, purpose, ui_language="de"):
        box["to"] = to_email
        box["code"] = code
        box["purpose"] = purpose
        box["ui_language"] = ui_language

    monkeypatch.setattr("app.routers.auth.send_verification_code", fake_send)
    return box


def _register(real_auth_client, captured_email, email="test@example.com", password=TESTPW_ORIGINAL):
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
        assert resp.json()["detail"]["error_key"] == "auth.email_already_registered"

    def test_negativ_zu_kurzes_passwort_liefert_422(self, real_auth_client, captured_email):
        resp = real_auth_client.post("/api/auth/register", json={"email": "kurz@example.com", "password": TESTPW_TOO_SHORT})
        assert resp.status_code == 422

    def test_negativ_ungueltige_email_liefert_422(self, real_auth_client, captured_email):
        resp = real_auth_client.post("/api/auth/register", json={"email": "keine-email", "password": TESTPW_ORIGINAL})
        assert resp.status_code == 422

    def test_positiv_ui_language_default_ist_englisch(self, real_auth_client, captured_email):
        _register(real_auth_client, captured_email)
        verify_resp = real_auth_client.post("/api/auth/verify-email", json={"email": "test@example.com", "code": captured_email["code"]})
        token = verify_resp.json()["access_token"]

        resp = real_auth_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.json()["ui_language"] == "en"

    def test_positiv_ui_language_kann_explizit_de_gesetzt_werden(self, real_auth_client, captured_email):
        resp = real_auth_client.post(
            "/api/auth/register",
            json={"email": "test@example.com", "password": TESTPW_ORIGINAL, "ui_language": "de"},
        )
        assert resp.status_code == 201
        verify_resp = real_auth_client.post("/api/auth/verify-email", json={"email": "test@example.com", "code": captured_email["code"]})
        token = verify_resp.json()["access_token"]

        me_resp = real_auth_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me_resp.json()["ui_language"] == "de"

    def test_negativ_ui_language_unbekannter_wert_liefert_422(self, real_auth_client, captured_email):
        resp = real_auth_client.post(
            "/api/auth/register",
            json={"email": "test@example.com", "password": TESTPW_ORIGINAL, "ui_language": "fr"},
        )
        assert resp.status_code == 422

    def test_positiv_bestaetigungsmail_wird_in_gewaehlter_sprache_verschickt(self, real_auth_client, captured_email):
        real_auth_client.post(
            "/api/auth/register",
            json={"email": "test@example.com", "password": TESTPW_ORIGINAL, "ui_language": "en"},
        )
        assert captured_email["ui_language"] == "en"


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
        assert resp.json()["detail"]["error_key"] == "auth.code_invalid"

    def test_negativ_bereits_bestaetigtes_konto_kann_nicht_erneut_bestaetigt_werden(self, real_auth_client, captured_email):
        _register(real_auth_client, captured_email)
        code = captured_email["code"]
        real_auth_client.post("/api/auth/verify-email", json={"email": "test@example.com", "code": code})

        resp = real_auth_client.post("/api/auth/verify-email", json={"email": "test@example.com", "code": code})

        assert resp.status_code == 400
        assert resp.json()["detail"]["error_key"] == "auth.already_verified"

    def test_negativ_unbekannte_email_liefert_404(self, real_auth_client):
        resp = real_auth_client.post("/api/auth/verify-email", json={"email": "nichtregistriert@example.com", "code": "123456"})
        assert resp.status_code == 404


class TestResendCode:
    def test_positiv_neuer_code_kann_bestaetigten(self, real_auth_client, captured_email):
        _register(real_auth_client, captured_email)

        resp = real_auth_client.post("/api/auth/resend-code", json={"email": "test@example.com"})

        assert resp.status_code == 200
        assert captured_email["purpose"] == "verify_email"
        neuer_code = captured_email["code"]
        verify_resp = real_auth_client.post("/api/auth/verify-email", json={"email": "test@example.com", "code": neuer_code})
        assert verify_resp.status_code == 200

    def test_negativ_bereits_bestaetigtes_konto_bekommt_keinen_neuen_code(self, real_auth_client, captured_email):
        _register(real_auth_client, captured_email)
        real_auth_client.post("/api/auth/verify-email", json={"email": "test@example.com", "code": captured_email["code"]})
        captured_email.clear()

        resp = real_auth_client.post("/api/auth/resend-code", json={"email": "test@example.com"})

        assert resp.status_code == 200
        assert captured_email == {}  # kein Versand ausgelöst

    def test_corner_case_unbekannte_email_liefert_trotzdem_200_ohne_versand(self, real_auth_client, captured_email):
        resp = real_auth_client.post("/api/auth/resend-code", json={"email": "nichtregistriert@example.com"})

        assert resp.status_code == 200
        assert captured_email == {}  # keine User-Enumeration: gleiche Antwort, kein Versand


class TestLogin:
    def test_positiv_login_nach_verifizierung(self, real_auth_client, captured_email):
        _register(real_auth_client, captured_email)
        real_auth_client.post("/api/auth/verify-email", json={"email": "test@example.com", "code": captured_email["code"]})

        resp = real_auth_client.post("/api/auth/login", json={"email": "test@example.com", "password": TESTPW_ORIGINAL})

        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_negativ_login_vor_verifizierung_wird_abgelehnt(self, real_auth_client, captured_email):
        _register(real_auth_client, captured_email)

        resp = real_auth_client.post("/api/auth/login", json={"email": "test@example.com", "password": TESTPW_ORIGINAL})

        assert resp.status_code == 403
        assert resp.json()["detail"]["error_key"] == "auth.email_not_verified"

    def test_negativ_falsches_passwort(self, real_auth_client, captured_email):
        _register(real_auth_client, captured_email)
        real_auth_client.post("/api/auth/verify-email", json={"email": "test@example.com", "code": captured_email["code"]})

        resp = real_auth_client.post("/api/auth/login", json={"email": "test@example.com", "password": TESTPW_WRONG})

        assert resp.status_code == 401
        assert resp.json()["detail"]["error_key"] == "auth.login_failed"

    def test_negativ_unbekannte_email(self, real_auth_client):
        resp = real_auth_client.post("/api/auth/login", json={"email": "niemand@example.com", "password": TESTPW_NEW})
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
            json={"old_password": TESTPW_ORIGINAL, "new_password": TESTPW_NEW},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

        login_resp = real_auth_client.post("/api/auth/login", json={"email": "test@example.com", "password": TESTPW_NEW})
        assert login_resp.status_code == 200

    def test_negativ_falsches_altes_passwort(self, real_auth_client, captured_email):
        token = self._token(real_auth_client, captured_email)

        resp = real_auth_client.post(
            "/api/auth/change-password",
            json={"old_password": TESTPW_WRONG, "new_password": TESTPW_NEW},
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
            json={"email": "test@example.com", "code": reset_code, "new_password": TESTPW_RESET},
        )
        assert resp.status_code == 200

        login_resp = real_auth_client.post("/api/auth/login", json={"email": "test@example.com", "password": TESTPW_RESET})
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
            json={"email": "test@example.com", "code": "000000", "new_password": TESTPW_RESET},
        )

        assert resp.status_code == 400

    def test_negativ_verify_code_kann_nicht_fuer_reset_missbraucht_werden(self, real_auth_client, captured_email):
        # Codes sind zweckgebunden (purpose) — ein noch gültiger Verifizierungs-Code
        # darf nicht als Passwort-Reset-Code akzeptiert werden.
        _register(real_auth_client, captured_email)
        verify_code = captured_email["code"]

        resp = real_auth_client.post(
            "/api/auth/reset-password",
            json={"email": "test@example.com", "code": verify_code, "new_password": TESTPW_RESET},
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


class TestProfileAndCv:
    def _token(self, real_auth_client, captured_email, email="test@example.com"):
        _register(real_auth_client, captured_email, email=email)
        r = real_auth_client.post("/api/auth/verify-email", json={"email": email, "code": captured_email["code"]})
        return r.json()["access_token"]

    def test_positiv_profil_speichern(self, real_auth_client, captured_email):
        token = self._token(real_auth_client, captured_email)

        resp = real_auth_client.patch(
            "/api/auth/profile",
            json={"vorname": "Ada", "nachname": "Lovelace", "linkedin_url": "https://www.linkedin.com/in/ada-lovelace"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["vorname"] == "Ada"
        assert body["nachname"] == "Lovelace"
        assert body["linkedin_url"] == "https://www.linkedin.com/in/ada-lovelace"

    def test_negativ_profil_ohne_token_liefert_401(self, real_auth_client):
        resp = real_auth_client.patch("/api/auth/profile", json={"vorname": "Ada"})
        assert resp.status_code == 401

    def test_positiv_ui_language_kann_geaendert_werden(self, real_auth_client, captured_email):
        token = self._token(real_auth_client, captured_email)

        resp = real_auth_client.patch(
            "/api/auth/profile", json={"ui_language": "de"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        assert resp.json()["ui_language"] == "de"

    def test_corner_case_profil_update_ohne_ui_language_aendert_sie_nicht(self, real_auth_client, captured_email):
        """Ein Profil-Save aus einem anderen Tab (z.B. Vorname) darf die zuvor
        gesetzte UI-Sprache nicht klammheimlich zurücksetzen, nur weil das Feld
        im Payload fehlt — anders als vorname/nachname/linkedin_url, die dieser
        Endpoint bewusst unconditional überschreibt."""
        token = self._token(real_auth_client, captured_email)
        real_auth_client.patch(
            "/api/auth/profile", json={"ui_language": "de"},
            headers={"Authorization": f"Bearer {token}"},
        )

        resp = real_auth_client.patch(
            "/api/auth/profile", json={"vorname": "Ada", "nachname": "Lovelace", "linkedin_url": None},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        assert resp.json()["ui_language"] == "de"

    def test_corner_case_profil_felder_koennen_wieder_geleert_werden(self, real_auth_client, captured_email):
        token = self._token(real_auth_client, captured_email)
        real_auth_client.patch(
            "/api/auth/profile", json={"vorname": "Ada", "nachname": "Lovelace", "linkedin_url": "https://example.com"},
            headers={"Authorization": f"Bearer {token}"},
        )

        resp = real_auth_client.patch(
            "/api/auth/profile", json={"vorname": None, "nachname": None, "linkedin_url": None},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        assert resp.json()["vorname"] is None

    def test_positiv_cv_hochladen(self, real_auth_client, captured_email):
        token = self._token(real_auth_client, captured_email)

        resp = real_auth_client.post(
            "/api/auth/cv",
            files={"file": ("lebenslauf.pdf", b"%PDF-1.4 fake cv content", "application/pdf")},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["cv_filename"] == "lebenslauf.pdf"
        assert body["cv_size_bytes"] == len(b"%PDF-1.4 fake cv content")

    def test_negativ_falsche_dateiendung_wird_abgelehnt(self, real_auth_client, captured_email):
        token = self._token(real_auth_client, captured_email)

        resp = real_auth_client.post(
            "/api/auth/cv",
            files={"file": ("lebenslauf.exe", b"irrelevant", "application/octet-stream")},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 400
        assert resp.json()["detail"]["error_key"] == "auth.cv_type_invalid"

    def test_negativ_zu_grosse_datei_wird_abgelehnt(self, real_auth_client, captured_email, monkeypatch):
        monkeypatch.setattr("app.routers.auth.MAX_CV_BYTES", 10)
        token = self._token(real_auth_client, captured_email)

        resp = real_auth_client.post(
            "/api/auth/cv",
            files={"file": ("lebenslauf.pdf", b"eine deutlich laengere Datei als 10 Bytes", "application/pdf")},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 413
        assert resp.json()["detail"]["error_key"] == "auth.cv_too_large"

    def test_positiv_cv_erneut_hochladen_ersetzt_alte_datei(self, real_auth_client, captured_email):
        token = self._token(real_auth_client, captured_email)
        headers = {"Authorization": f"Bearer {token}"}
        real_auth_client.post("/api/auth/cv", files={"file": ("alt.pdf", b"alte version", "application/pdf")}, headers=headers)

        resp = real_auth_client.post("/api/auth/cv", files={"file": ("neu.pdf", b"neue version", "application/pdf")}, headers=headers)

        assert resp.status_code == 201
        assert resp.json()["cv_filename"] == "neu.pdf"

    def test_positiv_cv_herunterladen(self, real_auth_client, captured_email):
        token = self._token(real_auth_client, captured_email)
        headers = {"Authorization": f"Bearer {token}"}
        real_auth_client.post("/api/auth/cv", files={"file": ("lebenslauf.pdf", b"cv inhalt", "application/pdf")}, headers=headers)

        resp = real_auth_client.get("/api/auth/cv", headers=headers)

        assert resp.status_code == 200
        assert resp.content == b"cv inhalt"

    def test_negativ_cv_herunterladen_ohne_upload_liefert_404(self, real_auth_client, captured_email):
        token = self._token(real_auth_client, captured_email)

        resp = real_auth_client.get("/api/auth/cv", headers={"Authorization": f"Bearer {token}"})

        assert resp.status_code == 404

    def test_positiv_cv_loeschen(self, real_auth_client, captured_email):
        token = self._token(real_auth_client, captured_email)
        headers = {"Authorization": f"Bearer {token}"}
        real_auth_client.post("/api/auth/cv", files={"file": ("lebenslauf.pdf", b"cv inhalt", "application/pdf")}, headers=headers)

        resp = real_auth_client.delete("/api/auth/cv", headers=headers)
        assert resp.status_code == 204

        me_resp = real_auth_client.get("/api/auth/me", headers=headers)
        assert me_resp.json()["cv_filename"] is None
