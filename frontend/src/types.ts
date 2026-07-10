export type MainStatus =
  | 'prospecting'
  | 'applied'
  | 'hr'
  | 'fb'
  | 'waiting'
  | 'negotiating'
  | 'signed'
  | 'rejected'

export const MAIN_STATUS_LABELS: Record<MainStatus, string> = {
  prospecting:  'Anbahnung',
  applied:      'Beworben',
  hr:           'Gespräch HR/HH',
  fb:           'Gespräch FB',
  waiting:      'Warten auf Entscheidung',
  negotiating:  'Angebotsverhandlung',
  signed:       'Unterschrift',
  rejected:     'Absage',
}

export const MAIN_STATUS_COLORS: Record<MainStatus, string> = {
  prospecting:  'bg-gray-100 text-gray-700',
  applied:      'bg-blue-100 text-blue-800',
  hr:           'bg-yellow-100 text-yellow-800',
  fb:           'bg-purple-100 text-purple-800',
  waiting:      'bg-pink-100 text-pink-800',
  negotiating:  'bg-green-100 text-green-800',
  signed:       'bg-emerald-100 text-emerald-900',
  rejected:     'bg-red-100 text-red-700',
}

export const MAIN_PIPELINE: MainStatus[] = [
  'prospecting', 'applied', 'hr', 'fb', 'waiting', 'negotiating', 'signed',
]

export const SUB_STATUS_LABELS: Record<string, string> = {
  '1_scheduled': '1. Gespräch terminiert',
  '1_done':      '1. Gespräch geführt',
  '2_scheduled': '2. Gespräch terminiert',
  '2_done':      '2. Gespräch geführt',
  '3_scheduled': '3. Gespräch terminiert',
  '3_done':      '3. Gespräch geführt',
  '4_scheduled': '4. Gespräch terminiert',
  '4_done':      '4. Gespräch geführt',
  '5_scheduled': '5. Gespräch terminiert',
  '5_done':      '5. Gespräch geführt',
}

// Sub-status options for HR/FB stages (terminiert → geführt → nächste Runde)
export const SUB_STATUS_SEQUENCE = [
  '1_scheduled', '1_done',
  '2_scheduled', '2_done',
  '3_scheduled', '3_done',
  '4_scheduled', '4_done',
  '5_scheduled', '5_done',
]

export interface Application {
  id: number
  firma: string
  rolle: string
  main_status: MainStatus
  sub_status?: string
  pre_rejection_status?: string
  is_headhunter: boolean
  zielfirma_bei_hh?: string
  quelle?: string
  wurde_besetzt_von?: string
  ort?: string
  datum_bewerbung?: string
  letztes_update?: string
  naechster_schritt?: string
  abgesagt: boolean
  ghosting: boolean
  kommentar?: string
  stellenanzeige_url?: string
  gespraech_1?: string
  gespraech_2?: string
  gespraech_3?: string
  gespraech_4?: string
  gespraech_5?: string
  contacts?: Contact[]
  events?: Event[]
  company_profile_id?: number | null
  target_company_profile_id?: number | null
  company_website?: string | null
  target_company_website?: string | null
  company_name_display?: string | null
  target_company_name_display?: string | null
  ai_color?: 'green' | 'yellow' | 'red' | null
  ai_next_step?: string | null
  ai_reasoning?: string | null
  ai_assessed_at?: string | null
}

export interface CompanyContactRef {
  id: number
  name: string
  email?: string | null
  telefon?: string | null
  linkedin_url?: string | null
  firma?: string | null
  rolle?: string | null
  typ?: string | null
}

export interface CompanyProfile {
  id: number
  name_display: string | null
  name_norm: string
  industry: string | null
  company_type: string | null
  employee_range: string | null
  employee_count: number | null
  founded_year: number | null
  hq_city: string | null
  hq_country: string | null
  website: string | null
  linkedin_company_url: string | null
  description: string | null
  sync_source: string | null
  sync_status: string
  sync_error: string | null
  last_synced_at: string | null
  app_count?: number
  contact_count?: number
  has_logo?: boolean
  logo_data?: string | null
  parent_company_id?: number | null
  parent_name?: string | null
  subsidiaries?: { id: number; name_display: string | null; name_norm: string }[]
  applications?: { id: number; firma: string; rolle: string; main_status: string; datum_bewerbung?: string | null }[]
  contacts?: CompanyContactRef[]
}

export interface Contact {
  id: number
  name: string
  vorname?: string
  email?: string
  telefon?: string
  linkedin_url?: string
  firma?: string
  rolle?: string
  typ?: string
  notizen?: string
  letzter_kontakt?: string
  company_website?: string | null
  company_profile_id?: number | null
}

export interface ContactWithApp extends Contact {
  applications?: { id: number; firma: string; rolle: string; company_name_display?: string | null }[]
}

