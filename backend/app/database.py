from sqlalchemy import create_engine
from sqlalchemy import event as _event_module
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import Session as _OrmSession
from sqlalchemy.orm import with_loader_criteria as _with_loader_criteria
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/jobtracker.db")

connect_args = {"check_same_thread": False, "timeout": 30} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)

if DATABASE_URL.startswith("sqlite"):
    from sqlalchemy import event as _sa_event

    @_sa_event.listens_for(engine, "connect")
    def _set_sqlite_wal(dbapi_conn, _):
        # WAL journal mode: readers never block writers and vice-versa,
        # eliminating the write-lock contention that causes 502s during background syncs.
        dbapi_conn.execute("PRAGMA journal_mode=WAL")
        dbapi_conn.execute("PRAGMA busy_timeout=60000")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Mandantentrennung: zentraler Query-Filter ──────────────────────────────
#
# Statt jede einzelne Query in ~20 Router-Dateien manuell um ein
# `.filter_by(user_id=...)` zu ergänzen (fehleranfällig — eine vergessene
# Stelle wäre ein echtes Datenleck zwischen Konten), wird die aktive Konto-ID
# einmal pro Request an der DB-Session hinterlegt (siehe set_session_user()).
# Ein SQLAlchemy-Session-Event wendet daraufhin automatisch einen Filter auf
# JEDE SELECT-Query gegen ein mandantengebundenes Modell an — inklusive
# Relationship-Lazy-Loads und Subqueries, solange sie über die ORM-Query-API
# laufen (rohes db.execute(text(...)) umgeht das, ebenso wie Session.get()/
# db.query(X).get(id) — siehe SQLAlchemy-Doku zu with_loader_criteria. Für
# Primary-Key-Lookups auf Anfrage-Pfaden ist daher zusätzlich eine explizite
# Eigentums-Prüfung nach dem Laden nötig.
_SCOPED_MODEL_NAMES = [
    "CompanyProfile", "Application", "Contact", "MergeAlias", "Event", "Attachment",
    "GoogleSync", "SyncedItem", "PendingMatch", "ICloudSync", "CallsConfig", "LinkedInSync",
    "AiSettings", "MapsSettings", "AgentSettings", "SyncSettings", "AuditLog",
    "FilesConfig", "BackupConfig", "LogoSettings",
]


def set_session_user(db, user_id) -> None:
    """Aktiviert den automatischen Mandanten-Filter für diese Session. Wird
    pro HTTP-Request von get_current_user() aufgerufen, und von den
    Hintergrund-Sync-Jobs für das ausführende Konto (siehe main.py)."""
    db.info["current_user_id"] = user_id


@_event_module.listens_for(_OrmSession, "do_orm_execute")
def _apply_tenant_filter(execute_state):
    if not execute_state.is_select:
        return
    user_id = execute_state.session.info.get("current_user_id")
    if user_id is None:
        return
    # Lazy-Import: verhindert einen zirkulären Import beim Laden von
    # database.py selbst (models.py importiert Base von hier). Zum Zeitpunkt,
    # an dem tatsächlich eine Query läuft, ist app.models garantiert bereits
    # importiert — Modell-Instanzen können sonst gar nicht existieren.
    from app import models as _models

    for name in _SCOPED_MODEL_NAMES:
        cls = getattr(_models, name)
        execute_state.statement = execute_state.statement.options(
            _with_loader_criteria(cls, cls.user_id == user_id, include_aliases=True)
        )


