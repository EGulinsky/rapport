from sqlalchemy import Column, Integer, String, Date, Boolean, Text, DateTime, Float, ForeignKey, Table, Index
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
    # Cached geocode of `ort`, set/cleared whenever `ort` changes (see
    # _geocode_ort() in applications.py) -- avoids re-geocoding on
    # every distance calculation. None if geocoding failed or ort is empty.
    ort_lat             = Column(Float, nullable=True)
    ort_lng             = Column(Float, nullable=True)
    # Cached car-navigation distance/duration from the account's home
    # location to `ort` (see _update_drive_distance() in applications.py) --
    # a live routing call per request would be too slow/costly, so this is
    # recomputed only when `ort` changes or (via backfill_drive_distance())
    # after home_location changes. Straight-line/haversine was the original
    # v4.6.23 implementation; replaced because it understated real commute
    # distance and gave no time estimate at all. None if either coordinate
    # is missing or the routing call failed.
    drive_distance_km   = Column(Float, nullable=True)
    drive_duration_min  = Column(Float, nullable=True)

    salary_currency        = Column(String, nullable=True)   # ISO code, e.g. "EUR"
    salary_expectation_min = Column(Integer, nullable=True)
    salary_expectation_max = Column(Integer, nullable=True)
    salary_budget_min      = Column(Integer, nullable=True)
    salary_budget_max      = Column(Integer, nullable=True)

    # Optional per-slot breakdown: when set, the corresponding plain total
    # above is kept equal to fixed + bonus (enforced in applications.py,
    # not silently rewritten) rather than being a redundant free number.
    salary_expectation_min_fixed = Column(Integer, nullable=True)
    salary_expectation_min_bonus = Column(Integer, nullable=True)
    salary_expectation_max_fixed = Column(Integer, nullable=True)
    salary_expectation_max_bonus = Column(Integer, nullable=True)
    salary_budget_min_fixed      = Column(Integer, nullable=True)
    salary_budget_min_bonus      = Column(Integer, nullable=True)
    salary_budget_max_fixed      = Column(Integer, nullable=True)
    salary_budget_max_bonus      = Column(Integer, nullable=True)

    salary_expectation_company_car = Column(Boolean, default=False)
    salary_budget_company_car      = Column(Boolean, default=False)

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
    def salary_mismatch(self) -> bool:
        """True only when the best possible budget (its max if a range was
        given, else its single value) is still below the lowest amount the
        applicant would accept — i.e. the ranges can't possibly meet. If
        either side has no value at all, or the ranges could plausibly
        overlap, this stays False rather than flagging a false positive."""
        if self.salary_expectation_min is None:
            return False
        budget_ceiling = self.salary_budget_max if self.salary_budget_max is not None else self.salary_budget_min
        if budget_ceiling is None:
            return False
        return budget_ceiling < self.salary_expectation_min

    @property
    def ghosting(self) -> bool:
        # Real callers (list_applications, get_application, analytics,
        # export_excel) always inject a precise, event-based value via
        # _apply_ghosting_overrides() in routers/applications.py — see there
        # for the actual algorithm. This branch is a degraded, DB-query-free
        # fallback for the rare case something reads .ghosting directly off
        # an ORM object without that bulk pass (e.g. a bare unit test).
        if hasattr(self, '_ghosting_override'):
            return self._ghosting_override
        if self.main_status in ("signed", "prospecting"):
            return False
        if self.main_status == "rejected":
            # Ghosted-then-rejected: gap of >= 14 days between application and rejection
            if self.datum_bewerbung and self.letztes_update:
                return (self.letztes_update - self.datum_bewerbung).days >= 14
            return False
        # Active application (incl. negotiating): no activity for > 14 days
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
    # Full timestamp, when the sync source actually had one (mail, timed
    # calendar events, calls, LinkedIn messages, local files) -- datum stays
    # date-only for all existing floor/filter/display logic; this is used
    # purely to break same-day ties in newest-first sort order, which datum
    # alone can't do (see docs/ARCHITECTURE.md's timeline-sort note). Always
    # naive-but-UTC-semantic (see _to_naive_utc() in sync_common.py) --
    # SQLite/SQLAlchemy discards tzinfo on read-back anyway, so staying
    # naive avoids a naive/aware mismatch between a freshly-built value and
    # one just read from the database. None when the source is genuinely
    # time-blind (manual entries, LinkedIn's own relative-date scraping, or
    # an all-day calendar entry).
    datum_zeit      = Column(DateTime, nullable=True)
    # True for events whose datum_zeit is the v4.6.7 noon backfill's arbitrary
    # placeholder (set once, for events that predate the datum_zeit column
    # entirely, purely to fix same-day sort order) rather than a genuine
    # timestamp -- lets the frontend hide it instead of showing a fabricated
    # "14:00" as if it were real (see _flag_noon_backfill_placeholders() in
    # database.py). None/False for every event with a real timestamp, whether
    # sync-derived or explicitly set via the edit form.
    datum_zeit_is_placeholder = Column(Boolean, nullable=True)
    titel           = Column(String, nullable=True)
    notiz           = Column(Text, nullable=True)
    # For mail events: the *other party* -- the sender for received mail, or
    # the recipient for mail the account owner sent themselves (see
    # mail_direction below). Not the account owner's own name/address either
    # way, so the timeline always shows who's actually being corresponded
    # with rather than "me" for half of the conversation.
    autor           = Column(String, nullable=True)
    # "sent" or "received", mail events only (None for every other source) --
    # determined by comparing the mail's From header against the account's
    # own synced addresses (_get_owner_emails() in sync_common.py).
    mail_direction  = Column(String, nullable=True)
    source          = Column(String, nullable=True)   # "gmail","gcal","notes","call"
    external_id     = Column(String, nullable=True)   # original ID from sync source (for deep links)
    # Ready-to-use deep link for sources whose external_id alone can't be
    # turned into a working URL client-side -- e.g. Google Calendar's
    # "eventedit" link needs the calendar ID (the account's email) base64-
    # encoded together with the event ID, which the frontend has no access
    # to. Populated straight from the sync API's own link field (Google
    # Calendar's "htmlLink") instead of reconstructing it. None for sources
    # that build their link purely from external_id (gmail, icloud_*).
    external_url    = Column(String, nullable=True)

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


