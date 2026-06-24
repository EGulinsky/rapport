from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
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

    # Migrate rows that still have old status and no main_status yet
    for old_val, (main, sub) in OLD_STATUS_MIGRATION.items():
        cur.execute(
            "UPDATE applications SET main_status=?, sub_status=? "
            "WHERE status=? AND (main_status IS NULL OR main_status='applied')",
            (main, sub, old_val),
        )

    # Drop legacy columns replaced by computed properties
    cur.execute("PRAGMA table_info(applications)")
    app_cols = {row[1] for row in cur.fetchall()}
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
    """Add pre_rejection_status column to applications if missing."""
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
    conn.close()


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
    Base.metadata.create_all(bind=engine)
    _backfill_events()
    _migrate_gespraeche_to_events()