def _migrate_status_fields():
    """Add main_status/sub_status columns and migrate from old flat status values."""
    import sqlite3
    from app.models import OLD_STATUS_MIGRATION

    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
    if not os.path.exists(db_path):
        return  # fresh DB, create_all handles everything

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(applications)")
    existing_cols = {row[1] for row in cur.fetchall()}

    if "main_status" not in existing_cols:
        cur.execute("ALTER TABLE applications ADD COLUMN main_status TEXT NOT NULL DEFAULT 'applied'")
    if "sub_status" not in existing_cols:
        cur.execute("ALTER TABLE applications ADD COLUMN sub_status TEXT")

    # Migrate rows that still have old status and no main_status yet.
    # Guard: skip entirely if status column was already dropped.
    if "status" in existing_cols:
        for old_val, (main, sub) in OLD_STATUS_MIGRATION.items():
            cur.execute(
                "UPDATE applications SET main_status=?, sub_status=? "
                "WHERE status=? AND main_status IS NULL",
                (main, sub, old_val),
            )

    # Drop legacy columns replaced by computed properties
    cur.execute("PRAGMA table_info(applications)")
    app_cols = {row[1] for row in cur.fetchall()}
    if "status" in app_cols:
        cur.execute("ALTER TABLE applications DROP COLUMN status")
    if "abgesagt" in app_cols:
        cur.execute("ALTER TABLE applications DROP COLUMN abgesagt")
    if "ghosting" in app_cols:
        cur.execute("ALTER TABLE applications DROP COLUMN ghosting")
    if "stellenanzeige_url" not in app_cols:
        cur.execute("ALTER TABLE applications ADD COLUMN stellenanzeige_url TEXT")

    # Add source column to events if missing
    cur.execute("PRAGMA table_info(events)")
    event_cols = {row[1] for row in cur.fetchall()}
    if "source" not in event_cols:
        cur.execute("ALTER TABLE events ADD COLUMN source TEXT")

    # Add raw_content / status_only to pending_matches if missing
    cur.execute("PRAGMA table_info(pending_matches)")
    pm_cols = {row[1] for row in cur.fetchall()}
    if "raw_content" not in pm_cols:
        cur.execute("ALTER TABLE pending_matches ADD COLUMN raw_content TEXT")
    if "status_only" not in pm_cols:
        cur.execute("ALTER TABLE pending_matches ADD COLUMN status_only INTEGER NOT NULL DEFAULT 0")

    # Add autor to events if missing
    cur.execute("PRAGMA table_info(events)")
    ev_cols = {row[1] for row in cur.fetchall()}
    if "autor" not in ev_cols:
        cur.execute("ALTER TABLE events ADD COLUMN autor TEXT")

    conn.commit()
    conn.close()


def _backfill_events():
    """Create initial timeline events for applications that have none yet."""
    import sqlite3
    from datetime import date as _date

    MAIN_LABELS = {
        "prospecting": "Anbahnung", "applied": "Beworben",
        "hr": "Gespräch HR/HH", "fb": "Gespräch FB",
        "waiting": "Warten auf Entscheidung", "negotiating": "Angebotsverhandlung",
        "signed": "Unterschrift", "rejected": "Absage",
    }
    SUB_LABELS = {
        "1_scheduled": "1. Gespräch terminiert", "1_done": "1. Gespräch geführt",
        "2_scheduled": "2. Gespräch terminiert", "2_done": "2. Gespräch geführt",
        "3_scheduled": "3. Gespräch terminiert", "3_done": "3. Gespräch geführt",
    }

    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='events'")
    if not cur.fetchone():
        conn.close()
        return

    cur.execute("""
        SELECT a.id, a.kommentar, a.datum_bewerbung, a.letztes_update, a.main_status, a.sub_status
        FROM applications a
        WHERE NOT EXISTS (SELECT 1 FROM events e WHERE e.application_id = a.id)
    """)
    apps = cur.fetchall()
    today = _date.today().isoformat()

    for app_id, kommentar, datum_bew, letztes, main_status, sub_status in apps:
        ref_date = datum_bew or letztes or today
        late_date = letztes or datum_bew or today

        cur.execute(
            "INSERT INTO events (application_id, typ, datum, titel) VALUES (?,?,?,?)",
            (app_id, "bewerbung", ref_date, "Bewerbung eingereicht"),
        )

        if main_status and main_status not in ("applied", "prospecting"):
            label = MAIN_LABELS.get(main_status, main_status)
            if sub_status:
                label += f" – {SUB_LABELS.get(sub_status, sub_status)}"
            cur.execute(
                "INSERT INTO events (application_id, typ, datum, titel) VALUES (?,?,?,?)",
                (app_id, "status", late_date, label),
            )

        if kommentar and kommentar.strip():
            cur.execute(
                "INSERT INTO events (application_id, typ, datum, notiz) VALUES (?,?,?,?)",
                (app_id, "notiz", late_date, kommentar.strip()),
            )

    conn.commit()
    conn.close()


