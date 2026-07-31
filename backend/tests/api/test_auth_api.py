"""L2 API — /api/auth/*: simple registration (email+password, JWT returned
directly — no email-verification step and no password-reset flow; both
required sending mail, which no longer exists here — see git history for the
removed verify-email/resend-code and forgot-password/reset-password flows),
login, password change.
"""
import pytest

pytestmark = pytest.mark.api

# Keine echten Geheimnisse — reine Test-Fixture-Werte für den Auth-Flow.
# Bewusst nicht "passwort-förmig" benannt, um GitGuardian-Fehlalarme zu vermeiden.
TESTPW_ORIGINAL = "not-a-real-secret-fixture-1"
TESTPW_NEW = "not-a-real-secret-fixture-2"
TESTPW_WRONG = "not-a-real-secret-fixture-WRONG"
TESTPW_TOO_SHORT = "abcd123"


def _register(real_auth_client, email="test@example.com", password=TESTPW_ORIGINAL, ui_language=None):
    payload = {"email": email, "password": password}
    if ui_language is not None:
        payload["ui_language"] = ui_language
    return real_auth_client.post("/api/auth/register", json=payload)


def _token(real_auth_client, email="test@example.com", password=TESTPW_ORIGINAL) -> str:
    return _register(real_auth_client, email=email, password=password).json()["access_token"]


class TestRegister:
    def test_positiv_registrierung_liefert_token_direkt(self, real_auth_client):
        resp = _register(real_auth_client)

        assert resp.status_code == 201
        assert "access_token" in resp.json()

    def test_negativ_doppelte_email_liefert_409(self, real_auth_client):
        _register(real_auth_client)
        resp = _register(real_auth_client)
        assert resp.status_code == 409
        assert resp.json()["detail"]["error_key"] == "auth.email_already_registered"

    def test_negativ_zu_kurzes_passwort_liefert_422(self, real_auth_client):
        resp = real_auth_client.post("/api/auth/register", json={"email": "kurz@example.com", "password": TESTPW_TOO_SHORT})
        assert resp.status_code == 422

    def test_negativ_ungueltige_email_liefert_422(self, real_auth_client):
        resp = real_auth_client.post("/api/auth/register", json={"email": "keine-email", "password": TESTPW_ORIGINAL})
        assert resp.status_code == 422

    def test_positiv_ui_language_default_ist_englisch(self, real_auth_client):
        token = _token(real_auth_client)

        resp = real_auth_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.json()["ui_language"] == "en"

    def test_positiv_ui_language_kann_explizit_de_gesetzt_werden(self, real_auth_client):
        resp = _register(real_auth_client, ui_language="de")
        assert resp.status_code == 201
        token = resp.json()["access_token"]

        me_resp = real_auth_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me_resp.json()["ui_language"] == "de"

    def test_negativ_ui_language_unbekannter_wert_liefert_422(self, real_auth_client):
        resp = real_auth_client.post(
            "/api/auth/register",
            json={"email": "test@example.com", "password": TESTPW_ORIGINAL, "ui_language": "fr"},
        )
        assert resp.status_code == 422


class TestLogin:
    def test_positiv_login_nach_registrierung(self, real_auth_client):
        _register(real_auth_client)

        resp = real_auth_client.post("/api/auth/login", json={"email": "test@example.com", "password": TESTPW_ORIGINAL})

        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_negativ_falsches_passwort(self, real_auth_client):
        _register(real_auth_client)

        resp = real_auth_client.post("/api/auth/login", json={"email": "test@example.com", "password": TESTPW_WRONG})

        assert resp.status_code == 401
        assert resp.json()["detail"]["error_key"] == "auth.login_failed"

    def test_negativ_unbekannte_email(self, real_auth_client):
        resp = real_auth_client.post("/api/auth/login", json={"email": "niemand@example.com", "password": TESTPW_NEW})
        assert resp.status_code == 401


