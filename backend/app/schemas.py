from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime


class ContactPhoneIn(BaseModel):
    number: str
    type: str = "other"


class ContactPhoneOut(ContactPhoneIn):
    id: int

    model_config = {"from_attributes": True}


class ContactBase(BaseModel):
    name: str
    vorname: Optional[str] = None
    email: Optional[str] = None
    phones: List[ContactPhoneIn] = []
    linkedin_url: Optional[str] = None
    firma: Optional[str] = None
    rolle: Optional[str] = None
    typ: Optional[str] = None
    notizen: Optional[str] = None
    letzter_kontakt: Optional[date] = None


class ContactCreate(ContactBase):
    email: str  # required on create
    application_id: Optional[int] = None


class ContactUpdate(BaseModel):
    name: Optional[str] = None
    vorname: Optional[str] = None
    email: Optional[str] = None
    phones: Optional[List[ContactPhoneIn]] = None
    linkedin_url: Optional[str] = None
    firma: Optional[str] = None
    rolle: Optional[str] = None
    typ: Optional[str] = None
    notizen: Optional[str] = None
    letzter_kontakt: Optional[date] = None


class ContactRead(BaseModel):
    id: int
    name: str
    vorname: Optional[str] = None
    email: Optional[str] = None
    phones: List[ContactPhoneOut] = []
    linkedin_url: Optional[str] = None
    firma: Optional[str] = None
    rolle: Optional[str] = None
    typ: Optional[str] = None
    notizen: Optional[str] = None
    letzter_kontakt: Optional[date] = None
    icloud_last_synced_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ApplicationBrief(BaseModel):
    id: int
    firma: str
    rolle: str
    company_name_display: Optional[str] = None

    model_config = {"from_attributes": True}


class ContactWithApp(ContactRead):
    applications: List[ApplicationBrief] = []
    company_website: Optional[str] = None
    company_profile_id: Optional[int] = None


class AttachmentRead(BaseModel):
    id: int
    filename: str
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None
    source: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class EventBase(BaseModel):
    typ: str
    datum: Optional[date] = None
    titel: Optional[str] = None
    notiz: Optional[str] = None
    autor: Optional[str] = None
    source: Optional[str] = None


class EventUpdate(BaseModel):
    typ: Optional[str] = None
    datum: Optional[date] = None
    # Naive datetime representing Europe/Berlin wall-clock time (the app's
    # single hardcoded reference zone) -- converted to naive UTC in
    # update_event() (applications.py) via _berlin_naive_to_utc_naive()
    # before being stored, for consistency with sync-derived timestamps.
    # Sending an explicit null clears a previously-set time; omitting the
    # field entirely leaves the stored value untouched.
    datum_zeit: Optional[datetime] = None
    titel: Optional[str] = None
    notiz: Optional[str] = None

    model_config = {"from_attributes": True}


class EventCreate(EventBase):
    application_id: int


class EventRead(EventBase):
    id: int
    application_id: int
    external_id: Optional[str] = None
    # Ready-to-use deep link for sources whose external_id alone can't be
    # turned into a working URL client-side (currently only gcal -- see the
    # Event.external_url comment in models.py).
    external_url: Optional[str] = None
    # Full timestamp when the sync source had one -- read-only, used by the
    # frontend timeline to break same-day ties in newest-first sort order
    # (datum alone can't). Not on EventBase: the create form stays date-only;
    # editing an existing event's time goes through EventUpdate instead.
    datum_zeit: Optional[datetime] = None
    # True when datum_zeit is the v4.6.7 noon-backfill's arbitrary placeholder
    # rather than a real timestamp -- the frontend uses this to hide it
    # instead of showing a fabricated time as if it were genuine.
    datum_zeit_is_placeholder: Optional[bool] = None
    created_at: Optional[datetime] = None
    attachments: list[AttachmentRead] = []

    model_config = {"from_attributes": True}


class ExtractFromUrlRequest(BaseModel):
    url: str