export interface ICloudContactCandidate {
  name: string
  email?: string | null
  telefon?: string | null
  firma?: string | null
  rolle?: string | null
  linkedin_url?: string | null
  already_imported?: boolean
}

export interface LinkedInPeopleCandidate {
  name: string
  headline?: string | null
  profile_url: string
}

export interface LinkedInCompanyCandidate {
  name: string
  url: string
  snippet?: string | null
}

export interface Attachment {
  id: number
  filename: string
  content_type?: string
  size_bytes?: number
  source?: string
  created_at?: string
}

export interface Event {
  id: number
  application_id: number
  typ: string
  datum?: string
  titel?: string
  notiz?: string
  autor?: string
  source?: string
  external_id?: string
  created_at?: string
  attachments?: Attachment[]
}

export interface FileBrowseItem {
  name: string
  path: string
  type: 'folder' | 'file'
  modified: number
}

export interface FileBrowseResult {
  path: string
  default_root: string
  items: FileBrowseItem[]
}

export interface ManualCandidate {
  id: number
  source: string
  external_id?: string
  event_type?: string
  datum?: string
  titel?: string
  extract?: string
  confidence: number
  suggested_app_id?: number
  suggested_app_firma?: string
}

export interface Stats {
  total: number
  active: number
  rejected: number
  by_status: Record<string, number>
}

export interface AiSettings {
  provider: string
  model: string
  has_key: boolean
  base_url?: string
  enabled: boolean
}

export interface AiSettingsWrite {
  provider: string
  model: string
  api_key?: string
  base_url?: string
  enabled: boolean
}

export interface MapsSettings {
  has_key: boolean
}

export interface AgentSettings {
  url?: string
  has_token: boolean
}

export interface AgentHealthModule {
  ok: boolean
  error?: string
  phone_accessible?: boolean
  whatsapp_accessible?: boolean
}

export interface AgentHealth {
  reachable: boolean
  version?: string
  platform?: string
  modules: Record<string, AgentHealthModule>
  error?: string
}

export interface GoogleSyncStatus {
  connected: boolean
  client_id?: string
  gmail_last_sync?: string
  gcal_last_sync?: string
}

export interface SyncResult {
  processed: number
  created: number
  skipped: number
  errors: string[]
  requires_2fa?: boolean
}

export interface ICloudSyncStatus {
  connected: boolean
  apple_id?: string
  icloud_email?: string
  mail_last_sync?: string
  calendar_last_sync?: string
  reminders_last_sync?: string
  contacts_last_sync?: string
  notes_last_sync?: string
}

export interface CallsStatus {
  enabled: boolean
  last_sync?: string
  bridge_reachable: boolean
}

export interface PendingMatch {
  id: number
  source: string
  confidence: number
  event_type?: string
  datum?: string
  titel?: string
  extract?: string
  raw_content?: string
  suggested_app_id?: number
  suggested_app_firma?: string
  suggested_app_rolle?: string
  suggested_main_status?: string
  suggested_sub_status?: string
  current_main_status?: string
  status_only?: boolean
  created_at?: string
}

export interface ImportResult {
  imported: number
  skipped: number
  errors: string[]
  message: string
}

export interface DupAppEntry {
  id: number
  firma: string
  rolle: string
  main_status: string
  abgesagt: boolean
  events: number
  contacts: number
  events_count?: number
  contacts_count?: number
}

export interface DupContactEntry {
  id: number
  name: string
  email?: string
  firma?: string
  apps: number
  apps_count?: number
}

export interface DupCompanyEntry {
  id: number
  name: string
  website?: string
  apps: number
  contacts: number
  apps_count?: number
  contacts_count?: number
}

export interface DupEventEntry {
  id: number
  application_id: number
  typ?: string
  datum?: string
  titel?: string
  has_notiz: boolean
}

export interface AppGroup {
  keep: DupAppEntry
  remove: DupAppEntry[]
  events_merged: number
  contacts_merged: number
}

export interface ContactGroup {
  keep: DupContactEntry
  remove: DupContactEntry[]
  apps_merged: number
}

export interface EventGroup {
  keep: DupEventEntry
  remove: DupEventEntry[]
}

export interface CompanyGroup {
  keep: DupCompanyEntry
  remove: DupCompanyEntry[]
  apps_merged: number
  contacts_merged: number
}

export type CleanupScope = 'applications' | 'contacts' | 'companies' | 'events'

export interface CleanupPreview {
  applications: AppGroup[]
  contacts: ContactGroup[]
  companies: CompanyGroup[]
  events: EventGroup[]
  cross_app_events: EventGroup[]
}

