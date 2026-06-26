from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime


class ContactBase(BaseModel):
    name: str
    email: Optional[str] = None
    telefon: Optional[str] = None
    linkedin_url: Optional[str] = None
    firma: Optional[str] = None
    rolle: Optional[str] = None
    typ: Optional[str] = None
    notizen: Optional[str] = None
    letzter_kontakt: Optional[date] = None


class ContactCreate(ContactBase):
    application_id: Optional[int] = None


class ContactUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    telefon: Optional[str] = None
    linkedin_url: Optional[str] = None
    firma: Optional[str] = None
    rolle: Optional[str] = None
    typ: Optional[str] = None
    notizen: Optional[str] = None
    letzter_kontakt: Optional[date] = None


class ContactRead(ContactBase):
    id: int
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ApplicationBrief(BaseModel):
    id: int
    firma: str
    rolle: str

    model_config = {"from_attributes": True}


class ContactWithApp(ContactRead):
    applications: List[ApplicationBrief] = []
    company_website: Optional[str] = None


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
    titel: Optional[str] = None
    notiz: Optional[str] = None

    model_config = {"from_attributes": True}


class EventCreate(EventBase):
    application_id: int


class EventRead(EventBase):
    id: int
    application_id: int
    external_id: Optional[str] = None
    created_at: Optional[datetime] = None
    attachments: list[AttachmentRead] = []

    model_config = {"from_attributes": True}


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
    datum_bewerbung: Optional[date] = None
    letztes_update: Optional[date] = None
    kommentar: Optional[str] = None
    stellenanzeige_url: Optional[str] = None
    gespraech_1: Optional[str] = None
    gespraech_2: Optional[str] = None
    gespraech_3: Optional[str] = None
    gespraech_4: Optional[str] = None
    gespraech_5: Optional[str] = None


class ApplicationCreate(ApplicationBase):
    pass


class ApplicationUpdate(BaseModel):
    firma: Optional[str] = None
    rolle: Optional[str] = None
    main_status: Optional[str] = None
    sub_status: Optional[str] = None
    is_headhunter: Optional[bool] = None
    zielfirma_bei_hh: Optional[str] = None
    quelle: Optional[str] = None
    wurde_besetzt_von: Optional[str] = None
    datum_bewerbung: Optional[date] = None
    letztes_update: Optional[date] = None
    kommentar: Optional[str] = None
    stellenanzeige_url: Optional[str] = None
    gespraech_1: Optional[str] = None
    gespraech_2: Optional[str] = None
    gespraech_3: Optional[str] = None
    gespraech_4: Optional[str] = None
    gespraech_5: Optional[str] = None


class ApplicationRead(ApplicationBase):
    id: int
    abgesagt: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    company_profile_id: Optional[int] = None
    target_company_profile_id: Optional[int] = None
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
    datum_bewerbung: Optional[date] = None
    letztes_update: Optional[date] = None
    abgesagt: bool
    ghosting: bool
    kommentar: Optional[str] = None
    naechster_schritt: Optional[str] = None
    company_profile_id: Optional[int] = None
    target_company_profile_id: Optional[int] = None
    company_website: Optional[str] = None
    target_company_website: Optional[str] = None

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
    application_id: int
    event_type: Optional[str] = None
    datum: Optional[date] = None
    titel: Optional[str] = None


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
