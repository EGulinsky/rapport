"""L1 Unit — inline SQLite migration functions in app/database.py.

Previously almost entirely uncovered (12%) since they only run once at real
app startup. Strategy: build a fresh SQLite file with the FULL current
schema (via Base.metadata.create_all against a temp engine), then strip the
specific column(s)/table(s)/index(es) a given migration is responsible for
before calling it directly — proving it (a) adds what's missing and
(b) is a no-op (idempotent) when already applied.
"""
import sqlite3

import pytest
from sqlalchemy import create_engine

from app import database as db_module
from app.database import Base

pytestmark = pytest.mark.unit


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    path = str(tmp_path / "migration_test.db")
    monkeypatch.setattr(db_module, "DATABASE_URL", f"sqlite:///{path}")
    eng = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(bind=eng)
    eng.dispose()
    return path


def _cols(path, table):
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    result = {row[1] for row in cur.fetchall()}
    conn.close()
    return result


def _drop_columns(path, table, *columns):
    # Plain "ALTER TABLE ... DROP COLUMN" refuses columns that participate in
    # a foreign key, index, or UNIQUE constraint (SQLite limitation) — most of
    # the columns these migrations add are exactly that. Rebuilding via
    # CREATE TABLE ... AS SELECT sidesteps it (constraints aren't relevant to
    # these tests, only column presence).
    #
    # Triggers on OTHER tables that reference this one (e.g. trg_main_status_change
    # on applications, which INSERTs into audit_log) aren't dropped by "DROP TABLE"
    # itself, and some SQLite builds validate them eagerly at DROP time — raising
    # "no such table" even though the table is about to be recreated under the same
    # name a statement later. Drop and recreate those triggers around the rebuild.
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='trigger' AND sql LIKE ?",
        (f"%{table}%",),
    )
    dependent_triggers = cur.fetchall()
    for name, _sql in dependent_triggers:
        cur.execute(f"DROP TRIGGER {name}")
    cur.execute(f"PRAGMA table_info({table})")
    keep = [row[1] for row in cur.fetchall() if row[1] not in columns]
    cur.execute(f"CREATE TABLE {table}__tmp AS SELECT {', '.join(keep)} FROM {table}")
    cur.execute(f"DROP TABLE {table}")
    cur.execute(f"ALTER TABLE {table}__tmp RENAME TO {table}")
    for _name, sql in dependent_triggers:
        cur.execute(sql)
    conn.commit()
    conn.close()


def _drop_table(path, table):
    conn = sqlite3.connect(path)
    conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.commit()
    conn.close()


def _exec(path, sql, params=()):
    conn = sqlite3.connect(path)
    conn.execute(sql, params)
    conn.commit()
    conn.close()


def _table_exists(path, table):
    conn = sqlite3.connect(path)
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    conn.close()
    return row is not None


def _index_exists(path, index):
    conn = sqlite3.connect(path)
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?", (index,)
    ).fetchone()
    conn.close()
    return row is not None


class TestNoFreshDbGuard:
    """Every migration must no-op silently when the DB file doesn't exist yet."""

    @pytest.mark.parametrize("fn_name", [
        "_migrate_status_fields", "_migrate_icloud", "_fix_mail_event_dates",
        "_migrate_contacts_m2m", "_migrate_calls", "_migrate_gespraeche_to_events",
        "_migrate_sync_settings_files", "_migrate_google_email", "_migrate_attachments",
        "_migrate_event_external_id", "_migrate_linkedin_job_id",
        "_migrate_pre_rejection_status", "_migrate_audit_log", "_migrate_audit_log_entities",
        "_migrate_company_profiles", "_backfill_company_profiles",
        "_migrate_contact_company_profile", "_migrate_company_logo",
        "_migrate_company_parent", "_migrate_contact_vorname", "_migrate_ai_assessment",
        "_migrate_application_ort", "_migrate_add_user_id_columns", "_migrate_user_profile",
        "_migrate_linkedin_profile_cache",
        "_migrate_audit_log_entity_type", "_backfill_events",
        "_backfill_event_datum_zeit_noon",
        "_migrate_event_datum_zeit_is_placeholder", "_flag_noon_backfill_placeholders",
        "_migrate_event_external_url", "_backfill_linkedin_message_external_url",
        "_migrate_event_mail_direction",
        "_migrate_user_home_location", "_migrate_application_ort_coords",
        "_migrate_application_drive_distance",
    ])
    def test_positiv_kein_fehler_wenn_db_datei_fehlt(self, tmp_path, monkeypatch, fn_name):
        monkeypatch.setattr(db_module, "DATABASE_URL", f"sqlite:///{tmp_path}/does-not-exist.db")
        getattr(db_module, fn_name)()  # must not raise


class TestMigrateStatusFields:
    def test_positiv_fuegt_main_und_sub_status_hinzu(self, db_path):
        _drop_columns(db_path, "applications", "main_status", "sub_status")

        db_module._migrate_status_fields()

        cols = _cols(db_path, "applications")
        assert "main_status" in cols
        assert "sub_status" in cols

    def test_positiv_migriert_alte_status_werte(self, db_path):
        _drop_columns(db_path, "applications", "main_status", "sub_status")
        _exec(db_path, "ALTER TABLE applications ADD COLUMN status TEXT")
        _exec(db_path, "INSERT INTO applications (firma, rolle, status) VALUES ('X', 'Y', 'beworben')")

        db_module._migrate_status_fields()

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT main_status FROM applications").fetchone()
        conn.close()
        assert row[0] is not None

    def test_positiv_legacy_spalten_werden_entfernt(self, db_path):
        _exec(db_path, "ALTER TABLE applications ADD COLUMN status TEXT")

        db_module._migrate_status_fields()

        assert "status" not in _cols(db_path, "applications")

    def test_corner_case_idempotent_bei_zweitem_lauf(self, db_path):
        db_module._migrate_status_fields()
        db_module._migrate_status_fields()  # must not raise
        assert "main_status" in _cols(db_path, "applications")