def _migrate_icloud():
    """Add icloud_email column to icloud_sync table if missing."""
    import sqlite3

    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='icloud_sync'")
    if not cur.fetchone():
        conn.close()
        return

    cur.execute("PRAGMA table_info(icloud_sync)")
    cols = {row[1] for row in cur.fetchall()}
    if "icloud_email" not in cols:
        cur.execute("ALTER TABLE icloud_sync ADD COLUMN icloud_email TEXT")
    if "web_password_enc" not in cols:
        cur.execute("ALTER TABLE icloud_sync ADD COLUMN web_password_enc TEXT")

    conn.commit()
    conn.close()


def _fix_mail_event_dates():
    """One-time fix: mail events where datum > created_at got the future meeting date
    extracted from the email body instead of the email received date. Reset to created_at date."""
    import sqlite3

    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='events'")
    if not cur.fetchone():
        conn.close()
        return

    cur.execute("""
        UPDATE events
        SET datum = DATE(created_at)
        WHERE source IN ('gmail', 'icloud_mail')
          AND datum IS NOT NULL
          AND created_at IS NOT NULL
          AND datum > DATE(created_at)
    """)
    fixed = cur.rowcount
    if fixed:
        print(f"[migration] Fixed {fixed} mail event(s) with future datum → email received date")

    conn.commit()
    conn.close()


def _migrate_contacts_m2m():
    """Create contact_application join table and backfill from contacts.application_id."""
    import sqlite3

    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='contacts'")
    if not cur.fetchone():
        conn.close()
        return

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='contact_application'")
    join_exists = cur.fetchone()

    if not join_exists:
        cur.execute("""
            CREATE TABLE contact_application (
                contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
                application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
                PRIMARY KEY (contact_id, application_id)
            )
        """)
        # Backfill from existing application_id FK column
        cur.execute("PRAGMA table_info(contacts)")
        contact_cols = {row[1] for row in cur.fetchall()}
        if "application_id" in contact_cols:
            cur.execute("""
                INSERT INTO contact_application (contact_id, application_id)
                SELECT id, application_id FROM contacts
                WHERE application_id IS NOT NULL
            """)

    conn.commit()
    conn.close()


def _migrate_calls():
    """Add calls_last_sync column to icloud_sync table if missing."""
    import sqlite3

    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='icloud_sync'")
    if not cur.fetchone():
        conn.close()
        return
    cur.execute("PRAGMA table_info(icloud_sync)")
    cols = {row[1] for row in cur.fetchall()}
    if "calls_last_sync" not in cols:
        cur.execute("ALTER TABLE icloud_sync ADD COLUMN calls_last_sync TIMESTAMP")
    conn.commit()
    conn.close()


def _migrate_gespraeche_to_events():
    """One-time: convert gespraech_1..5 date fields into gespräch timeline events."""
    import sqlite3

    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='events'")
    if not cur.fetchone():
        conn.close()
        return

    cur.execute("""
        SELECT id, gespraech_1, gespraech_2, gespraech_3, gespraech_4, gespraech_5
        FROM applications
        WHERE gespraech_1 IS NOT NULL
           OR gespraech_2 IS NOT NULL
           OR gespraech_3 IS NOT NULL
           OR gespraech_4 IS NOT NULL
           OR gespraech_5 IS NOT NULL
    """)
    apps = cur.fetchall()
    created = 0

    for row in apps:
        app_id = row[0]
        for n, raw_val in enumerate(row[1:], start=1):
            if not raw_val or raw_val.strip() in ("-", ""):
                continue
            # Parse datetime string "YYYY-MM-DD HH:MM:SS" → date
            try:
                datum = raw_val.strip()[:10]  # "YYYY-MM-DD"
                # Validate
                from datetime import date as _date
                _date.fromisoformat(datum)
            except Exception:
                continue

            # Skip if a gespräch event with this date already exists for this app
            exists = cur.execute(
                "SELECT 1 FROM events WHERE application_id=? AND typ='gespräch' AND datum=?",
                (app_id, datum),
            ).fetchone()
            if exists:
                continue

            cur.execute(
                "INSERT INTO events (application_id, typ, datum, titel) VALUES (?,?,?,?)",
                (app_id, "gespräch", datum, f"Gespräch {n}"),
            )
            created += 1

    if created:
        print(f"[migration] Migrated {created} Gespräch date(s) to timeline events")
    conn.commit()
    conn.close()