class TestMe:
    def test_positiv_liefert_eigene_daten_mit_gueltigem_token(self, real_auth_client):
        token = _token(real_auth_client)

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
    def test_positiv_passwort_aendern_und_neu_einloggen(self, real_auth_client):
        token = _token(real_auth_client)

        resp = real_auth_client.post(
            "/api/auth/change-password",
            json={"old_password": TESTPW_ORIGINAL, "new_password": TESTPW_NEW},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

        login_resp = real_auth_client.post("/api/auth/login", json={"email": "test@example.com", "password": TESTPW_NEW})
        assert login_resp.status_code == 200

    def test_negativ_falsches_altes_passwort(self, real_auth_client):
        token = _token(real_auth_client)

        resp = real_auth_client.post(
            "/api/auth/change-password",
            json={"old_password": TESTPW_WRONG, "new_password": TESTPW_NEW},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 401


class TestClaimOnFirstRegistration:
    """claim_unowned_data() (pre-account, user_id IS NULL rows adopted by the
    very first account) used to trigger on the first *verified* account; now
    that there's no verification step, the equivalent moment is the first
    account ever *registered* — see register() in auth.py."""

    def test_positiv_erstes_konto_erbt_bisherigen_datenbestand(self, real_auth_client, db_session):
        from app import models
        from tests.factories import application_factory

        app = application_factory(db_session, user_id=None)
        db_session.commit()

        resp = _register(real_auth_client, email="first@example.com")
        assert resp.status_code == 201

        user = db_session.query(models.User).filter_by(email="first@example.com").one()
        db_session.refresh(app)
        assert app.user_id == user.id

    def test_negativ_zweites_konto_erbt_nichts(self, real_auth_client, db_session):
        from app import models
        from tests.factories import application_factory

        app = application_factory(db_session, user_id=None)
        db_session.commit()

        _register(real_auth_client, email="first@example.com")
        first_user = db_session.query(models.User).filter_by(email="first@example.com").one()

        _register(real_auth_client, email="second@example.com")

        db_session.refresh(app)
        assert app.user_id == first_user.id  # unverändert, gehört weiterhin dem ersten Konto


class TestProfileAndCv:
    def test_positiv_profil_speichern(self, real_auth_client):
        token = _token(real_auth_client)

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

    def test_positiv_ui_language_kann_geaendert_werden(self, real_auth_client):
        token = _token(real_auth_client)

        resp = real_auth_client.patch(
            "/api/auth/profile", json={"ui_language": "de"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        assert resp.json()["ui_language"] == "de"

    def test_corner_case_profil_update_ohne_ui_language_aendert_sie_nicht(self, real_auth_client):
        """Ein Profil-Save aus einem anderen Tab (z.B. Vorname) darf die zuvor
        gesetzte UI-Sprache nicht klammheimlich zurücksetzen, nur weil das Feld
        im Payload fehlt — anders als vorname/nachname/linkedin_url, die dieser
        Endpoint bewusst unconditional überschreibt."""
        token = _token(real_auth_client)
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

    def test_positiv_sprachwechsel_pusht_an_gepaarten_agent(self, real_auth_client, db_session):
        """Ein Sprachwechsel im Account-Panel muss auch den bereits gepaarten
        Agent aktualisieren — nicht nur beim (Wieder-)Speichern des Agent-Tokens
        in Settings → Agent (siehe test_settings_agent_api.py::TestAgentUiLanguagePush)."""
        from unittest.mock import MagicMock, patch
        from app import models
        from app.ai.provider import encrypt_api_key

        token = _token(real_auth_client)
        db_session.add(models.AgentSettings(user_id=1, token_enc=encrypt_api_key("AgentToken123")))
        db_session.commit()

        calls = []

        async def fake_patch(self, url, **kw):
            calls.append((url, kw.get("json")))
            return MagicMock(status_code=200)

        # Registrierung setzt bereits ui_language="en" per Default — auf "de"
        # wechseln ist damit eine echte Änderung und muss den Push auslösen.
        with patch("httpx.AsyncClient.patch", new=fake_patch):
            resp = real_auth_client.patch(
                "/api/auth/profile", json={"ui_language": "de"},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 200
        assert len(calls) == 1
        url, payload = calls[0]
        assert url.endswith("/config")
        assert payload == {"ui_language": "de"}

    def test_negativ_kein_push_ohne_gepaarten_agent(self, real_auth_client):
        from unittest.mock import MagicMock, patch

        token = _token(real_auth_client)
        calls = []

        async def fake_patch(self, url, **kw):
            calls.append((url, kw.get("json")))
            return MagicMock(status_code=200)

        with patch("httpx.AsyncClient.patch", new=fake_patch):
            resp = real_auth_client.patch(
                "/api/auth/profile", json={"ui_language": "de"},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 200
        assert len(calls) == 0

    def test_negativ_kein_push_wenn_sprache_unveraendert(self, real_auth_client, db_session):
        from unittest.mock import MagicMock, patch
        from app import models
        from app.ai.provider import encrypt_api_key

        token = _token(real_auth_client)
        db_session.add(models.AgentSettings(user_id=1, token_enc=encrypt_api_key("AgentToken123")))
        db_session.commit()

        calls = []

        async def fake_patch(self, url, **kw):
            calls.append((url, kw.get("json")))
            return MagicMock(status_code=200)

        # Registrierung setzt bereits ui_language="en" per Default — derselbe Wert
        # nochmal zu senden, darf keinen (unnötigen) Push auslösen.
        with patch("httpx.AsyncClient.patch", new=fake_patch):
            resp = real_auth_client.patch(
                "/api/auth/profile", json={"ui_language": "en"},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 200
        assert len(calls) == 0

    def test_corner_case_profil_felder_koennen_wieder_geleert_werden(self, real_auth_client):
        token = _token(real_auth_client)
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

    def test_positiv_cv_hochladen(self, real_auth_client):
        token = _token(real_auth_client)

        resp = real_auth_client.post(
            "/api/auth/cv",
            files={"file": ("lebenslauf.pdf", b"%PDF-1.4 fake cv content", "application/pdf")},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["cv_filename"] == "lebenslauf.pdf"
        assert body["cv_size_bytes"] == len(b"%PDF-1.4 fake cv content")

    def test_negativ_falsche_dateiendung_wird_abgelehnt(self, real_auth_client):
        token = _token(real_auth_client)

        resp = real_auth_client.post(
            "/api/auth/cv",
            files={"file": ("lebenslauf.exe", b"irrelevant", "application/octet-stream")},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 400
        assert resp.json()["detail"]["error_key"] == "auth.cv_type_invalid"

    def test_negativ_zu_grosse_datei_wird_abgelehnt(self, real_auth_client, monkeypatch):
        monkeypatch.setattr("app.routers.auth.MAX_CV_BYTES", 10)
        token = _token(real_auth_client)

        resp = real_auth_client.post(
            "/api/auth/cv",
            files={"file": ("lebenslauf.pdf", b"eine deutlich laengere Datei als 10 Bytes", "application/pdf")},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 413
        assert resp.json()["detail"]["error_key"] == "auth.cv_too_large"

    def test_positiv_cv_erneut_hochladen_ersetzt_alte_datei(self, real_auth_client):
        token = _token(real_auth_client)
        headers = {"Authorization": f"Bearer {token}"}
        real_auth_client.post("/api/auth/cv", files={"file": ("alt.pdf", b"alte version", "application/pdf")}, headers=headers)

        resp = real_auth_client.post("/api/auth/cv", files={"file": ("neu.pdf", b"neue version", "application/pdf")}, headers=headers)

        assert resp.status_code == 201
        assert resp.json()["cv_filename"] == "neu.pdf"

    def test_positiv_cv_herunterladen(self, real_auth_client):
        token = _token(real_auth_client)
        headers = {"Authorization": f"Bearer {token}"}
        real_auth_client.post("/api/auth/cv", files={"file": ("lebenslauf.pdf", b"cv inhalt", "application/pdf")}, headers=headers)

        resp = real_auth_client.get("/api/auth/cv", headers=headers)

        assert resp.status_code == 200
        assert resp.content == b"cv inhalt"

    def test_negativ_cv_herunterladen_ohne_upload_liefert_404(self, real_auth_client):
        token = _token(real_auth_client)

        resp = real_auth_client.get("/api/auth/cv", headers={"Authorization": f"Bearer {token}"})

        assert resp.status_code == 404

    def test_positiv_cv_loeschen(self, real_auth_client):
        token = _token(real_auth_client)
        headers = {"Authorization": f"Bearer {token}"}
        real_auth_client.post("/api/auth/cv", files={"file": ("lebenslauf.pdf", b"cv inhalt", "application/pdf")}, headers=headers)

        resp = real_auth_client.delete("/api/auth/cv", headers=headers)
        assert resp.status_code == 204

        me_resp = real_auth_client.get("/api/auth/me", headers=headers)
        assert me_resp.json()["cv_filename"] is None

    def test_positiv_cv_upload_extrahiert_und_cached_text(self, real_auth_client, db_session, monkeypatch):
        """Extraction happens once at upload time, not per AI assessment —
        see User.cv_extracted_text's docstring in models.py for why."""
        from app import models
        monkeypatch.setattr("app.cv_extract.extract_cv_text", lambda path: "Extracted résumé text")
        token = _token(real_auth_client)

        resp = real_auth_client.post(
            "/api/auth/cv",
            files={"file": ("lebenslauf.pdf", b"%PDF-1.4 fake cv content", "application/pdf")},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 201
        user = db_session.query(models.User).filter_by(email="test@example.com").one()
        assert user.cv_extracted_text == "Extracted résumé text"

    def test_positiv_cv_loeschen_leert_extrahierten_text(self, real_auth_client, db_session):
        from app import models
        token = _token(real_auth_client)
        headers = {"Authorization": f"Bearer {token}"}
        real_auth_client.post("/api/auth/cv", files={"file": ("lebenslauf.pdf", b"cv inhalt", "application/pdf")}, headers=headers)
        user = db_session.query(models.User).filter_by(email="test@example.com").one()
        user.cv_extracted_text = "some cached text"
        db_session.commit()

        resp = real_auth_client.delete("/api/auth/cv", headers=headers)

        assert resp.status_code == 204
        db_session.refresh(user)
        assert user.cv_extracted_text is None


class TestSalaryDefaults:
    def test_positiv_speichern_und_lesen(self, real_auth_client):
        token = _token(real_auth_client)
        headers = {"Authorization": f"Bearer {token}"}

        resp = real_auth_client.patch(
            "/api/auth/profile",
            json={
                "default_salary_currency": "USD",
                "default_salary_expectation_min": 60000,
                "default_salary_expectation_max": 70000,
                "default_salary_expectation_company_car": True,
            },
            headers=headers,
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["default_salary_currency"] == "USD"
        assert body["default_salary_expectation_min"] == 60000
        assert body["default_salary_expectation_max"] == 70000
        assert body["default_salary_expectation_company_car"] is True

        assert real_auth_client.get("/api/auth/me", headers=headers).json()["default_salary_expectation_min"] == 60000

    def test_negativ_max_ohne_min_liefert_400(self, real_auth_client):
        token = _token(real_auth_client)
        resp = real_auth_client.patch(
            "/api/auth/profile",
            json={"default_salary_expectation_max": 70000},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400

    def test_negativ_max_kleiner_min_liefert_400(self, real_auth_client):
        token = _token(real_auth_client)
        resp = real_auth_client.patch(
            "/api/auth/profile",
            json={"default_salary_expectation_min": 70000, "default_salary_expectation_max": 60000},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400

    def test_negativ_nur_fixum_ohne_bonus_liefert_400(self, real_auth_client):
        token = _token(real_auth_client)
        resp = real_auth_client.patch(
            "/api/auth/profile",
            json={"default_salary_expectation_min": 60000, "default_salary_expectation_min_fixed": 50000},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400

    def test_negativ_fixum_plus_bonus_ungleich_gesamt_liefert_400(self, real_auth_client):
        token = _token(real_auth_client)
        resp = real_auth_client.patch(
            "/api/auth/profile",
            json={
                "default_salary_expectation_min": 60000,
                "default_salary_expectation_min_fixed": 50000,
                "default_salary_expectation_min_bonus": 5000,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400

    def test_positiv_fixum_plus_bonus_gleich_gesamt_wird_akzeptiert(self, real_auth_client):
        token = _token(real_auth_client)
        resp = real_auth_client.patch(
            "/api/auth/profile",
            json={
                "default_salary_expectation_min": 60000,
                "default_salary_expectation_min_fixed": 50000,
                "default_salary_expectation_min_bonus": 10000,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    def test_corner_case_anderer_profil_save_loescht_salary_defaults_nicht(self, real_auth_client):
        token = _token(real_auth_client)
        headers = {"Authorization": f"Bearer {token}"}
        real_auth_client.patch(
            "/api/auth/profile",
            json={"default_salary_currency": "USD", "default_salary_expectation_min": 60000},
            headers=headers,
        )

        resp = real_auth_client.patch(
            "/api/auth/profile",
            json={
                "vorname": "Ada",
                "default_salary_currency": "USD",
                "default_salary_expectation_min": 60000,
            },
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["default_salary_expectation_min"] == 60000


class TestHomeLocation:
    """Home address for the distance-to-job feature (KanbanBoard/
    ApplicationModal) -- geocoded once when home_location changes (see
    update_profile() in auth.py), not on every profile save."""

    def test_positiv_speichern_geocodiert_und_setzt_koordinaten(self, real_auth_client, db_session, monkeypatch):
        from app import models

        async def fake_geocode_one(term, api_key):
            assert term == "Berlin, Deutschland"
            return (52.52, 13.405)
        monkeypatch.setattr("app.routers.geo.geocode_one", fake_geocode_one)

        token = _token(real_auth_client)
        resp = real_auth_client.patch(
            "/api/auth/profile", json={"home_location": "Berlin, Deutschland"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        assert resp.json()["home_location"] == "Berlin, Deutschland"
        user = db_session.query(models.User).filter_by(email="test@example.com").one()
        assert user.home_lat == 52.52
        assert user.home_lng == 13.405

    def test_negativ_geocoding_fehlschlag_laesst_koordinaten_leer(self, real_auth_client, db_session, monkeypatch):
        from app import models

        async def fake_geocode_one(term, api_key):
            return None
        monkeypatch.setattr("app.routers.geo.geocode_one", fake_geocode_one)

        token = _token(real_auth_client)
        resp = real_auth_client.patch(
            "/api/auth/profile", json={"home_location": "Nirgendwostadt"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        user = db_session.query(models.User).filter_by(email="test@example.com").one()
        assert user.home_lat is None
        assert user.home_lng is None

    def test_positiv_leeren_loescht_koordinaten(self, real_auth_client, db_session, monkeypatch):
        from app import models

        async def fake_geocode_one(term, api_key):
            return (52.52, 13.405)
        monkeypatch.setattr("app.routers.geo.geocode_one", fake_geocode_one)

        token = _token(real_auth_client)
        headers = {"Authorization": f"Bearer {token}"}
        real_auth_client.patch("/api/auth/profile", json={"home_location": "Berlin, Deutschland"}, headers=headers)

        resp = real_auth_client.patch("/api/auth/profile", json={"home_location": None}, headers=headers)

        assert resp.status_code == 200
        user = db_session.query(models.User).filter_by(email="test@example.com").one()
        assert user.home_location is None
        assert user.home_lat is None
        assert user.home_lng is None

    def test_negativ_unveraenderte_home_location_geokodiert_nicht_erneut(self, real_auth_client, monkeypatch):
        """A profile save that doesn't touch home_location (e.g. just vorname)
        must not burn an extra geocoding call every time."""
        calls = []

        async def fake_geocode_one(term, api_key):
            calls.append(term)
            return (52.52, 13.405)
        monkeypatch.setattr("app.routers.geo.geocode_one", fake_geocode_one)

        token = _token(real_auth_client)
        headers = {"Authorization": f"Bearer {token}"}
        real_auth_client.patch("/api/auth/profile", json={"home_location": "Berlin, Deutschland"}, headers=headers)
        assert len(calls) == 1

        real_auth_client.patch("/api/auth/profile", json={"home_location": "Berlin, Deutschland", "vorname": "Ada"}, headers=headers)

        assert len(calls) == 1

    def test_positiv_aenderung_loescht_cached_drive_distance_fuer_alle_apps(self, real_auth_client, db_session, monkeypatch):
        # Every application's cached drive_distance_km/drive_duration_min was
        # computed from the OLD home coordinates -- must be cleared in bulk
        # so a stale distance never lingers after moving (see
        # backfill_drive_distance() for how it gets repopulated).
        from app import models
        from tests.factories import application_factory

        async def fake_geocode_one(term, api_key):
            return (52.52, 13.405)
        monkeypatch.setattr("app.routers.geo.geocode_one", fake_geocode_one)

        token = _token(real_auth_client)
        headers = {"Authorization": f"Bearer {token}"}
        user = db_session.query(models.User).filter_by(email="test@example.com").one()
        app = application_factory(db_session, ort="München", ort_lat=48.1351, ort_lng=11.5820,
                                   drive_distance_km=504.0, drive_duration_min=312.0, user_id=user.id)
        db_session.commit()

        resp = real_auth_client.patch("/api/auth/profile", json={"home_location": "Berlin, Deutschland"}, headers=headers)

        assert resp.status_code == 200
        db_session.refresh(app)
        assert app.drive_distance_km is None
        assert app.drive_duration_min is None