export interface CleanupResult {
  deleted_applications: number
  queued_contacts: number
  deleted_companies: number
  deleted_events: number
  queued_cross_app_events: number
  merged_app_groups: number
  contact_groups_queued: number
  merged_company_groups: number
  merged_event_groups: number
  cross_app_event_groups: number
}

export interface SyncSettings {
  google_enabled: boolean
  gmail_enabled: boolean
  gcal_enabled: boolean
  icloud_enabled: boolean
  icloud_mail_enabled: boolean
  icloud_cal_enabled: boolean
  icloud_notes_enabled: boolean
  icloud_reminders_enabled: boolean
  icloud_contacts_enabled: boolean
  icloud_calls_enabled: boolean
  linkedin_enabled: boolean
  files_enabled: boolean
  audit_log_level: 'off' | 'normal' | 'verbose'
}

export interface AuditEntry {
  id: number
  app_id: number | null
  app_firma: string | null
  app_rolle: string | null
  contact_id: number | null
  contact_name: string | null
  company_profile_id: number | null
  company_name: string | null
  event_id: number | null
  event_titel: string | null
  entity_type: 'application' | 'contact' | 'company' | 'event' | null
  timestamp: string
  action: string
  field: string | null
  old_value: string | null
  new_value: string | null
  source: string
  reason: string | null
}

export interface AuditLogResponse {
  total: number
  items: AuditEntry[]
}

export interface FilesConfig {
  folder_path?: string
  enabled: boolean
  last_sync?: string
  bridge_reachable?: boolean
}

export interface BackupEntry {
  name: string
  path: string
  modified: number
  size: number
}

export interface BackupStatus {
  enabled: boolean
  backup_folder?: string
  frequency_hours: number
  keep_count: number
  last_backup?: string
  backups: BackupEntry[]
}

export interface CalendarEvent {
  id: number
  application_id: number
  firma: string
  rolle: string
  main_status: string
  typ: string
  datum: string
  titel?: string
  notiz?: string
  autor?: string
  source?: string
}

export interface LinkedInSyncLogEntry {
  aktion: 'neu' | 'abgesagt' | 'aktualisiert' | 'unverändert'
  firma: string
  rolle: string
  von?: string
  zu?: string
  status?: string
}

export interface MergeRequest {
  winner_id: number
  loser_ids: number[]
  field_overrides: Record<string, number>
}

export interface MergeResult {
  success: boolean
  winner_id: number
}

export interface LinkedInSyncCategoryCount {
  card_type: string
  label: string
  count: number
}

export interface LinkedInSyncStatus {
  status: 'idle' | 'running' | 'done' | 'error' | 'needs_login' | 'needs_2fa'
  step: string
  processed: number
  total: number
  created: number
  updated: number
  skipped: number
  errors: string[]
  log: LinkedInSyncLogEntry[]
  category_counts: LinkedInSyncCategoryCount[]
  msg_processed: number
  msg_created: number
  started_at: string | null
  finished_at: string | null
}

export interface AnalyticsFunnelItem {
  status: string
  label: string
  count: number
  pct: number
}

export interface AnalyticsByMonth {
  month: string
  label: string
  count: number
}

export interface AnalyticsHHGroup {
  total: number
  gespräch: number
  offer: number
}

export interface AnalyticsStageConversion {
  from_status: string
  from_label: string
  to_status: string
  to_label: string
  rate: number
  drop_off: number
}

export interface AnalyticsSuccessGroup {
  label: string
  total: number
  gespräch: number
  offer: number
  gespräch_rate: number
  offer_rate: number
}

export interface AnalyticsSummary {
  kpis: {
    total: number
    active: number
    rejected: number
    signed: number
    ghosting_count: number
    ghosting_rate: number
    hh_count: number
    direct_count: number
    hh_pct: number
    conversion_gespräch: number
    conversion_offer: number
    avg_days_to_gespräch: number | null
    avg_days_applied_to_rejected: number | null
  }
  funnel: AnalyticsFunnelItem[]
  by_month: AnalyticsByMonth[]
  by_source: Array<{ source: string; count: number }>
  hh_vs_direct: { hh: AnalyticsHHGroup; direct: AnalyticsHHGroup }
  rejection_by_status: Array<{ status: string; label: string; count: number }>
  company_sync: { total: number; pending: number; done: number; failed: number }
  stage_conversions: AnalyticsStageConversion[]
  bottleneck: AnalyticsStageConversion | null
  by_company_type: AnalyticsSuccessGroup[]
  by_employee_range: AnalyticsSuccessGroup[]
  by_role_category: AnalyticsSuccessGroup[]
}

export interface CompanySyncStatus {
  running: boolean
  current_company: string | null
  pending: number
  done: number
  failed: number
  profiles: Array<{
    id: number
    name_display: string | null
    sync_status: string
    sync_error: string | null
    last_synced_at: string | null
  }>
}