def _migrate_sync_settings_files():
    """Add files_enabled column to sync_settings table if missing."""
    import sqlite3

    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sync_settings'")
    if not cur.fetchone():
        conn.close()
        return
    cur.execute("PRAGMA table_info(sync_settings)")
    cols = {row[1] for row in cur.fetchall()}
    if "files_enabled" not in cols:
        cur.execute("ALTER TABLE sync_settings ADD COLUMN files_enabled INTEGER NOT NULL DEFAULT 1")
    conn.commit()
    conn.close()


def _migrate_google_email():
    """Add gmail_email column to google_sync table if missing."""
    import sqlite3

    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='google_sync'")
    if not cur.fetchone():
        conn.close()
        return
    cur.execute("PRAGMA table_info(google_sync)")
    cols = {row[1] for row in cur.fetchall()}
    if "gmail_email" not in cols:
        cur.execute("ALTER TABLE google_sync ADD COLUMN gmail_email TEXT")
    conn.commit()
    conn.close()


def _migrate_attachments():
    """Create attachments table if missing."""
    import sqlite3

    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='attachments'")
    if not cur.fetchone():
        cur.execute("""
            CREATE TABLE attachments (
                id INTEGER PRIMARY KEY,
                event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                filename TEXT NOT NULL,
                content_type TEXT,
                size_bytes INTEGER,
                storage_path TEXT NOT NULL,
                source TEXT,
                external_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("CREATE INDEX ix_attachments_event_id ON attachments (event_id)")
    conn.commit()
    conn.close()

    # Ensure /data/attachments directory exists
    attachments_dir = os.path.join(os.path.dirname(db_path), "attachments")
    os.makedirs(attachments_dir, exist_ok=True)


def _migrate_event_external_id():
    """Add external_id column to events if missing."""
    import sqlite3

    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(events)")
    cols = {row[1] for row in cur.fetchall()}
    if "external_id" not in cols:
        cur.execute("ALTER TABLE events ADD COLUMN external_id TEXT")
    conn.commit()
    conn.close()


def _migrate_linkedin_job_id():
    """Add linkedin_job_id column to applications if missing."""
    import sqlite3

    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(applications)")
    cols = {row[1] for row in cur.fetchall()}
    if "linkedin_job_id" not in cols:
        cur.execute("ALTER TABLE applications ADD COLUMN linkedin_job_id TEXT")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_applications_linkedin_job_id ON applications (linkedin_job_id)")
    conn.commit()
    conn.close()


def _migrate_pre_rejection_status():
    """Add pre_rejection_status column and backfill it from status events."""
    import sqlite3

    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(applications)")
    cols = {row[1] for row in cur.fetchall()}
    if "pre_rejection_status" not in cols:
        cur.execute("ALTER TABLE applications ADD COLUMN pre_rejection_status TEXT")
        conn.commit()

    # Backfill for existing rejected apps: derive from event history via bulk SQL UPDATEs.
    # Priority (highest wins): negotiating > waiting > fb > hr > NULL (→ "applied" fallback)

    # Any gespräch-type event → at least HR stage
    cur.execute("""
        UPDATE applications SET pre_rejection_status = 'hr'
        WHERE main_status = 'rejected'
          AND (pre_rejection_status IS NULL OR pre_rejection_status = '')
          AND id IN (SELECT DISTINCT application_id FROM events WHERE typ = 'gespräch')
    """)

    # Canonical status labels — overwrite with higher stage if found
    for label_prefix, status in [
        ("Gespräch FB", "fb"),
        ("Warten auf Entscheidung", "waiting"),
        ("Angebotsverhandlung", "negotiating"),
    ]:
        cur.execute("""
            UPDATE applications SET pre_rejection_status = ?
            WHERE main_status = 'rejected'
              AND id IN (
                SELECT DISTINCT application_id FROM events
                WHERE typ = 'status' AND titel LIKE ?
              )
        """, (status, f"{label_prefix}%"))

    conn.commit()
    conn.close()


def _migrate_audit_log():
    """Add audit_log table and audit_log_level column to sync_settings."""
    import sqlite3

    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(sync_settings)")
    sync_cols = {row[1] for row in cur.fetchall()}
    if "audit_log_level" not in sync_cols:
        cur.execute("ALTER TABLE sync_settings ADD COLUMN audit_log_level TEXT NOT NULL DEFAULT 'normal'")

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'")
    if not cur.fetchone():
        cur.execute("""
            CREATE TABLE audit_log (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                app_id    INTEGER REFERENCES applications(id) ON DELETE SET NULL,
                timestamp DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                action    TEXT NOT NULL,
                field     TEXT,
                old_value TEXT,
                new_value TEXT,
                source    TEXT NOT NULL DEFAULT 'user',
                reason    TEXT
            )
        """)
        cur.execute("CREATE INDEX ix_audit_log_app_id ON audit_log (app_id)")
        cur.execute("CREATE INDEX ix_audit_log_timestamp ON audit_log (timestamp)")

    # DB-level trigger: catches every main_status change regardless of Python code path.
    # Uses source='db_trigger' so it's distinguishable from Python-written entries.
    # Skips if Python already logged the same change within 2 seconds (avoids duplicates).
    cur.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_main_status_change
        AFTER UPDATE OF main_status ON applications
        FOR EACH ROW
        WHEN OLD.main_status IS NOT NEW.main_status
          AND NOT EXISTS (
            SELECT 1 FROM audit_log
            WHERE app_id    = NEW.id
              AND action    = 'status_change'
              AND old_value = OLD.main_status
              AND new_value = NEW.main_status
              AND (julianday(strftime('%Y-%m-%dT%H:%M:%fZ','now')) - julianday(timestamp)) * 86400 < 2
          )
        BEGIN
          INSERT INTO audit_log (action, field, old_value, new_value, app_id, source, reason)
          VALUES (
            'status_change', 'main_status', OLD.main_status, NEW.main_status,
            NEW.id, 'db_trigger', 'Nicht via Python-Audit-Pfad erfasst'
          );
        END
    """)

    conn.commit()
    conn.close()


