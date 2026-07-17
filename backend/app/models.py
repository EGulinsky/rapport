from sqlalchemy import Column, Integer, String, Date, Boolean, Text, DateTime, ForeignKey, Table, Index
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

# Was als "Kalendereintrag" zählt — geteilt zwischen routers/calendar.py (Anzeige)
# und routers/cleanup.py (Bereinigen-Scope "calendar"), damit beide exakt dieselben
# Events meinen.
CALENDAR_TYPEN = ('gespräch', 'interview', 'termin')
CALENDAR_SOURCES = ('gcal', 'icloud_cal')

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


class CompanyProfile(Base):
    """Background data about a company or headhunter, populated by async web sync."""
    __tablename__ = "company_profiles"
    __table_args__ = (
        Index("ix_company_profiles_user_id_name_norm", "user_id", "name_norm", unique=True),
    )

    id                   = Column(Integer, primary_key=True, index=True)
    user_id              = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    name_norm            = Column(String, nullable=False)  # normalised key for dedup, unique per Nutzer (siehe __table_args__)
    name_display         = Column(String, nullable=True)

    # Location
    hq_city              = Column(String, nullable=True)
    hq_country           = Column(String, nullable=True)

    # Classification
    industry             = Column(String, nullable=True)   # free text, e.g. "Automotive Software"
    company_type         = Column(String, nullable=True)   # startup|kmu|konzern|beratung|headhunter|nonprofit|public|other
    employee_range       = Column(String, nullable=True)   # "1-10"|"11-50"|"51-200"|"201-500"|"501-1000"|"1001-5000"|"5001-10000"|"10001+"
    employee_count       = Column(Integer, nullable=True)  # exact number if available
    founded_year         = Column(Integer, nullable=True)

    # Online presence
    website              = Column(String, nullable=True)
    linkedin_company_url = Column(String, nullable=True)

    # Free-text summary from sync source
    description          = Column(Text, nullable=True)

    # Custom logo (base64 data URI)
    logo_data            = Column(Text, nullable=True)

    # Sync bookkeeping
    sync_source          = Column(String, nullable=True)   # "linkedin"|"wikidata"|"manual"
    sync_status          = Column(String, default="pending", nullable=False)  # pending|done|failed|needs_review
    sync_error           = Column(Text, nullable=True)
    last_synced_at       = Column(DateTime(timezone=True), nullable=True)

    created_at           = Column(DateTime(timezone=True), server_default=func.now())
    updated_at           = Column(DateTime(timezone=True), onupdate=func.now())

    parent_company_id    = Column(Integer, ForeignKey("company_profiles.id"), nullable=True)

    applications         = relationship("Application", foreign_keys="Application.company_profile_id",    back_populates="company_profile")
    hh_applications      = relationship("Application", foreign_keys="Application.target_company_profile_id", back_populates="target_company_profile")
    direct_contacts      = relationship("Contact", foreign_keys="Contact.company_profile_id", back_populates="company_profile")
    parent               = relationship("CompanyProfile", foreign_keys=[parent_company_id], remote_side="CompanyProfile.id", back_populates="subsidiaries")
    subsidiaries         = relationship("CompanyProfile", foreign_keys="CompanyProfile.parent_company_id", back_populates="parent")