class TestMigrateIcloud:
    def test_positiv_fuegt_spalten_hinzu(self, db_path):
        _drop_columns(db_path, "icloud_sync", "icloud_email", "web_password_enc")

        db_module._migrate_icloud()

        cols = _cols(db_path, "icloud_sync")
        assert "icloud_email" in cols
        assert "web_password_enc" in cols

    def test_negativ_tabelle_fehlt_wird_uebersprungen(self, db_path):
        _drop_table(db_path, "icloud_sync")
        db_module._migrate_icloud()  # must not raise


class TestFixMailEventDates:
    def test_positiv_korrigiert_zukuenftiges_datum_bei_mail_events(self, db_path):
        _exec(db_path, """
            INSERT INTO applications (firma, rolle, main_status) VALUES ('X', 'Y', 'applied')
        """)
        _exec(db_path, """
            INSERT INTO events (application_id, typ, datum, source, created_at)
            VALUES (1, 'notiz', '2030-01-01', 'gmail', '2026-01-01 10:00:00')
        """)

        db_module._fix_mail_event_dates()

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT datum FROM events").fetchone()
        conn.close()
        assert row[0] == "2026-01-01"

    def test_negativ_tabelle_fehlt_wird_uebersprungen(self, db_path):
        _drop_table(db_path, "events")
        db_module._fix_mail_event_dates()  # must not raise


class TestMigrateContactsM2M:
    def test_positiv_erstellt_join_tabelle_und_backfillt(self, db_path):
        _drop_table(db_path, "contact_application")
        _exec(db_path, "ALTER TABLE contacts ADD COLUMN application_id INTEGER")
        _exec(db_path, "INSERT INTO applications (firma, rolle, main_status) VALUES ('X', 'Y', 'applied')")
        _exec(db_path, "INSERT INTO contacts (name, application_id) VALUES ('Max', 1)")

        db_module._migrate_contacts_m2m()

        assert _table_exists(db_path, "contact_application")
        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT contact_id, application_id FROM contact_application").fetchone()
        conn.close()
        assert row == (1, 1)

    def test_corner_case_bereits_vorhanden_wird_nicht_neu_erstellt(self, db_path):
        db_module._migrate_contacts_m2m()  # already exists via create_all
        db_module._migrate_contacts_m2m()  # must not raise (idempotent)

    def test_negativ_contacts_tabelle_fehlt_wird_uebersprungen(self, db_path):
        _drop_table(db_path, "contacts")
        db_module._migrate_contacts_m2m()  # must not raise


class TestMigrateCalls:
    def test_positiv_fuegt_spalte_hinzu(self, db_path):
        _drop_columns(db_path, "icloud_sync", "calls_last_sync")
        db_module._migrate_calls()
        assert "calls_last_sync" in _cols(db_path, "icloud_sync")

    def test_negativ_tabelle_fehlt_wird_uebersprungen(self, db_path):
        _drop_table(db_path, "icloud_sync")
        db_module._migrate_calls()  # must not raise


class TestMigrateGespraecheToEvents:
    def test_positiv_erstellt_gespraech_events_aus_datumsfeldern(self, db_path):
        _exec(db_path, "INSERT INTO applications (firma, rolle, main_status, gespraech_1) VALUES ('X', 'Y', 'applied', '2026-03-01 10:00:00')")

        db_module._migrate_gespraeche_to_events()

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT typ, datum FROM events WHERE typ='gespräch'").fetchone()
        conn.close()
        assert row == ("gespräch", "2026-03-01")

    def test_negativ_ungueltiges_datum_wird_uebersprungen(self, db_path):
        _exec(db_path, "INSERT INTO applications (firma, rolle, main_status, gespraech_1) VALUES ('X', 'Y', 'applied', 'nicht-valide')")

        db_module._migrate_gespraeche_to_events()  # must not raise

        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM events WHERE typ='gespräch'").fetchone()[0]
        conn.close()
        assert count == 0

    def test_corner_case_doppelter_lauf_erstellt_kein_duplikat(self, db_path):
        _exec(db_path, "INSERT INTO applications (firma, rolle, main_status, gespraech_1) VALUES ('X', 'Y', 'applied', '2026-03-01 10:00:00')")
        db_module._migrate_gespraeche_to_events()
        db_module._migrate_gespraeche_to_events()

        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM events WHERE typ='gespräch'").fetchone()[0]
        conn.close()
        assert count == 1

    def test_negativ_events_tabelle_fehlt_wird_uebersprungen(self, db_path):
        _drop_table(db_path, "events")
        db_module._migrate_gespraeche_to_events()  # must not raise


class TestMigrateSyncSettingsFiles:
    def test_positiv_fuegt_spalte_hinzu(self, db_path):
        _drop_columns(db_path, "sync_settings", "files_enabled")
        db_module._migrate_sync_settings_files()
        assert "files_enabled" in _cols(db_path, "sync_settings")

    def test_negativ_tabelle_fehlt_wird_uebersprungen(self, db_path):
        _drop_table(db_path, "sync_settings")
        db_module._migrate_sync_settings_files()  # must not raise


