from sqlalchemy import Column, Integer, String, Date, Boolean, Text, DateTime, ForeignKey, Table
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum

# Many-to-many join table: one contact can be linked to multiple applications
contact_application = Table(
    "contact_application",
    Base.metadata,
    Column("contact_id", Integer, ForeignKey("contacts.id", ondelete="CASCADE"), primary_key=True),
    Column("application_id", Integer, ForeignKey("applications.id", ondelete="CASCADE"), primary_key=True),
)


class MainStatus(str, enum.Enum):
    prospecting  = "prospecting"   # 00 Anbahnung
    applied      = "applied"       # 01 Beworben
    hr           = "hr"            # 02 Gespräch HR/HH
    fb           = "fb"            # 03 Gespräch FB
    waiting      = "waiting"       # 04 Warten auf Entscheidung
    negotiating  = "negotiating"   # 05 Angebotsverhandlung
    signed       = "signed"        # 06 Unterschrift
    rejected     = "rejected"      # 07 Absage


MAIN_STATUS_LABELS: dict[str, str] = {
    "prospecting":  "Anbahnung",
    "applied":      "Beworben",
    "hr":           "Gespräch HR/HH",
    "fb":           "Gespräch FB",
    "waiting":      "Warten auf Entscheidung",
    "negotiating":  "Angebotsverhandlung",
    "signed":       "Unterschrift",
    "rejected":     "Absage",
}

SUB_STATUS_LABELS: dict[str, str] = {
    "1_scheduled": "1. Gespräch terminiert",
    "1_done":      "1. Gespräch geführt",
    "2_scheduled": "2. Gespräch terminiert",
    "2_done":      "2. Gespräch geführt",
    "3_scheduled": "3. Gespräch terminiert",
    "3_done":      "3. Gespräch geführt",
    "4_scheduled": "4. Gespräch terminiert",
    "4_done":      "4. Gespräch geführt",
    "5_scheduled": "5. Gespräch terminiert",
    "5_done":      "5. Gespräch geführt",
}

PIPELINE_ORDER = [
    MainStatus.prospecting,
    MainStatus.applied,
    MainStatus.hr,
    MainStatus.fb,
    MainStatus.waiting,
    MainStatus.negotiating,
    MainStatus.signed,
    MainStatus.rejected,
]

# Excel-Import: old flat status → (main_status, sub_status)
EXCEL_IMPORT_MAP: dict[str, tuple[str, str | None]] = {
    "00 Anbahnung":                        ("prospecting", None),
    "01 beworben":                         ("applied",     None),
    "02 1. Gespräch HR/HH terminiert":     ("hr",          "1_scheduled"),
    "03 1. Gespräch HR/HH geführt":        ("hr",          "1_done"),
    "05 2. Interview geführt":             ("hr",          "2_done"),
    "06 1. Gespräch FB terminiert":        ("fb",          "1_scheduled"),
    "07 3. Interview geführt":             ("fb",          "1_done"),
    "08 2. Gespräch FB terminiert":        ("fb",          "2_scheduled"),
    "12 Warten auf finale Entscheidung":   ("waiting",     None),
}

# Old flat status values (migration) → (main_status, sub_status)
OLD_STATUS_MIGRATION: dict[str, tuple[str, str | None]] = {
    "prospecting":   ("prospecting", None),
    "applied":       ("applied",     None),
    "hr_scheduled":  ("hr",          "1_scheduled"),
    "hr_done":       ("hr",          "1_done"),
    "interview_2":   ("hr",          "2_done"),
    "fb_scheduled":  ("fb",          "1_scheduled"),
    "interview_3":   ("fb",          "1_done"),
    "fb_2":          ("fb",          "2_scheduled"),
    "final_decision":("waiting",     None),
    "offer":         ("negotiating", None),
    "rejected":      ("rejected",    None),
}

# Excel-Export: (main_status, sub_status) → Excel-Statuswert
EXCEL_EXPORT_MAP: dict[tuple[str, str | None], str] = {
    ("prospecting", None):          "00 Anbahnung",
    ("applied",     None):          "01 beworben",
    ("hr",          "1_scheduled"): "02 1. Gespräch HR/HH terminiert",
    ("hr",          "1_done"):      "03 1. Gespräch HR/HH geführt",
    ("hr",          "2_done"):      "05 2. Interview geführt",
    ("fb",          "1_scheduled"): "06 1. Gespräch FB terminiert",
    ("fb",          "1_done"):      "07 3. Interview geführt",
    ("fb",          "2_scheduled"): "08 2. Gespräch FB terminiert",
    ("waiting",     None):          "12 Warten auf finale Entscheidung",
    ("negotiating", None):          "Angebotsverhandlung",
    ("signed",      None):          "Unterschrift",
    ("rejected",    None):          "",
}