class ApplicationBase(BaseModel):
    firma: str
    rolle: str
    main_status: str = "applied"
    sub_status: Optional[str] = None
    pre_rejection_status: Optional[str] = None
    is_headhunter: bool = False
    zielfirma_bei_hh: Optional[str] = None
    quelle: Optional[str] = None
    wurde_besetzt_von: Optional[str] = None
    ort: Optional[str] = None
    datum_bewerbung: Optional[date] = None
    letztes_update: Optional[date] = None
    kommentar: Optional[str] = None
    stellenanzeige_url: Optional[str] = None
    gespraech_1: Optional[str] = None
    gespraech_2: Optional[str] = None
    gespraech_3: Optional[str] = None
    gespraech_4: Optional[str] = None
    gespraech_5: Optional[str] = None
    salary_currency: Optional[str] = "EUR"
    salary_expectation_min: Optional[int] = None
    salary_expectation_max: Optional[int] = None
    salary_budget_min: Optional[int] = None
    salary_budget_max: Optional[int] = None
    salary_expectation_min_fixed: Optional[int] = None
    salary_expectation_min_bonus: Optional[int] = None
    salary_expectation_max_fixed: Optional[int] = None
    salary_expectation_max_bonus: Optional[int] = None
    salary_budget_min_fixed: Optional[int] = None
    salary_budget_min_bonus: Optional[int] = None
    salary_budget_max_fixed: Optional[int] = None
    salary_budget_max_bonus: Optional[int] = None
    salary_expectation_company_car: bool = False
    salary_budget_company_car: bool = False


class ApplicationCreate(ApplicationBase):
    # Not persisted — tells create_application() whether to skip the
    # automatic post-create LinkedIn sync (see applications.py). True when
    # the frontend prefilled this form from LinkedInImportModal; the AI
    # extraction that produced the prefill already pulled fresh LinkedIn
    # data, so re-running the per-app LinkedIn category search immediately
    # afterward would just re-find the same listing.
    created_from_linkedin: bool = False


class ApplicationUpdate(BaseModel):
    firma: Optional[str] = None
    company_profile_id: Optional[int] = None
    target_company_profile_id: Optional[int] = None
    rolle: Optional[str] = None
    main_status: Optional[str] = None
    sub_status: Optional[str] = None
    is_headhunter: Optional[bool] = None
    zielfirma_bei_hh: Optional[str] = None
    quelle: Optional[str] = None
    wurde_besetzt_von: Optional[str] = None
    ort: Optional[str] = None
    datum_bewerbung: Optional[date] = None
    letztes_update: Optional[date] = None
    kommentar: Optional[str] = None
    stellenanzeige_url: Optional[str] = None
    gespraech_1: Optional[str] = None
    gespraech_2: Optional[str] = None
    gespraech_3: Optional[str] = None
    gespraech_4: Optional[str] = None
    gespraech_5: Optional[str] = None
    salary_currency: Optional[str] = None
    salary_expectation_min: Optional[int] = None
    salary_expectation_max: Optional[int] = None
    salary_budget_min: Optional[int] = None
    salary_budget_max: Optional[int] = None
    salary_expectation_min_fixed: Optional[int] = None
    salary_expectation_min_bonus: Optional[int] = None
    salary_expectation_max_fixed: Optional[int] = None
    salary_expectation_max_bonus: Optional[int] = None
    salary_budget_min_fixed: Optional[int] = None
    salary_budget_min_bonus: Optional[int] = None
    salary_budget_max_fixed: Optional[int] = None
    salary_budget_max_bonus: Optional[int] = None
    salary_expectation_company_car: Optional[bool] = None
    salary_budget_company_car: Optional[bool] = None


class ApplicationRead(ApplicationBase):
    id: int
    abgesagt: bool
    salary_mismatch: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    company_profile_id: Optional[int] = None
    target_company_profile_id: Optional[int] = None
    company_name_display: Optional[str] = None
    target_company_name_display: Optional[str] = None
    company_website: Optional[str] = None
    target_company_website: Optional[str] = None
    ai_color: Optional[str] = None
    ai_next_step: Optional[str] = None
    ai_reasoning: Optional[str] = None
    ai_assessed_at: Optional[datetime] = None
    contacts: List[ContactRead] = []
    events: List[EventRead] = []

    model_config = {"from_attributes": True}