class TestMigrateGoogleEmail:
    def test_positiv_fuegt_spalte_hinzu(self, db_path):
        _drop_columns(db_path, "google_sync", "gmail_email")
        db_module._migrate_google_email()
        assert "gmail_email" in _cols(db_path, "google_sync")

    def test_negativ_tabelle_fehlt_wird_uebersprungen(self, db_path):
        _drop_table(db_path, "google_sync")
        db_module._migrate_google_email()  # must not raise


class TestMigrateAttachments:
    def test_positiv_erstellt_tabelle_und_verzeichnis(self, db_path, tmp_path):
        _drop_table(db_path, "attachments")

        db_module._migrate_attachments()

        assert _table_exists(db_path, "attachments")
        assert (tmp_path / "attachments").is_dir()

    def test_corner_case_idempotent(self, db_path):
        db_module._migrate_attachments()
        db_module._migrate_attachments()  # must not raise


class TestMigrateEventExternalId:
    def test_positiv_fuegt_spalte_hinzu(self, db_path):
        _drop_columns(db_path, "events", "external_id")
        db_module._migrate_event_external_id()
        assert "external_id" in _cols(db_path, "events")


class TestMigrateLinkedinJobId:
    def test_positiv_fuegt_spalte_und_index_hinzu(self, db_path):
        _drop_columns(db_path, "applications", "linkedin_job_id")
        db_module._migrate_linkedin_job_id()
        assert "linkedin_job_id" in _cols(db_path, "applications")
        assert _index_exists(db_path, "ix_applications_linkedin_job_id")


class TestMigratePreRejectionStatus:
    def test_positiv_fuegt_spalte_hinzu(self, db_path):
        _drop_columns(db_path, "applications", "pre_rejection_status")
        db_module._migrate_pre_rejection_status()
        assert "pre_rejection_status" in _cols(db_path, "applications")

    def test_positiv_backfillt_aus_gespraech_events(self, db_path):
        _exec(db_path, "INSERT INTO applications (firma, rolle, main_status) VALUES ('X', 'Y', 'rejected')")
        _exec(db_path, "INSERT INTO events (application_id, typ, datum) VALUES (1, 'gespräch', '2026-01-01')")

        db_module._migrate_pre_rejection_status()

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT pre_rejection_status FROM applications WHERE id=1").fetchone()
        conn.close()
        assert row[0] == "hr"

    def test_positiv_hoehere_stufe_ueberschreibt_niedrigere(self, db_path):
        _exec(db_path, "INSERT INTO applications (firma, rolle, main_status) VALUES ('X', 'Y', 'rejected')")
        _exec(db_path, "INSERT INTO events (application_id, typ, datum) VALUES (1, 'gespräch', '2026-01-01')")
        _exec(db_path, "INSERT INTO events (application_id, typ, datum, titel) VALUES (1, 'status', '2026-02-01', 'Angebotsverhandlung gestartet')")

        db_module._migrate_pre_rejection_status()

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT pre_rejection_status FROM applications WHERE id=1").fetchone()
        conn.close()
        assert row[0] == "negotiating"


class TestMigrateAuditLog:
    def test_positiv_erstellt_tabelle_spalte_und_trigger(self, db_path):
        _drop_table(db_path, "audit_log")
        _drop_columns(db_path, "sync_settings", "audit_log_level")

        db_module._migrate_audit_log()

        assert _table_exists(db_path, "audit_log")
        assert "audit_log_level" in _cols(db_path, "sync_settings")

    def test_positiv_trigger_protokolliert_status_wechsel(self, db_path):
        db_module._migrate_audit_log()
        _exec(db_path, "INSERT INTO applications (firma, rolle, main_status) VALUES ('X', 'Y', 'applied')")
        _exec(db_path, "UPDATE applications SET main_status='hr' WHERE id=1")

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT source, old_value, new_value FROM audit_log WHERE action='status_change'").fetchone()
        conn.close()
        assert row == ("db_trigger", "applied", "hr")

    def test_corner_case_idempotent(self, db_path):
        db_module._migrate_audit_log()
        db_module._migrate_audit_log()  # must not raise


class TestMigrateAuditLogEntities:
    def test_positiv_fuegt_entitaets_spalten_hinzu(self, db_path):
        db_module._migrate_audit_log()  # ensure audit_log table exists first
        _drop_columns(db_path, "audit_log", "contact_id", "company_profile_id", "event_id")

        db_module._migrate_audit_log_entities()

        cols = _cols(db_path, "audit_log")
        assert {"contact_id", "company_profile_id", "event_id"} <= cols
        assert _index_exists(db_path, "ix_audit_log_contact_id")

    def test_negativ_audit_log_tabelle_fehlt_wird_uebersprungen(self, db_path):
        _drop_table(db_path, "audit_log")
        db_module._migrate_audit_log_entities()  # must not raise


class TestMigrateCompanyProfiles:
    def test_positiv_fuegt_fk_spalten_hinzu(self, db_path):
        _drop_columns(db_path, "applications", "company_profile_id", "target_company_profile_id")
        db_module._migrate_company_profiles()
        cols = _cols(db_path, "applications")
        assert "company_profile_id" in cols
        assert "target_company_profile_id" in cols