class Application(Base):
    __tablename__ = "applications"

    id                  = Column(Integer, primary_key=True, index=True)
    firma               = Column(String, nullable=False)
    rolle               = Column(String, nullable=False)

    # New status model
    main_status         = Column(String, default="applied", nullable=False)
    sub_status          = Column(String, nullable=True)   # e.g. "1_scheduled", "2_done"

    is_headhunter       = Column(Boolean, default=False)
    zielfirma_bei_hh    = Column(String, nullable=True)
    quelle              = Column(String, nullable=True)
    wurde_besetzt_von   = Column(String, nullable=True)

    datum_bewerbung     = Column(Date, nullable=True)
    letztes_update      = Column(Date, nullable=True)


    kommentar           = Column(Text, nullable=True)
    linkedin_job_id     = Column(String, nullable=True, index=True)
    stellenanzeige_url  = Column(String, nullable=True)

    gespraech_1         = Column(Text, nullable=True)
    gespraech_2         = Column(Text, nullable=True)
    gespraech_3         = Column(Text, nullable=True)
    gespraech_4         = Column(Text, nullable=True)
    gespraech_5         = Column(Text, nullable=True)

    created_at          = Column(DateTime(timezone=True), server_default=func.now())
    updated_at          = Column(DateTime(timezone=True), onupdate=func.now())

    contacts            = relationship("Contact", secondary="contact_application", back_populates="applications")
    events              = relationship("Event", back_populates="application", cascade="all, delete-orphan")

    @property
    def abgesagt(self) -> bool:
        return self.main_status == "rejected"

    @property
    def ghosting(self) -> bool:
        # list_applications sets _ghosting_override before overwriting letztes_update
        if hasattr(self, '_ghosting_override'):
            return self._ghosting_override
        if self.main_status in ("signed", "negotiating", "prospecting"):
            return False
        if self.main_status == "rejected":
            # Ghosted-then-rejected: gap of >= 14 days between application and rejection
            if self.datum_bewerbung and self.letztes_update:
                return (self.letztes_update - self.datum_bewerbung).days >= 14
            return False
        # Active application: no activity for > 14 days
        from datetime import date
        last = self.letztes_update or self.datum_bewerbung
        if last is None:
            return False
        return (date.today() - last).days > 14

    def __repr__(self):
        return f"<Application {self.firma} | {self.rolle}>"


class Contact(Base):
    __tablename__ = "contacts"

    id              = Column(Integer, primary_key=True, index=True)

    name            = Column(String, nullable=False)
    email           = Column(String, nullable=True)
    telefon         = Column(String, nullable=True)
    linkedin_url    = Column(String, nullable=True)
    foto_url        = Column(String, nullable=True)

    firma           = Column(String, nullable=True)
    rolle           = Column(String, nullable=True)
    typ             = Column(String, nullable=True)

    notizen         = Column(Text, nullable=True)
    letzter_kontakt = Column(Date, nullable=True)

    created_at      = Column(DateTime(timezone=True), server_default=func.now())

    applications    = relationship("Application", secondary="contact_application", back_populates="contacts")


class Event(Base):
    __tablename__ = "events"

    id              = Column(Integer, primary_key=True, index=True)
    application_id  = Column(Integer, ForeignKey("applications.id"), nullable=False)

    typ             = Column(String)
    datum           = Column(Date, nullable=True)
    titel           = Column(String, nullable=True)
    notiz           = Column(Text, nullable=True)
    autor           = Column(String, nullable=True)   # sender for mail events
    source          = Column(String, nullable=True)   # "gmail","gcal","notes","call"
    external_id     = Column(String, nullable=True)   # original ID from sync source (for deep links)

    created_at      = Column(DateTime(timezone=True), server_default=func.now())

    application     = relationship("Application", back_populates="events")
    attachments     = relationship("Attachment", back_populates="event", cascade="all, delete-orphan")


class Attachment(Base):
    __tablename__ = "attachments"

    id           = Column(Integer, primary_key=True, index=True)
    event_id     = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    filename     = Column(String, nullable=False)
    content_type = Column(String, nullable=True)
    size_bytes   = Column(Integer, nullable=True)
    storage_path = Column(String, nullable=False)   # relative to /data/attachments/
    source       = Column(String, nullable=True)    # "gmail", "icloud_mail", "local_files", etc.
    external_id  = Column(String, nullable=True)    # original attachment ID from source
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    event = relationship("Event", back_populates="attachments")


class GoogleSync(Base):
    __tablename__ = "google_sync"

    id                  = Column(Integer, primary_key=True)
    client_id           = Column(String, nullable=False)
    client_secret_enc   = Column(Text, nullable=False)
    access_token_enc    = Column(Text, nullable=True)
    refresh_token_enc   = Column(Text, nullable=True)
    token_expiry        = Column(DateTime(timezone=True), nullable=True)
    oauth_state         = Column(String, nullable=True)   # CSRF token during flow
    gmail_email         = Column(String, nullable=True)   # authenticated Google account email
    gmail_last_sync     = Column(DateTime(timezone=True), nullable=True)
    gcal_last_sync      = Column(DateTime(timezone=True), nullable=True)
    created_at          = Column(DateTime(timezone=True), server_default=func.now())
    updated_at          = Column(DateTime(timezone=True), onupdate=func.now())