def _migrate_audit_log_entities():
    """Add contact_id / company_profile_id / event_id columns to audit_log —
    bislang konnte Audit-Log nur Bewerbungen referenzieren (app_id)."""
    import sqlite3

    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'")
    if not cur.fetchone():
        conn.close()
        return

    cur.execute("PRAGMA table_info(audit_log)")
    cols = {row[1] for row in cur.fetchall()}
    for col, ref in (
        ("contact_id", "contacts(id)"),
        ("company_profile_id", "company_profiles(id)"),
        ("event_id", "events(id)"),
    ):
        if col not in cols:
            cur.execute(f"ALTER TABLE audit_log ADD COLUMN {col} INTEGER REFERENCES {ref}")
            cur.execute(f"CREATE INDEX ix_audit_log_{col} ON audit_log ({col})")

    conn.commit()
    conn.close()


def _migrate_company_profiles():
    """Add company_profile_id / target_company_profile_id FKs to applications."""
    import sqlite3
    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
    if not os.path.exists(db_path):
        return
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(applications)")
    cols = {row[1] for row in cur.fetchall()}
    if "company_profile_id" not in cols:
        cur.execute("ALTER TABLE applications ADD COLUMN company_profile_id INTEGER REFERENCES company_profiles(id)")
    if "target_company_profile_id" not in cols:
        cur.execute("ALTER TABLE applications ADD COLUMN target_company_profile_id INTEGER REFERENCES company_profiles(id)")
    conn.commit()
    conn.close()