class TestBackfillCompanyProfiles:
    def test_positiv_legt_profile_fuer_bestehende_firmen_an(self, db_path):
        _exec(db_path, "INSERT INTO applications (firma, rolle, main_status) VALUES ('Contoso GmbH', 'Engineer', 'applied')")

        db_module._backfill_company_profiles()

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT company_profile_id FROM applications WHERE id=1").fetchone()
        profile = conn.execute("SELECT name_display FROM company_profiles").fetchone()
        conn.close()
        assert row[0] is not None
        assert profile[0] == "Contoso GmbH"

    def test_negativ_company_profiles_tabelle_fehlt_wird_uebersprungen(self, db_path):
        _drop_table(db_path, "company_profiles")
        db_module._backfill_company_profiles()  # must not raise


class TestMigrateContactCompanyProfile:
    def test_positiv_fuegt_spalte_hinzu(self, db_path):
        _drop_columns(db_path, "contacts", "company_profile_id")
        db_module._migrate_contact_company_profile()
        assert "company_profile_id" in _cols(db_path, "contacts")


class TestMigrateCompanyLogo:
    def test_positiv_fuegt_spalte_hinzu(self, db_path):
        _drop_columns(db_path, "company_profiles", "logo_data")
        db_module._migrate_company_logo()
        assert "logo_data" in _cols(db_path, "company_profiles")


class TestMigrateCompanyParent:
    def test_positiv_fuegt_spalte_hinzu(self, db_path):
        _drop_columns(db_path, "company_profiles", "parent_company_id")
        db_module._migrate_company_parent()
        assert "parent_company_id" in _cols(db_path, "company_profiles")


class TestMigrateContactVorname:
    def test_positiv_fuegt_spalte_hinzu(self, db_path):
        _drop_columns(db_path, "contacts", "vorname")
        db_module._migrate_contact_vorname()
        assert "vorname" in _cols(db_path, "contacts")


class TestMigrateAiAssessment:
    def test_positiv_fuegt_alle_spalten_hinzu(self, db_path):
        _drop_columns(db_path, "applications", "ai_color", "ai_next_step", "ai_assessed_at", "ai_reasoning")
        db_module._migrate_ai_assessment()
        cols = _cols(db_path, "applications")
        assert {"ai_color", "ai_next_step", "ai_assessed_at", "ai_reasoning"} <= cols


class TestMigrateApplicationOrt:
    def test_positiv_fuegt_spalte_hinzu(self, db_path):
        _drop_columns(db_path, "applications", "ort")
        db_module._migrate_application_ort()
        assert "ort" in _cols(db_path, "applications")


class TestMigrateAddUserIdColumns:
    def test_positiv_fuegt_user_id_zu_allen_tabellen_hinzu(self, db_path):
        for table in db_module._USER_SCOPED_TABLES:
            _drop_columns(db_path, table, "user_id")

        db_module._migrate_add_user_id_columns()

        for table in db_module._USER_SCOPED_TABLES:
            assert "user_id" in _cols(db_path, table), f"user_id missing on {table}"

    def test_positiv_ersetzt_unique_index_auf_company_profiles(self, db_path):
        db_module._migrate_add_user_id_columns()
        assert _index_exists(db_path, "ix_company_profiles_user_id_name_norm")

    def test_corner_case_idempotent(self, db_path):
        db_module._migrate_add_user_id_columns()
        db_module._migrate_add_user_id_columns()  # must not raise


class TestMigrateUserProfile:
    def test_positiv_fuegt_alle_profilfelder_hinzu(self, db_path):
        _drop_columns(
            db_path, "users",
            "vorname", "nachname", "linkedin_url",
            "cv_filename", "cv_content_type", "cv_size_bytes", "cv_storage_path",
        )

        db_module._migrate_user_profile()

        cols = _cols(db_path, "users")
        assert {"vorname", "nachname", "linkedin_url", "cv_filename",
                "cv_content_type", "cv_size_bytes", "cv_storage_path"} <= cols


class TestMigrateCvExtractedTextCache:
    def test_positiv_fuegt_spalte_hinzu(self, db_path):
        _drop_columns(db_path, "users", "cv_extracted_text")

        db_module._migrate_cv_extracted_text_cache()

        assert "cv_extracted_text" in _cols(db_path, "users")

    def test_corner_case_idempotent_bei_zweitem_lauf(self, db_path):
        _drop_columns(db_path, "users", "cv_extracted_text")

        db_module._migrate_cv_extracted_text_cache()
        db_module._migrate_cv_extracted_text_cache()  # must not raise ("duplicate column")

        assert "cv_extracted_text" in _cols(db_path, "users")

    def test_positiv_backfillt_bestehende_uploads(self, db_path, tmp_path, monkeypatch):
        """Users who uploaded a CV before this fix existed (cv_storage_path
        already set, cv_extracted_text never populated) must get it
        backfilled on the first run after upgrading — see
        _migrate_cv_extracted_text_cache()'s docstring."""
        _drop_columns(db_path, "users", "cv_extracted_text")
        # Explicit id: _drop_columns rebuilds the table via "CREATE TABLE ...
        # AS SELECT", which drops the id column's PRIMARY KEY/autoincrement
        # behavior — an insert without an explicit id would silently store
        # NULL, and the migration's per-row UPDATE ... WHERE id = ? would
        # never match.
        _exec(
            db_path,
            "INSERT INTO users (id, email, password_hash, email_verified, cv_storage_path) "
            "VALUES (?, ?, ?, ?, ?)",
            (1, "cv-backfill@example.com", "x", 1, "1/lebenslauf.pdf"),
        )
        cv_dir = tmp_path / "user_files" / "1"
        cv_dir.mkdir(parents=True)
        (cv_dir / "lebenslauf.pdf").write_text("placeholder")  # content irrelevant, extraction is mocked below

        monkeypatch.setattr("app.cv_extract.extract_cv_text", lambda path: "Backfilled CV text")

        db_module._migrate_cv_extracted_text_cache()

        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT cv_extracted_text FROM users WHERE email = ?", ("cv-backfill@example.com",)
        ).fetchone()
        conn.close()
        assert row[0] == "Backfilled CV text"

    def test_negativ_user_ohne_cv_wird_nicht_angefasst(self, db_path):
        _drop_columns(db_path, "users", "cv_extracted_text")
        _exec(
            db_path,
            "INSERT INTO users (email, password_hash, email_verified) VALUES (?, ?, ?)",
            ("no-cv@example.com", "x", 1),
        )

        db_module._migrate_cv_extracted_text_cache()  # must not raise despite no cv_storage_path

        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT cv_extracted_text FROM users WHERE email = ?", ("no-cv@example.com",)
        ).fetchone()
        conn.close()
        assert row[0] is None