class ApplicationListItem(BaseModel):
    id: int
    firma: str
    rolle: str
    main_status: str
    sub_status: Optional[str] = None
    pre_rejection_status: Optional[str] = None
    is_headhunter: bool
    zielfirma_bei_hh: Optional[str] = None
    quelle: Optional[str] = None
    ort: Optional[str] = None
    datum_bewerbung: Optional[date] = None
    letztes_update: Optional[date] = None
    abgesagt: bool
    ghosting: bool
    salary_mismatch: bool
    kommentar: Optional[str] = None
    naechster_schritt: Optional[str] = None
    company_profile_id: Optional[int] = None
    target_company_profile_id: Optional[int] = None
    company_website: Optional[str] = None
    target_company_website: Optional[str] = None
    company_name_display: Optional[str] = None
    target_company_name_display: Optional[str] = None
    ai_color: Optional[str] = None
    ai_next_step: Optional[str] = None
    ai_reasoning: Optional[str] = None
    ai_assessed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class GoogleCredentials(BaseModel):
    client_id: str
    client_secret: str


class GoogleSyncStatus(BaseModel):
    connected: bool
    client_id: Optional[str] = None
    gmail_last_sync: Optional[datetime] = None
    gcal_last_sync: Optional[datetime] = None


class SyncResult(BaseModel):
    processed: int
    created: int
    skipped: int
    errors: List[str] = []
    requires_2fa: bool = False


class PendingMatchRead(BaseModel):
    id: int
    source: str
    confidence: int
    event_type: Optional[str] = None
    datum: Optional[date] = None
    titel: Optional[str] = None
    extract: Optional[str] = None
    raw_content: Optional[str] = None
    suggested_app_id: Optional[int] = None
    suggested_app_firma: Optional[str] = None
    suggested_app_rolle: Optional[str] = None
    suggested_main_status: Optional[str] = None
    suggested_sub_status: Optional[str] = None
    current_main_status: Optional[str] = None   # current app status for status_only items
    status_only: bool = False
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ApproveMatch(BaseModel):
    application_id: Optional[int] = None  # nicht nötig für event_type="company_candidate"
    event_type: Optional[str] = None
    datum: Optional[date] = None
    titel: Optional[str] = None
    linkedin_url: Optional[str] = None  # nur für event_type="company_candidate": gewählter Kandidat


class AiSettingsRead(BaseModel):
    provider: str
    model: str
    has_key: bool          # true if an encrypted key is stored
    base_url: Optional[str] = None
    enabled: bool

    model_config = {"from_attributes": True}


class AiSettingsWrite(BaseModel):
    provider: str
    model: str
    api_key: Optional[str] = None   # plain text; None = keep existing
    base_url: Optional[str] = None
    enabled: bool = True


class MapsSettingsRead(BaseModel):
    has_key: bool   # true if an encrypted Google Maps API key is stored

    model_config = {"from_attributes": True}


class MapsSettingsWrite(BaseModel):
    api_key: Optional[str] = None   # plain text; None/empty = clear existing key


class AgentSettingsRead(BaseModel):
    url: Optional[str] = None
    has_token: bool

    model_config = {"from_attributes": True}


class AgentSettingsWrite(BaseModel):
    url: Optional[str] = None
    token: Optional[str] = None   # plain text; None/empty = clear existing token


class AgentHealthModule(BaseModel):
    ok: bool
    error: Optional[str] = None
    phone_accessible: Optional[bool] = None
    whatsapp_accessible: Optional[bool] = None


class AgentHealth(BaseModel):
    reachable: bool
    version: Optional[str] = None
    platform: Optional[str] = None
    modules: dict[str, AgentHealthModule] = {}
    error: Optional[str] = None


class ImportResult(BaseModel):
    imported: int
    skipped: int
    errors: List[str] = []
    message: str


class ICloudCredentials(BaseModel):
    apple_id: str
    app_password: str
    icloud_email: Optional[str] = None   # @icloud.com/@me.com for IMAP
    web_password: Optional[str] = None   # actual Apple ID password for pyicloud (Notes)


class ICloud2FAVerify(BaseModel):
    code: str


class ICloudSyncStatus(BaseModel):
    connected: bool
    apple_id: Optional[str] = None
    icloud_email: Optional[str] = None
    mail_last_sync: Optional[datetime] = None
    calendar_last_sync: Optional[datetime] = None
    reminders_last_sync: Optional[datetime] = None
    contacts_last_sync: Optional[datetime] = None
    notes_last_sync: Optional[datetime] = None


class CallsStatus(BaseModel):
    enabled: bool
    last_sync: Optional[datetime] = None
    bridge_reachable: bool = False


class StatsResponse(BaseModel):
    total: int
    active: int
    rejected: int
    by_status: dict