def _backfill_company_profiles():
    """Create pending CompanyProfile entries for all existing applications that lack one."""
    import sqlite3
    from app.dedup import norm_firma
    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
    if not os.path.exists(db_path):
        return
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Check table exists (create_all must have run first)
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='company_profiles'")
    if not cur.fetchone():
        conn.close()
        return

    cur.execute("SELECT id, firma, is_headhunter, zielfirma_bei_hh, company_profile_id, target_company_profile_id FROM applications")
    apps = cur.fetchall()

    def _get_or_create_profile(name: str) -> int:
        nname = norm_firma(name)
        cur.execute("SELECT id FROM company_profiles WHERE name_norm=?", (nname,))
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute(
            "INSERT INTO company_profiles (name_norm, name_display, sync_status, created_at) VALUES (?,?,'pending',datetime('now'))",
            (nname, name),
        )
        return cur.lastrowid

    changed = 0
    for app in apps:
        updates = {}
        if not app["company_profile_id"] and app["firma"]:
            updates["company_profile_id"] = _get_or_create_profile(app["firma"])
        if not app["target_company_profile_id"] and app["is_headhunter"] and app["zielfirma_bei_hh"]:
            updates["target_company_profile_id"] = _get_or_create_profile(app["zielfirma_bei_hh"])
        if updates:
            set_clause = ", ".join(f"{k}=?" for k in updates)
            cur.execute(f"UPDATE applications SET {set_clause} WHERE id=?", (*updates.values(), app["id"]))
            changed += 1

    conn.commit()
    conn.close()


def _migrate_contact_company_profile():
    import sqlite3
    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
    if not os.path.exists(db_path):
        return
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(contacts)")
    cols = {row[1] for row in cur.fetchall()}
    if "company_profile_id" not in cols:
        cur.execute("ALTER TABLE contacts ADD COLUMN company_profile_id INTEGER REFERENCES company_profiles(id)")
    conn.commit()
    conn.close()


def _migrate_company_logo():
    import sqlite3
    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
    if not os.path.exists(db_path):
        return
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(company_profiles)")
    cols = {row[1] for row in cur.fetchall()}
    if "logo_data" not in cols:
        cur.execute("ALTER TABLE company_profiles ADD COLUMN logo_data TEXT")
    conn.commit()
    conn.close()


def _migrate_company_parent():
    import sqlite3
    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
    if not os.path.exists(db_path):
        return
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(company_profiles)")
    cols = {row[1] for row in cur.fetchall()}
    if "parent_company_id" not in cols:
        cur.execute("ALTER TABLE company_profiles ADD COLUMN parent_company_id INTEGER REFERENCES company_profiles(id)")
    conn.commit()
    conn.close()


def _migrate_contact_vorname():
    import sqlite3
    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
    if not os.path.exists(db_path):
        return
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(contacts)")
    cols = {row[1] for row in cur.fetchall()}
    if "vorname" not in cols:
        cur.execute("ALTER TABLE contacts ADD COLUMN vorname VARCHAR")
    conn.commit()
    conn.close()


def _migrate_ai_assessment():
    import sqlite3
    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
    if not os.path.exists(db_path):
        return
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(applications)")
    cols = {row[1] for row in cur.fetchall()}
    if "ai_color" not in cols:
        cur.execute("ALTER TABLE applications ADD COLUMN ai_color TEXT")
    if "ai_next_step" not in cols:
        cur.execute("ALTER TABLE applications ADD COLUMN ai_next_step TEXT")
    if "ai_assessed_at" not in cols:
        cur.execute("ALTER TABLE applications ADD COLUMN ai_assessed_at TIMESTAMP")
    if "ai_reasoning" not in cols:
        cur.execute("ALTER TABLE applications ADD COLUMN ai_reasoning TEXT")
    conn.commit()
    conn.close()


