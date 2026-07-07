"""
Geteilte Fixtures für alle Teststufen.

WICHTIG: DATABASE_URL wird gesetzt, BEVOR irgendein `app.*`-Modul importiert
wird — app/database.py bindet Engine/SessionLocal beim Import an die zu dem
Zeitpunkt aktive Umgebungsvariable. So laufen Tests garantiert nie gegen die
echte /app/data/jobtracker.db.
"""
import os
import tempfile

_TEST_DB_DIR = tempfile.mkdtemp(prefix="rapport_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_DIR}/test.db"
os.environ.setdefault("LOG_LEVEL", "ERROR")
os.environ.setdefault("SEQ_URL", "http://seq-not-reachable-in-tests:5341")

import pytest  # noqa: E402
from faker import Faker  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine, SessionLocal  # noqa: E402  (Reihenfolge ist Absicht, siehe oben)
from app import models  # noqa: E402,F401  (registriert alle Model-Klassen auf Base.metadata)


@pytest.fixture(autouse=True)
def _reset_db():
    """Frische, leere Tabellen vor jedem einzelnen Test — keine Kopplung zwischen Testfällen."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture()
def db_session():
    """Direkte DB-Session für L1-Component-Tests (ohne HTTP-Layer)."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# Feste ID des simulierten eingeloggten Nutzers für den `client`-Fixture —
# tests/factories.py setzt denselben Wert standardmäßig auf jede
# mandantengebundene Zeile, damit bestehende Tests (ohne jede Auth-Änderung)
# ihre eigenen Test-Daten weiterhin sehen.
DEFAULT_TEST_USER_ID = 1


@pytest.fixture()
def client(db_session):
    """FastAPI TestClient für L2-API-Tests — nutzt dieselbe Session wie db_session,
    damit Test-Setup (z.B. per Factory angelegte Objekte) und Request denselben
    Datenbankzustand sehen. Lifespan (Background-Sync-Loop, echte Startup-Checks)
    wird bewusst NICHT getriggert (kein `with TestClient(...)`-Contextmanager).

    get_current_user() wird direkt überschrieben (kein echter Registrierungs-/
    Login-Fluss, keine Zeile in der users-Tabelle) — das hält die bestehenden,
    nicht-auth-bezogenen Tests unverändert lauffähig, ohne die "erstes je
    bestätigtes Konto"-Zählung für die claim_unowned_data()-Tests zu verfälschen."""
    from app.main import app
    from app.database import get_db, set_session_user
    from app.auth.dependencies import get_current_user

    fake_user = models.User(
        id=DEFAULT_TEST_USER_ID, email="test-client@example.com",
        password_hash="x", email_verified=True,
    )

    def _override_get_db():
        yield db_session

    def _override_get_current_user():
        set_session_user(db_session, fake_user.id)
        return fake_user

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_get_current_user
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def real_auth_client(db_session):
    """Wie `client`, aber OHNE die get_current_user()-Überschreibung — für Tests
    des Auth-Systems selbst (tests/api/test_auth_api.py), die echte Tokens,
    echte 401-Fälle und die echte users-Tabelle brauchen."""
    from app.main import app
    from app.database import get_db

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _deterministic_faker():
    """Fester Seed pro Test — Fehlschläge sind reproduzierbar."""
    Faker.seed(1234)