class TestMigrateLinkedinProfileCache:
    def test_positiv_fuegt_beide_spalten_hinzu(self, db_path):
        _drop_columns(db_path, "users", "linkedin_profile_text", "linkedin_profile_synced_at")

        db_module._migrate_linkedin_profile_cache()

        cols = _cols(db_path, "users")
        assert {"linkedin_profile_text", "linkedin_profile_synced_at"} <= cols

    def test_corner_case_idempotent_bei_zweitem_lauf(self, db_path):
        _drop_columns(db_path, "users", "linkedin_profile_text", "linkedin_profile_synced_at")

        db_module._migrate_linkedin_profile_cache()
        db_module._migrate_linkedin_profile_cache()  # must not raise ("duplicate column")

        cols = _cols(db_path, "users")
        assert {"linkedin_profile_text", "linkedin_profile_synced_at"} <= cols


class TestMigrateAuditLogEntityType:
    def test_positiv_fuegt_spalte_hinzu_und_backfillt(self, db_path):
        db_module._migrate_audit_log()
        db_module._migrate_audit_log_entities()
        _drop_columns(db_path, "audit_log", "entity_type")
        _exec(db_path, "INSERT INTO applications (firma, rolle, main_status) VALUES ('X', 'Y', 'applied')")
        _exec(db_path, "INSERT INTO contacts (name) VALUES ('Max')")
        _exec(db_path, "INSERT INTO audit_log (app_id, contact_id, action) VALUES (1, 1, 'create')")

        db_module._migrate_audit_log_entity_type()

        assert "entity_type" in _cols(db_path, "audit_log")
        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT entity_type FROM audit_log").fetchone()
        conn.close()
        assert row[0] == "contact"  # contact takes precedence over app in the backfill CASE

    def test_negativ_audit_log_tabelle_fehlt_wird_uebersprungen(self, db_path):
        _drop_table(db_path, "audit_log")
        db_module._migrate_audit_log_entity_type()  # must not raise


class TestClaimUnownedData:
    def test_positiv_weist_herrenlose_zeilen_dem_konto_zu(self, db_session):
        from app import models
        app = models.Application(firma="X", rolle="Y", user_id=None)
        db_session.add(app)
        db_session.commit()

        db_module.claim_unowned_data(db_session, user_id=42)

        db_session.refresh(app)
        assert app.user_id == 42

    def test_negativ_bereits_zugeordnete_zeilen_bleiben_unveraendert(self, db_session):
        from app import models
        app = models.Application(firma="X", rolle="Y", user_id=7)
        db_session.add(app)
        db_session.commit()

        db_module.claim_unowned_data(db_session, user_id=42)

        db_session.refresh(app)
        assert app.user_id == 7


class TestGetFirstUserId:
    def test_positiv_liefert_niedrigste_id(self, db_session):
        from app import models
        db_session.add(models.User(id=5, email="b@example.com", password_hash="x"))
        db_session.add(models.User(id=2, email="a@example.com", password_hash="x"))
        db_session.commit()

        assert db_module.get_first_user_id(db_session) == 2

    def test_negativ_keine_nutzer_liefert_none(self, db_session):
        assert db_module.get_first_user_id(db_session) is None


class TestBackfillEvents:
    def test_positiv_erstellt_bewerbung_event_fuer_bestehende_bewerbung(self, db_path):
        _exec(db_path, "INSERT INTO applications (firma, rolle, datum_bewerbung, main_status) VALUES ('X', 'Y', '2026-01-01', 'applied')")

        db_module._backfill_events()

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT typ, datum FROM events WHERE typ='bewerbung'").fetchone()
        conn.close()
        assert row == ("bewerbung", "2026-01-01")

    def test_positiv_bestehende_bewerbung_mit_events_wird_uebersprungen(self, db_path):
        _exec(db_path, "INSERT INTO applications (firma, rolle, main_status) VALUES ('X', 'Y', 'applied')")
        _exec(db_path, "INSERT INTO events (application_id, typ, datum) VALUES (1, 'notiz', '2026-01-01')")

        db_module._backfill_events()

        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM events WHERE application_id=1").fetchone()[0]
        conn.close()
        assert count == 1  # kein zusätzliches bewerbung-Event

    def test_negativ_events_tabelle_fehlt_wird_uebersprungen(self, db_path):
        _drop_table(db_path, "events")
        db_module._backfill_events()  # must not raise