def _migrate_application_ort():
    import sqlite3
    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
    if not os.path.exists(db_path):
        return
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(applications)")
    cols = {row[1] for row in cur.fetchall()}
    if "ort" not in cols:
        cur.execute("ALTER TABLE applications ADD COLUMN ort TEXT")
    conn.commit()
    conn.close()


_USER_SCOPED_TABLES = [
    "company_profiles", "applications", "contacts", "merge_aliases", "events",
    "attachments", "google_sync", "synced_items", "pending_matches", "icloud_sync",
    "calls_config", "linkedin_sync", "ai_settings", "maps_settings", "agent_settings",
    "sync_settings", "audit_log", "files_config", "backup_config", "logo_settings",
]


def _migrate_add_user_id_columns():
    """Benutzerkonten-Feature (Mandantentrennung): fügt jeder bisher globalen
    Tabelle eine user_id-Spalte hinzu (zunächst NULL für bereits vorhandene
    Zeilen — siehe Claim-on-first-verify in app/routers/auth.py) und ersetzt
    den globalen Unique-Index auf CompanyProfile.name_norm durch einen
    zusammengesetzten (user_id, name_norm)-Index. Muss nach create_all()
    laufen, da die users-Tabelle als FK-Ziel existieren muss."""
    import sqlite3
    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    for table in _USER_SCOPED_TABLES:
        cur.execute(f"PRAGMA table_info({table})")
        cols = {row[1] for row in cur.fetchall()}
        if "user_id" not in cols:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER REFERENCES users(id)")

    cur.execute("DROP INDEX IF EXISTS ix_company_profiles_name_norm")
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_company_profiles_user_id_name_norm "
        "ON company_profiles (user_id, name_norm)"
    )

    conn.commit()
    conn.close()


def claim_unowned_data(db, user_id: int) -> None:
    """Weist einem Konto alle Zeilen zu, die noch keinem Nutzer gehören
    (user_id IS NULL) — der einmalige Übergang von der bisherigen Ein-
    Personen-Installation zu echten Benutzerkonten. Wird ausschließlich für
    das allererste bestätigte Konto aufgerufen (siehe verify_email() in
    app/routers/auth.py)."""
    from sqlalchemy import text

    for table in _USER_SCOPED_TABLES:
        db.execute(
            text(f"UPDATE {table} SET user_id = :uid WHERE user_id IS NULL"),
            {"uid": user_id},
        )
    db.commit()


def get_first_user_id(db) -> int | None:
    """Liefert die ID des am längsten bestehenden Kontos (niedrigste ID), oder
    None wenn noch niemand registriert ist. Genutzt vom Hintergrund-Sync-Loop
    (siehe main.py) und ähnlichen Background-Jobs ohne HTTP-Request-Kontext —
    diese laufen bewusst nur für das erste/einzige Konto (siehe Projektentscheidung
    zur pragmatischen Mehrkonten-Behandlung von Hintergrundjobs)."""
    from app import models

    row = db.query(models.User.id).order_by(models.User.id).first()
    return row[0] if row else None


def init_db():
    from app import models  # noqa: F401
    _migrate_status_fields()
    _migrate_icloud()
    _migrate_calls()
    _migrate_google_email()
    _migrate_sync_settings_files()
    _fix_mail_event_dates()
    _migrate_contacts_m2m()
    _migrate_attachments()
    _migrate_event_external_id()
    _migrate_linkedin_job_id()
    _migrate_pre_rejection_status()
    _migrate_audit_log()
    _migrate_audit_log_entities()
    _migrate_contact_company_profile()
    _migrate_contact_vorname()
    _migrate_company_logo()
    _migrate_company_parent()
    _migrate_ai_assessment()
    _migrate_application_ort()
    Base.metadata.create_all(bind=engine)
    _migrate_add_user_id_columns()
    _migrate_company_profiles()
    _backfill_company_profiles()
    _backfill_events()
    _migrate_gespraeche_to_events()
