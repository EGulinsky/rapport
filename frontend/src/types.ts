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
  is_headhunter: boolean
  zielfirma_bei_hh?: string
  quelle?: string
  wurde_besetzt_von?: string
  datum_bewerbung?: string
  letztes_update?: string
  naechster_schritt?: string
  abgesagt: boolean
  ghosting: boolean
  kommentar?: string
  gespraech_1?: string
  gespraech_2?: string
  gespraech_3?: string
  gespraech_4?: string
  gespraech_5?: string
  contacts?: Contact[]
  events?: Event[]
}

export interface Contact {
  id: number
  name: string
  email?: string
  telefon?: string
  linkedin_url?: string
  firma?: string
  rolle?: string
  typ?: string
  notizen?: string
  letzter_kontakt?: string
}

export interface ContactWithApp extends Contact {
  applications?: { id: number; firma: string; rolle: string }[]
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

export interface CleanupPreview {
  applications: AppGroup[]
  contacts: ContactGroup[]
  events: EventGroup[]
}

export interface CleanupResult {
  deleted_applications: number
  deleted_contacts: number
  deleted_events: number
  merged_app_groups: number
  merged_contact_groups: number
  merged_event_groups: number
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
}

export interface FilesConfig {
  folder_path?: string
  enabled: boolean
  last_sync?: string
  bridge_reachable?: boolean
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

export interface LinkedInSyncStatus {
  status: 'idle' | 'running' | 'done' | 'error' | 'needs_login' | 'needs_2fa'
  step: string
  processed: number
  created: number
  updated: number
  skipped: number
  errors: string[]
  log: LinkedInSyncLogEntry[]
  started_at: string | null
  finished_at: string | null
}