class TestBackfillEventDatumZeitNoon:
    def test_positiv_setzt_mittag_fuer_events_ohne_datum_zeit(self, db_path):
        _exec(db_path, "INSERT INTO applications (firma, rolle, main_status) VALUES ('X', 'Y', 'applied')")
        _exec(db_path, "INSERT INTO events (application_id, typ, datum) VALUES (1, 'notiz', '2026-03-01')")

        db_module._backfill_event_datum_zeit_noon()

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT datum_zeit FROM events WHERE id=1").fetchone()
        conn.close()
        assert row[0] == "2026-03-01 12:00:00"

    def test_positiv_markiert_backfillte_zeile_als_platzhalter(self, db_path):
        _exec(db_path, "INSERT INTO applications (firma, rolle, main_status) VALUES ('X', 'Y', 'applied')")
        _exec(db_path, "INSERT INTO events (application_id, typ, datum) VALUES (1, 'notiz', '2026-03-01')")

        db_module._backfill_event_datum_zeit_noon()

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT datum_zeit_is_placeholder FROM events WHERE id=1").fetchone()
        conn.close()
        assert row[0] == 1

    def test_negativ_bereits_gesetztes_datum_zeit_bleibt_unveraendert(self, db_path):
        _exec(db_path, "INSERT INTO applications (firma, rolle, main_status) VALUES ('X', 'Y', 'applied')")
        _exec(
            db_path,
            "INSERT INTO events (application_id, typ, datum, datum_zeit) VALUES (1, 'mail', '2026-03-01', '2026-03-01 08:15:00')",
        )

        db_module._backfill_event_datum_zeit_noon()

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT datum_zeit, datum_zeit_is_placeholder FROM events WHERE id=1").fetchone()
        conn.close()
        assert row[0] == "2026-03-01 08:15:00"
        assert row[1] is None  # already had a real value -- not touched, not flagged either

    def test_negativ_events_ohne_datum_werden_uebersprungen(self, db_path):
        _exec(db_path, "INSERT INTO applications (firma, rolle, main_status) VALUES ('X', 'Y', 'applied')")
        _exec(db_path, "INSERT INTO events (application_id, typ, datum) VALUES (1, 'notiz', NULL)")

        db_module._backfill_event_datum_zeit_noon()  # must not raise

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT datum_zeit FROM events WHERE id=1").fetchone()
        conn.close()
        assert row[0] is None

    def test_corner_case_marker_verhindert_erneutes_ueberschreiben_nach_manuellem_leeren(self, db_path):
        """A user can deliberately clear an event's time via the edit form
        (v4.6.6) -- once the one-time backfill has already run, a later
        startup must NOT silently reinstate noon on that row."""
        _exec(db_path, "INSERT INTO applications (firma, rolle, main_status) VALUES ('X', 'Y', 'applied')")
        _exec(db_path, "INSERT INTO events (application_id, typ, datum) VALUES (1, 'notiz', '2026-03-01')")

        db_module._backfill_event_datum_zeit_noon()
        _exec(db_path, "UPDATE events SET datum_zeit = NULL WHERE id=1")  # user clears it by hand

        db_module._backfill_event_datum_zeit_noon()  # second app startup

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT datum_zeit FROM events WHERE id=1").fetchone()
        conn.close()
        assert row[0] is None

    def test_negativ_events_tabelle_fehlt_wird_uebersprungen(self, db_path):
        _drop_table(db_path, "events")
        db_module._backfill_event_datum_zeit_noon()  # must not raise

    def test_negativ_datum_zeit_spalte_fehlt_wird_uebersprungen(self, db_path):
        _drop_columns(db_path, "events", "datum_zeit")
        db_module._backfill_event_datum_zeit_noon()  # must not raise


class TestMigrateEventDatumZeitIsPlaceholder:
    def test_positiv_fuegt_spalte_hinzu(self, db_path):
        _drop_columns(db_path, "events", "datum_zeit_is_placeholder")
        db_module._migrate_event_datum_zeit_is_placeholder()
        assert "datum_zeit_is_placeholder" in _cols(db_path, "events")

    def test_negativ_events_tabelle_fehlt_wird_uebersprungen(self, db_path):
        _drop_table(db_path, "events")
        db_module._migrate_event_datum_zeit_is_placeholder()  # must not raise


class TestMigrateEventExternalUrl:
    def test_positiv_fuegt_spalte_hinzu(self, db_path):
        _drop_columns(db_path, "events", "external_url")
        db_module._migrate_event_external_url()
        assert "external_url" in _cols(db_path, "events")

    def test_negativ_events_tabelle_fehlt_wird_uebersprungen(self, db_path):
        _drop_table(db_path, "events")
        db_module._migrate_event_external_url()  # must not raise


class TestMigrateEventMailDirection:
    def test_positiv_fuegt_spalte_hinzu(self, db_path):
        _drop_columns(db_path, "events", "mail_direction")
        db_module._migrate_event_mail_direction()
        assert "mail_direction" in _cols(db_path, "events")

    def test_negativ_events_tabelle_fehlt_wird_uebersprungen(self, db_path):
        _drop_table(db_path, "events")
        db_module._migrate_event_mail_direction()  # must not raise

    def test_corner_case_idempotent_bei_zweitem_lauf(self, db_path):
        db_module._migrate_event_mail_direction()
        db_module._migrate_event_mail_direction()  # must not raise
        assert "mail_direction" in _cols(db_path, "events")


class TestMigrateUserHomeLocation:
    def test_positiv_fuegt_spalten_hinzu(self, db_path):
        _drop_columns(db_path, "users", "home_location", "home_lat", "home_lng")
        db_module._migrate_user_home_location()
        cols = _cols(db_path, "users")
        assert {"home_location", "home_lat", "home_lng"} <= cols

    def test_negativ_kein_fehler_wenn_db_datei_fehlt(self, tmp_path, monkeypatch):
        monkeypatch.setattr(db_module, "DATABASE_URL", f"sqlite:///{tmp_path}/does-not-exist.db")
        db_module._migrate_user_home_location()  # must not raise


