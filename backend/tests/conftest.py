"""
Geteilte Fixtures für alle Teststufen.

WICHTIG: DATABASE_URL wird gesetzt, BEVOR irgendein `app.*`-Modul importiert
wird — app/database.py bindet Engine/SessionLocal beim Import an die zu dem
Zeitpunkt aktive Umgebungsvariable. So laufen Tests garantiert nie gegen die
echte /app/data/jobtracker.db.
"""
import os
import tempfile

_TEST_DB_DIR = tempfile.mkdtemp(prefix="jobtracker_test_")
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


@pytest.fixture()
def client(db_session):
    """FastAPI TestClient für L2-API-Tests — nutzt dieselbe Session wie db_session,
    damit Test-Setup (z.B. per Factory angelegte Objekte) und Request denselben
    Datenbankzustand sehen. Lifespan (Background-Sync-Loop, echte Startup-Checks)
    wird bewusst NICHT getriggert (kein `with TestClient(...)`-Contextmanager)."""
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