class LinkedInMessage(Base):
    """One row per LinkedIn message conversation, imported from the official
    "Get a copy of your data" CSV export (messages.csv) — replaces the live
    Playwright inbox scraper, which only ever scrolled the page once and
    missed most conversations. See attach_linkedin_messages_for_contact()
    in sync_linkedin.py for how these get turned into timeline events."""
    __tablename__ = "linkedin_messages"

    id                           = Column(Integer, primary_key=True)
    user_id                      = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    conversation_id              = Column(String, nullable=False, index=True)
    participant_name             = Column(String, nullable=False)   # raw, as shown in the CSV
    participant_name_normalized  = Column(String, nullable=False, index=True)
    participant_profile_url      = Column(String, nullable=True)
    last_message_date            = Column(DateTime, nullable=True)
    last_message_preview         = Column(Text, nullable=True)
    message_count                = Column(Integer, default=1)
    folder                       = Column(String, nullable=True)   # INBOX | ARCHIVE | SPAM
    imported_at                  = Column(DateTime(timezone=True), server_default=func.now())


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

    # Home address for the distance-to-job feature (KanbanBoard/ApplicationModal).
    # home_location is the free-text label shown in Settings (either picked from
    # the same autocomplete used for Application.ort, or reverse-geocoded from
    # the browser's own geolocation); home_lat/home_lng are geocoded once when
    # home_location is set/changed (see update_profile() in routers/auth.py) and
    # reused for every distance calculation rather than re-geocoding per request.
    home_location    = Column(String, nullable=True)
    home_lat         = Column(Float, nullable=True)
    home_lng         = Column(Float, nullable=True)


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