class TestMigrateApplicationOrtCoords:
    def test_positiv_fuegt_spalten_hinzu(self, db_path):
        _drop_columns(db_path, "applications", "ort_lat", "ort_lng")
        db_module._migrate_application_ort_coords()
        cols = _cols(db_path, "applications")
        assert {"ort_lat", "ort_lng"} <= cols

    def test_negativ_applications_tabelle_fehlt_wird_uebersprungen(self, db_path):
        _drop_table(db_path, "applications")
        db_module._migrate_application_ort_coords()  # must not raise

    def test_negativ_kein_fehler_wenn_db_datei_fehlt(self, tmp_path, monkeypatch):
        monkeypatch.setattr(db_module, "DATABASE_URL", f"sqlite:///{tmp_path}/does-not-exist.db")
        db_module._migrate_application_ort_coords()  # must not raise


class TestMigrateApplicationDriveDistance:
    def test_positiv_fuegt_spalten_hinzu(self, db_path):
        _drop_columns(db_path, "applications", "drive_distance_km", "drive_duration_min")
        db_module._migrate_application_drive_distance()
        cols = _cols(db_path, "applications")
        assert {"drive_distance_km", "drive_duration_min"} <= cols

    def test_negativ_applications_tabelle_fehlt_wird_uebersprungen(self, db_path):
        _drop_table(db_path, "applications")
        db_module._migrate_application_drive_distance()  # must not raise

    def test_negativ_kein_fehler_wenn_db_datei_fehlt(self, tmp_path, monkeypatch):
        monkeypatch.setattr(db_module, "DATABASE_URL", f"sqlite:///{tmp_path}/does-not-exist.db")
        db_module._migrate_application_drive_distance()  # must not raise


class TestBackfillLinkedinMessageExternalUrl:
    """Populates Event.external_url for linkedin_msg events from
    LinkedInMessage.participant_profile_url -- a pure local join (no
    LinkedIn API access, unlike backfill_gcal_external_url()), so it's safe
    to run unconditionally on every startup rather than needing a manual
    endpoint."""

    def _seed_app(self, path) -> int:
        _exec(path, "INSERT INTO applications (firma, rolle, main_status) VALUES ('X', 'Y', 'applied')")
        return 1

    def test_positiv_setzt_external_url_aus_conversation_match(self, db_path):
        app_id = self._seed_app(db_path)
        _exec(
            db_path,
            "INSERT INTO events (application_id, typ, source, external_id) VALUES (?, 'mail', 'linkedin_msg', 'conv-1')",
            (app_id,),
        )
        _exec(
            db_path,
            "INSERT INTO linkedin_messages (conversation_id, participant_name, participant_name_normalized, participant_profile_url) "
            "VALUES ('conv-1', 'Max Mustermann', 'maxmustermann', 'https://www.linkedin.com/in/maxmustermann')",
        )

        db_module._backfill_linkedin_message_external_url()

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT external_url FROM events WHERE external_id='conv-1'").fetchone()
        conn.close()
        assert row[0] == "https://www.linkedin.com/in/maxmustermann"

    def test_negativ_bereits_gesetztes_external_url_bleibt_unveraendert(self, db_path):
        app_id = self._seed_app(db_path)
        _exec(
            db_path,
            "INSERT INTO events (application_id, typ, source, external_id, external_url) "
            "VALUES (?, 'mail', 'linkedin_msg', 'conv-2', 'https://old-link')",
            (app_id,),
        )
        _exec(
            db_path,
            "INSERT INTO linkedin_messages (conversation_id, participant_name, participant_name_normalized, participant_profile_url) "
            "VALUES ('conv-2', 'Someone', 'someone', 'https://www.linkedin.com/in/someone')",
        )

        db_module._backfill_linkedin_message_external_url()

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT external_url FROM events WHERE external_id='conv-2'").fetchone()
        conn.close()
        assert row[0] == "https://old-link"

    def test_negativ_kein_match_bleibt_null(self, db_path):
        app_id = self._seed_app(db_path)
        _exec(
            db_path,
            "INSERT INTO events (application_id, typ, source, external_id) VALUES (?, 'mail', 'linkedin_msg', 'conv-orphan')",
            (app_id,),
        )

        db_module._backfill_linkedin_message_external_url()

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT external_url FROM events WHERE external_id='conv-orphan'").fetchone()
        conn.close()
        assert row[0] is None

    def test_negativ_andere_source_wird_nicht_angefasst(self, db_path):
        app_id = self._seed_app(db_path)
        _exec(
            db_path,
            "INSERT INTO events (application_id, typ, source, external_id) VALUES (?, 'mail', 'gmail', 'conv-3')",
            (app_id,),
        )
        _exec(
            db_path,
            "INSERT INTO linkedin_messages (conversation_id, participant_name, participant_name_normalized, participant_profile_url) "
            "VALUES ('conv-3', 'Irrelevant', 'irrelevant', 'https://www.linkedin.com/in/irrelevant')",
        )

        db_module._backfill_linkedin_message_external_url()

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT external_url FROM events WHERE external_id='conv-3'").fetchone()
        conn.close()
        assert row[0] is None

    def test_negativ_linkedin_messages_tabelle_fehlt_wird_uebersprungen(self, db_path):
        _drop_table(db_path, "linkedin_messages")
        db_module._backfill_linkedin_message_external_url()  # must not raise

    def test_negativ_events_tabelle_fehlt_wird_uebersprungen(self, db_path):
        _drop_table(db_path, "events")
        db_module._backfill_linkedin_message_external_url()  # must not raise