class Application(Base):
    __tablename__ = "applications"

    id                   = Column(Integer, primary_key=True, index=True)
    user_id              = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    firma                = Column(String, nullable=False)
    rolle                = Column(String, nullable=False)

    # New status model
    main_status         = Column(String, default="applied", nullable=False)
    sub_status          = Column(String, nullable=True)   # e.g. "1_scheduled", "2_done"

    is_headhunter       = Column(Boolean, default=False)
    zielfirma_bei_hh    = Column(String, nullable=True)
    quelle              = Column(String, nullable=True)
    wurde_besetzt_von   = Column(String, nullable=True)
    ort                 = Column(String, nullable=True)

    datum_bewerbung     = Column(Date, nullable=True)
    letztes_update      = Column(Date, nullable=True)


    kommentar           = Column(Text, nullable=True)
    linkedin_job_id     = Column(String, nullable=True, index=True)
    stellenanzeige_url  = Column(String, nullable=True)
    pre_rejection_status = Column(String, nullable=True)

    # Company background data (populated by background sync)
    company_profile_id        = Column(Integer, ForeignKey("company_profiles.id"), nullable=True)
    target_company_profile_id = Column(Integer, ForeignKey("company_profiles.id"), nullable=True)

    gespraech_1         = Column(Text, nullable=True)
    gespraech_2         = Column(Text, nullable=True)
    gespraech_3         = Column(Text, nullable=True)
    gespraech_4         = Column(Text, nullable=True)
    gespraech_5         = Column(Text, nullable=True)

    ai_color            = Column(String, nullable=True)   # 'green', 'yellow', 'red'
    ai_next_step        = Column(Text, nullable=True)
    ai_reasoning        = Column(Text, nullable=True)
    ai_assessed_at      = Column(DateTime(timezone=True), nullable=True)

    created_at          = Column(DateTime(timezone=True), server_default=func.now())
    updated_at          = Column(DateTime(timezone=True), onupdate=func.now())

    contacts                = relationship("Contact", secondary="contact_application", back_populates="applications")
    events                  = relationship("Event", back_populates="application", cascade="all, delete-orphan")
    company_profile         = relationship("CompanyProfile", foreign_keys=[company_profile_id],        back_populates="applications")
    target_company_profile  = relationship("CompanyProfile", foreign_keys=[target_company_profile_id], back_populates="hh_applications")

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
    user_id         = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    name            = Column(String, nullable=False)
    vorname         = Column(String, nullable=True)
    email           = Column(String, nullable=True)
    linkedin_url    = Column(String, nullable=True)
    foto_url        = Column(String, nullable=True)

    firma           = Column(String, nullable=True)
    rolle           = Column(String, nullable=True)
    typ             = Column(String, nullable=True)

    notizen         = Column(Text, nullable=True)
    letzter_kontakt = Column(Date, nullable=True)

    icloud_last_synced_at = Column(DateTime(timezone=True), nullable=True)

    created_at      = Column(DateTime(timezone=True), server_default=func.now())

    company_profile_id = Column(Integer, ForeignKey("company_profiles.id"), nullable=True)
    company_profile    = relationship("CompanyProfile", foreign_keys=[company_profile_id], back_populates="direct_contacts")

    applications    = relationship("Application", secondary="contact_application", back_populates="contacts")
    phones          = relationship("ContactPhone", cascade="all, delete-orphan", order_by="ContactPhone.id")

    @property
    def display_name(self) -> str:
        """Most contact-creation paths store only the surname in "name"
        (structured N:-field split from vCard imports), so every user-facing
        string (audit log, event titles, etc.) needs vorname + name, not name
        alone. One path (mail-signature contact upsert, sync_common.py)
        instead stores the already-full name in "name" and redundantly
        duplicates the first name into "vorname" — guard against that
        prepending vorname a second time ("Niklas Niklas Zoch")."""
        if not self.vorname:
            return self.name
        if self.name.lower().startswith(self.vorname.lower()):
            return self.name
        return f"{self.vorname} {self.name}"


class ContactPhone(Base):
    __tablename__ = "contact_phones"

    id              = Column(Integer, primary_key=True, index=True)
    contact_id      = Column(Integer, ForeignKey("contacts.id"), nullable=False, index=True)
    user_id         = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    number          = Column(String, nullable=False)
    type            = Column(String, nullable=False, default="other")   # mobile|home|work|main|other