class SyncedItem(Base):
    __tablename__ = "synced_items"

    id          = Column(Integer, primary_key=True)
    source      = Column(String, nullable=False)
    external_id = Column(String, nullable=False)
    processed_at = Column(DateTime(timezone=True), server_default=func.now())


class PendingMatch(Base):
    __tablename__ = "pending_matches"

    id                    = Column(Integer, primary_key=True)
    source                = Column(String, nullable=False)   # "gmail", "gcal"
    external_id           = Column(String, nullable=False)
    confidence            = Column(Integer, nullable=False)  # 0–100
    event_type            = Column(String, nullable=True)
    datum                 = Column(Date, nullable=True)
    titel                 = Column(String, nullable=True)
    extract               = Column(Text, nullable=True)
    raw_content           = Column(Text, nullable=True)
    suggested_app_id      = Column(Integer, ForeignKey("applications.id"), nullable=True)
    suggested_main_status = Column(String, nullable=True)
    suggested_sub_status  = Column(String, nullable=True)
    status_only           = Column(Boolean, default=False)  # True = status change suggestion, no event
    review_status         = Column(String, default="pending")  # pending|approved|rejected
    created_at            = Column(DateTime(timezone=True), server_default=func.now())

    application = relationship("Application")


class ICloudSync(Base):
    __tablename__ = "icloud_sync"

    id                    = Column(Integer, primary_key=True)
    apple_id              = Column(String, nullable=False)
    icloud_email          = Column(String, nullable=True)   # @icloud.com/@me.com for IMAP; falls back to apple_id
    app_password_enc      = Column(Text, nullable=False)
    web_password_enc      = Column(Text, nullable=True)   # actual Apple ID password for pyicloud (Notes)
    mail_last_sync        = Column(DateTime(timezone=True), nullable=True)
    calendar_last_sync    = Column(DateTime(timezone=True), nullable=True)
    reminders_last_sync   = Column(DateTime(timezone=True), nullable=True)
    contacts_last_sync    = Column(DateTime(timezone=True), nullable=True)
    notes_last_sync       = Column(DateTime(timezone=True), nullable=True)
    calls_last_sync       = Column(DateTime(timezone=True), nullable=True)
    created_at            = Column(DateTime(timezone=True), server_default=func.now())
    updated_at            = Column(DateTime(timezone=True), onupdate=func.now())


class CallsConfig(Base):
    __tablename__ = "calls_config"

    id          = Column(Integer, primary_key=True)
    enabled     = Column(Boolean, default=True, nullable=False)
    last_sync   = Column(DateTime(timezone=True), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())


class LinkedInSync(Base):
    __tablename__ = "linkedin_sync"

    id               = Column(Integer, primary_key=True)
    email            = Column(String, nullable=False)
    password_enc     = Column(Text, nullable=False)    # Fernet-encrypted
    session_cookies  = Column(Text, nullable=True)     # JSON blob, reused across syncs
    last_sync        = Column(DateTime(timezone=True), nullable=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())
    updated_at       = Column(DateTime(timezone=True), onupdate=func.now())


class AiSettings(Base):
    __tablename__ = "ai_settings"

    id          = Column(Integer, primary_key=True)
    provider    = Column(String, nullable=False, default="groq")
    model       = Column(String, nullable=False, default="groq/llama-3.3-70b-versatile")
    api_key_enc = Column(Text, nullable=True)   # Fernet-encrypted, null for Ollama
    base_url    = Column(String, nullable=True)  # for Ollama / custom
    enabled     = Column(Boolean, default=True)

    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())


class SyncSettings(Base):
    __tablename__ = "sync_settings"

    id                       = Column(Integer, primary_key=True)
    google_enabled           = Column(Boolean, default=True, nullable=False)
    gmail_enabled            = Column(Boolean, default=True, nullable=False)
    gcal_enabled             = Column(Boolean, default=True, nullable=False)
    icloud_enabled           = Column(Boolean, default=True, nullable=False)
    icloud_mail_enabled      = Column(Boolean, default=True, nullable=False)
    icloud_cal_enabled       = Column(Boolean, default=True, nullable=False)
    icloud_notes_enabled     = Column(Boolean, default=True, nullable=False)
    icloud_reminders_enabled = Column(Boolean, default=True, nullable=False)
    icloud_contacts_enabled  = Column(Boolean, default=True, nullable=False)
    icloud_calls_enabled     = Column(Boolean, default=True, nullable=False)
    linkedin_enabled         = Column(Boolean, default=True, nullable=False)
    files_enabled            = Column(Boolean, default=True, nullable=False)


class FilesConfig(Base):
    __tablename__ = "files_config"

    id           = Column(Integer, primary_key=True)
    folder_path  = Column(String, nullable=True)
    enabled      = Column(Boolean, default=True, nullable=False)
    last_sync    = Column(DateTime(timezone=True), nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    updated_at   = Column(DateTime(timezone=True), onupdate=func.now())