class TestFlagNoonBackfillPlaceholders:
    """created_at < the hardcoded v4.6.5 cutoff is the whole discriminator --
    the datum_zeit column (and any code able to write a real value into it)
    didn't exist before that deploy, so any such row's datum_zeit can only
    have come from the noon backfill."""

    _BEFORE_CUTOFF = "2026-07-19 06:00:00"
    _AFTER_CUTOFF = "2026-07-19 08:00:00"

    def test_positiv_markiert_alte_zeilen_vor_dem_cutoff(self, db_path):
        _exec(db_path, "INSERT INTO applications (firma, rolle, main_status) VALUES ('X', 'Y', 'applied')")
        _exec(
            db_path,
            "INSERT INTO events (application_id, typ, datum, datum_zeit, created_at) "
            "VALUES (1, 'notiz', '2026-03-01', '2026-03-01 12:00:00', ?)",
            (self._BEFORE_CUTOFF,),
        )

        db_module._flag_noon_backfill_placeholders()

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT datum_zeit_is_placeholder FROM events WHERE id=1").fetchone()
        conn.close()
        assert row[0] == 1

    def test_negativ_zeilen_nach_dem_cutoff_bleiben_unmarkiert(self, db_path):
        """An event created after the datum_zeit feature existed either got a
        real timestamp at sync time or was left NULL on purpose -- neither
        case is a noon-backfill placeholder, regardless of what datum_zeit
        happens to contain."""
        _exec(db_path, "INSERT INTO applications (firma, rolle, main_status) VALUES ('X', 'Y', 'applied')")
        _exec(
            db_path,
            "INSERT INTO events (application_id, typ, datum, datum_zeit, created_at) "
            "VALUES (1, 'mail', '2026-07-19', '2026-07-19 09:30:00', ?)",
            (self._AFTER_CUTOFF,),
        )

        db_module._flag_noon_backfill_placeholders()

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT datum_zeit_is_placeholder FROM events WHERE id=1").fetchone()
        conn.close()
        assert row[0] is None

    def test_negativ_zeilen_ohne_datum_zeit_bleiben_unmarkiert(self, db_path):
        _exec(db_path, "INSERT INTO applications (firma, rolle, main_status) VALUES ('X', 'Y', 'applied')")
        _exec(
            db_path,
            "INSERT INTO events (application_id, typ, datum, created_at) VALUES (1, 'notiz', NULL, ?)",
            (self._BEFORE_CUTOFF,),
        )

        db_module._flag_noon_backfill_placeholders()

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT datum_zeit_is_placeholder FROM events WHERE id=1").fetchone()
        conn.close()
        assert row[0] is None

    def test_corner_case_marker_verhindert_erneutes_markieren_nach_manuellem_setzen(self, db_path):
        """A user can give an old event a real time by hand via the edit form
        (v4.6.6), which clears the flag (see update_event() in
        applications.py) -- a later startup must not silently re-flag it,
        since created_at never changes and would otherwise match forever."""
        _exec(db_path, "INSERT INTO applications (firma, rolle, main_status) VALUES ('X', 'Y', 'applied')")
        _exec(
            db_path,
            "INSERT INTO events (application_id, typ, datum, datum_zeit, created_at) "
            "VALUES (1, 'notiz', '2026-03-01', '2026-03-01 12:00:00', ?)",
            (self._BEFORE_CUTOFF,),
        )

        db_module._flag_noon_backfill_placeholders()
        _exec(db_path, "UPDATE events SET datum_zeit_is_placeholder = NULL WHERE id=1")  # user set a real time

        db_module._flag_noon_backfill_placeholders()  # second app startup

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT datum_zeit_is_placeholder FROM events WHERE id=1").fetchone()
        conn.close()
        assert row[0] is None

    def test_negativ_events_tabelle_fehlt_wird_uebersprungen(self, db_path):
        _drop_table(db_path, "events")
        db_module._flag_noon_backfill_placeholders()  # must not raise

    def test_negativ_spalte_fehlt_wird_uebersprungen(self, db_path):
        _drop_columns(db_path, "events", "datum_zeit_is_placeholder")
        db_module._flag_noon_backfill_placeholders()  # must not raise


class TestInitDb:
    def test_positiv_kompletter_lauf_gegen_leere_db_wirft_nicht(self, tmp_path, monkeypatch):
        # Realistischster Fresh-Install-Fall: DB-Datei existiert noch gar
        # nicht — alle _migrate_*()-Guards greifen, Base.metadata.create_all()
        # baut das komplette aktuelle Schema von Grund auf.
        path = str(tmp_path / "fresh.db")
        monkeypatch.setattr(db_module, "DATABASE_URL", f"sqlite:///{path}")
        eng = create_engine(f"sqlite:///{path}")
        monkeypatch.setattr(db_module, "engine", eng)

        db_module.init_db()

        assert _table_exists(path, "applications")
        assert "main_status" in _cols(path, "applications")
        eng.dispose()

    def test_positiv_zweiter_lauf_gegen_bereits_migrierte_db_wirft_nicht(self, db_path, monkeypatch):
        eng = create_engine(f"sqlite:///{db_path}")
        monkeypatch.setattr(db_module, "engine", eng)

        db_module.init_db()  # must not raise on an already-fully-migrated schema

        eng.dispose()