class MergeAlias(Base):
    """Tracks original identifiers of merged entities so future syncs find the canonical."""
    __tablename__ = "merge_aliases"

    id              = Column(Integer, primary_key=True, index=True)
    user_id         = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    entity_type     = Column(String, nullable=False)   # "application" | "contact"
    canonical_id    = Column(Integer, nullable=False, index=True)
    # Application alias fields
    alias_firma     = Column(String, nullable=True)
    alias_rolle     = Column(String, nullable=True)
    alias_li_job_id = Column(String, nullable=True, index=True)
    # Contact alias fields
    alias_name      = Column(String, nullable=True)
    alias_email     = Column(String, nullable=True, index=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())


class Event(Base):
    __tablename__ = "events"

    id              = Column(Integer, primary_key=True, index=True)
    user_id         = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
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
    user_id      = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
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
    user_id             = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
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
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    source      = Column(String, nullable=False)
    external_id = Column(String, nullable=False)
    processed_at = Column(DateTime(timezone=True), server_default=func.now())


class PendingMatch(Base):
    __tablename__ = "pending_matches"

    id                    = Column(Integer, primary_key=True)
    user_id               = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
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
    user_id               = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
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
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    enabled     = Column(Boolean, default=True, nullable=False)
    last_sync   = Column(DateTime(timezone=True), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())


class LinkedInSync(Base):
    __tablename__ = "linkedin_sync"

    id               = Column(Integer, primary_key=True)
    user_id          = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    email            = Column(String, nullable=False)
    password_enc     = Column(Text, nullable=False)    # Fernet-encrypted
    session_cookies  = Column(Text, nullable=True)     # JSON blob, reused across syncs
    last_sync        = Column(DateTime(timezone=True), nullable=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())
    updated_at       = Column(DateTime(timezone=True), onupdate=func.now())


class AiSettings(Base):
    __tablename__ = "ai_settings"

    id          = Column(Integer, primary_key=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    provider    = Column(String, nullable=False, default="groq")
    model       = Column(String, nullable=False, default="groq/llama-3.3-70b-versatile")
    api_key_enc = Column(Text, nullable=True)   # Fernet-encrypted, null for Ollama
    base_url    = Column(String, nullable=True)  # for Ollama / custom
    enabled     = Column(Boolean, default=True)

    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())


class MapsSettings(Base):
    __tablename__ = "maps_settings"

    id          = Column(Integer, primary_key=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    api_key_enc = Column(Text, nullable=True)   # Fernet-encrypted Google Maps API key

    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())


class AgentSettings(Base):
    """Connection to the host-side Rapport Agent (replaces the three old
    unauthenticated bridges: files/notes/calls). Token is Fernet-encrypted,
    same pattern as AiSettings/MapsSettings — the agent generates it on
    first run, the user pastes it in once."""
    __tablename__ = "agent_settings"

    id          = Column(Integer, primary_key=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    url         = Column(String, nullable=True)   # override; None = default AGENT_URL env var
    token_enc   = Column(Text, nullable=True)

    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())


class SyncSettings(Base):
    __tablename__ = "sync_settings"

    id                       = Column(Integer, primary_key=True)
    user_id                  = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
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
    # "off" | "normal" | "verbose"
    audit_log_level          = Column(String, default="normal", nullable=False, server_default="normal")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id                 = Column(Integer, primary_key=True, index=True)
    user_id            = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    app_id             = Column(Integer, ForeignKey("applications.id", ondelete="SET NULL"), nullable=True, index=True)
    contact_id         = Column(Integer, ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True, index=True)
    company_profile_id = Column(Integer, ForeignKey("company_profiles.id", ondelete="SET NULL"), nullable=True, index=True)
    event_id           = Column(Integer, ForeignKey("events.id", ondelete="SET NULL"), nullable=True, index=True)
    timestamp          = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    # application | contact | company | event — explicit, survives even if the
    # referenced row is later deleted (FK-based inference is unreliable, see add_audit()).
    entity_type        = Column(String, nullable=True, index=True)
    # create | update | delete | status_change | merge | import
    action             = Column(String, nullable=False)
    field              = Column(String, nullable=True)   # which field changed (verbose mode)
    old_value          = Column(Text, nullable=True)
    new_value          = Column(Text, nullable=True)
    # user | gmail | icloud_mail | linkedin | import | merge | system | …
    source             = Column(String, nullable=False, default="user")
    reason             = Column(Text, nullable=True)     # free-text explanation

    application     = relationship("Application", foreign_keys=[app_id])
    contact         = relationship("Contact", foreign_keys=[contact_id])
    company_profile = relationship("CompanyProfile", foreign_keys=[company_profile_id])
    event           = relationship("Event", foreign_keys=[event_id])


class FilesConfig(Base):
    __tablename__ = "files_config"

    id           = Column(Integer, primary_key=True)
    user_id      = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    folder_path  = Column(String, nullable=True)
    enabled      = Column(Boolean, default=True, nullable=False)
    last_sync    = Column(DateTime(timezone=True), nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    updated_at   = Column(DateTime(timezone=True), onupdate=func.now())


class BackupConfig(Base):
    __tablename__ = "backup_config"

    id              = Column(Integer, primary_key=True)
    user_id         = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    enabled         = Column(Boolean, default=False, nullable=False)
    backup_folder   = Column(String, nullable=True)   # absolute path on host Mac
    frequency_hours = Column(Integer, default=24, nullable=False)
    keep_count      = Column(Integer, default=7, nullable=False)
    last_backup     = Column(DateTime(timezone=True), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now())


class LogoSettings(Base):
    __tablename__ = "logo_settings"

    id      = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    api_key = Column(String, nullable=True)   # Logo.dev public pk_ key


class User(Base):
    __tablename__ = "users"

    id             = Column(Integer, primary_key=True, index=True)
    email          = Column(String, unique=True, nullable=False, index=True)
    password_hash  = Column(String, nullable=False)
    email_verified = Column(Boolean, default=False, nullable=False)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())
    updated_at     = Column(DateTime(timezone=True), onupdate=func.now())

    vorname          = Column(String, nullable=True)
    nachname         = Column(String, nullable=True)
    linkedin_url     = Column(String, nullable=True)
    cv_filename      = Column(String, nullable=True)
    cv_content_type  = Column(String, nullable=True)
    cv_size_bytes    = Column(Integer, nullable=True)
    cv_storage_path  = Column(String, nullable=True)

    # Cached extraction of cv_storage_path's text (app/cv_extract.py), fed
    # into the AI assessment prompt. Extracted once at upload time — a
    # per-assessment re-extraction (the original implementation) both
    # re-parsed the PDF/DOCX on every single "Reassess" click (slow: real
    # measured cost, not free) and did so synchronously inside an `async
    # def` endpoint, blocking the whole app's event loop for the duration
    # for every user, not just the one being assessed — the same class of
    # bug just fixed for the iCloud sync, self-inflicted here.
    cv_extracted_text = Column(Text, nullable=True)

    # Cached extracted text from linkedin_url's profile page (headline/about/
    # experience, scraped once on demand via the existing LinkedIn session
    # rather than live per assessment — see routers/sync_linkedin.py's
    # scrape_own_profile()). NULL until the user syncs at least once.
    linkedin_profile_text       = Column(Text, nullable=True)
    linkedin_profile_synced_at  = Column(DateTime(timezone=True), nullable=True)

    # UI-Sprache des Kontos ('de' | 'en', erweiterbar). Default 'de' schützt nur
    # bestehende Zeilen bei der Migration — neue Registrierungen setzen den Wert
    # immer explizit über RegisterPayload.ui_language (Default dort: 'en').
    ui_language      = Column(String, nullable=False, server_default="de")


class EmailVerificationCode(Base):
    """6-stelliger Code für E-Mail-Bestätigung und Passwort-Reset — gleicher
    Mechanismus, unterschieden über `purpose`."""
    __tablename__ = "email_verification_codes"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    code       = Column(String, nullable=False)
    purpose    = Column(String, nullable=False)  # "verify_email" | "reset_password"
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at    = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", foreign_keys=[user_id])
