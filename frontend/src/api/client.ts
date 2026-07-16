import type { Application, Contact, ContactWithApp, Event, Stats, ImportResult, AiSettings, AiSettingsWrite, MapsSettings, AgentSettings, AgentHealth, GoogleSyncStatus, SyncResult, PendingMatch, ICloudSyncStatus, CallsStatus, CleanupPreview, CleanupResult, CleanupScope, LinkedInSyncStatus, CalendarEvent, SyncSettings, FilesConfig, ManualCandidate, MergeRequest, MergeResult, AuditLogResponse, FileBrowseResult, BackupStatus, AnalyticsSummary, CompanyProfile } from '../types'

const BASE = '/api'

// ── Auth token storage + fetch wrapper ──────────────────────────────────────
const TOKEN_KEY = 'rapport_auth_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

/** Dispatched on any 401 response (except calls opting out via skipAuthHandling) so
 * AuthContext can clear its user state — the actual redirect happens via route guards. */
export const AUTH_UNAUTHORIZED_EVENT = 'rapport:unauthorized'

interface AuthFetchOptions extends RequestInit {
  /** Skip the automatic token-clear + logout-event on 401. Use for endpoints where
   * a 401 means "wrong input" (e.g. change-password's old_password), not "session expired". */
  skipAuthHandling?: boolean
}

export async function authFetch(url: string, options?: AuthFetchOptions): Promise<Response> {
  const { skipAuthHandling, ...init } = options ?? {}
  const token = getToken()
  const headers = new Headers(init.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const res = await fetch(url, { ...init, headers })
  if (res.status === 401 && !skipAuthHandling) {
    setToken(null)
    window.dispatchEvent(new Event(AUTH_UNAUTHORIZED_EVENT))
  }
  return res
}

/** Thrown by request() on a non-ok response. `errorKey` is set when the backend
 * sent a stable `detail.error_key` (see backend/app/error_keys.py) — callers can
 * look it up in the `errors` i18n namespace (`t(\`errors:${errorKey}\`)`) instead
 * of displaying `message` (the German fallback prose) directly. */
export class ApiError extends Error {
  errorKey: string | null
  constructor(message: string, errorKey: string | null = null) {
    super(message)
    this.name = 'ApiError'
    this.errorKey = errorKey
  }
}

async function request<T>(path: string, options?: AuthFetchOptions): Promise<T> {
  const headers = new Headers({ 'Content-Type': 'application/json' })
  if (options?.headers) new Headers(options.headers).forEach((v, k) => headers.set(k, v))
  const res = await authFetch(`${BASE}${path}`, { ...options, headers })
  if (!res.ok) {
    const raw = await res.text()
    let message = raw
    let errorKey: string | null = null
    try {
      const parsed = JSON.parse(raw)
      if (typeof parsed?.detail === 'string') message = parsed.detail
      else if (parsed?.detail && typeof parsed.detail === 'object') {
        if (typeof parsed.detail.message === 'string') message = parsed.detail.message
        if (typeof parsed.detail.error_key === 'string') errorKey = parsed.detail.error_key
      }
    } catch { /* not JSON — keep raw text */ }
    throw new ApiError(message || `${res.status}`, errorKey)
  }
  return res.json()
}

// ── Applications ─────────────────────────────────────────────────────────
export const api = {
  applications: {
    list: (params?: { main_status?: string; search?: string; show_rejected?: boolean }) => {
      const qs = new URLSearchParams()
      if (params?.main_status) qs.set('main_status', params.main_status)
      if (params?.search) qs.set('search', params.search)
      if (params?.show_rejected !== undefined) qs.set('show_rejected', String(params.show_rejected))
      return request<Application[]>(`/applications/?${qs}`)
    },

    get: (id: number) => request<Application>(`/applications/${id}`),

    create: (data: Partial<Application> & { created_from_linkedin?: boolean }) =>
      request<Application>('/applications/', {
        method: 'POST',
        body: JSON.stringify(data),
      }),

    update: (id: number, data: Partial<Application>) =>
      request<Application>(`/applications/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),

    delete: (id: number) =>
      authFetch(`${BASE}/applications/${id}`, { method: 'DELETE' }),

    stats: () => request<Stats>('/applications/stats'),

    aiAssess: (id: number) =>
      request<{ color: string; reasoning: string; next_step: string }>(`/applications/${id}/ai-assess`, { method: 'POST' }),
    aiAssessAllUrl: () => `${BASE}/applications/ai-assess-all`,
    extractFromLinkedInUrl: (url: string) =>
      request<{ firma: string; rolle: string; quelle: string; is_headhunter: boolean; zielfirma_bei_hh: string | null; kommentar: string | null; stellenanzeige_url: string; company_profile_id: number | null }>(
        '/applications/extract-from-linkedin-url',
        { method: 'POST', body: JSON.stringify({ url }) }
      ),

    deleteEvent: (appId: number, eventId: number) =>
      authFetch(`${BASE}/applications/${appId}/events/${eventId}`, { method: 'DELETE' }).then(r => {
        if (!r.ok) throw new Error(`${r.status}`)
      }),
    bulkDeleteEvents: (appId: number, ids: number[]) =>
      request<{ deleted: number }>(`/applications/${appId}/events/bulk`, {
        method: 'DELETE',
        body: JSON.stringify({ ids }),
      }),
    bulkDeleteContacts: (appId: number, ids: number[]) =>
      request<{ deleted: number }>(`/applications/${appId}/contacts/bulk`, {
        method: 'DELETE',
        body: JSON.stringify({ ids }),
      }),
    updateEvent: (appId: number, eventId: number, data: { typ?: string; datum?: string; titel?: string; notiz?: string }) =>
      request<Event>(`/applications/${appId}/events/${eventId}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    addEvent: (id: number, data: { typ: string; datum?: string; titel?: string; notiz?: string }) =>
      request<Event>(`/applications/${id}/events`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
  },

  contacts: {
    listAll: (search?: string) => {
      const qs = search ? `?search=${encodeURIComponent(search)}` : ''
      return request<ContactWithApp[]>(`/contacts/${qs}`)
    },

    add: (appId: number, data: Partial<Contact>) =>
      request<Contact>(`/applications/${appId}/contacts`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),

    link: (appId: number, contactId: number) =>
      request<Contact>(`/applications/${appId}/contacts/${contactId}`, { method: 'PUT' }),

    update: (appId: number, contactId: number, data: Partial<Contact>) =>
      request<Contact>(`/applications/${appId}/contacts/${contactId}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),

    delete: (appId: number, contactId: number) =>
      authFetch(`${BASE}/applications/${appId}/contacts/${contactId}`, { method: 'DELETE' }),

    bulkDelete: (ids: number[], all = false) =>
      request<{ deleted: number }>('/contacts/bulk', {
        method: 'DELETE',
        body: JSON.stringify({ ids, all }),
      }),

    patch: (id: number, data: Partial<Contact> & { company_profile_id?: number | null }) =>
      request<{ ok: boolean }>(`/contacts/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),

    create: (data: { name: string; vorname?: string; email?: string; telefon?: string; firma?: string; company_profile_id?: number; rolle?: string; typ?: string; linkedin_url?: string }) =>
      request<{ id: number; name: string; firma: string | null; company_profile_id: number | null }>('/contacts/', {
        method: 'POST',
        body: JSON.stringify(data),
      }),

    searchICloud: (q: string) =>
      request<import('../types').ICloudContactCandidate[]>(`/sync/icloud/contacts/search?q=${encodeURIComponent(q)}`),
    importFromICloud: (candidates: import('../types').ICloudContactCandidate[], applicationId?: number) =>
      request<{ imported: number; skipped: number }>('/sync/icloud/contacts/import', {
        method: 'POST',
        body: JSON.stringify({ candidates, application_id: applicationId }),
      }),

    searchLinkedIn: (q: string) =>
      request<import('../types').LinkedInPeopleCandidate[]>(`/sync/linkedin/people/search?q=${encodeURIComponent(q)}`),
    importFromLinkedIn: (candidates: import('../types').LinkedInPeopleCandidate[], applicationId?: number) =>
      request<{ imported: number; skipped: number }>('/sync/linkedin/people/import', {
        method: 'POST',
        body: JSON.stringify({ candidates, application_id: applicationId }),
      }),
  },

  export: {
    excel: async (showRejected = true): Promise<void> => {
      const qs = `?show_rejected=${showRejected}`
      const res = await authFetch(`${BASE}/export/excel${qs}`)
      if (!res.ok) throw new Error(await res.text())
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const disposition = res.headers.get('Content-Disposition') ?? ''
      const match = disposition.match(/filename="([^"]+)"/)
      a.download = match?.[1] ?? 'rapport_export.xlsx'
      a.click()
      URL.revokeObjectURL(url)
    },
    pdf: async (since?: string): Promise<void> => {
      const qs = since ? `?since=${since}` : ''
      const res = await authFetch(`${BASE}/export/pdf${qs}`)
      if (!res.ok) throw new Error(await res.text())
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const disposition = res.headers.get('Content-Disposition') ?? ''
      const match = disposition.match(/filename="([^"]+)"/)
      a.download = match?.[1] ?? 'Eigenbemühungen.pdf'
      a.click()
      URL.revokeObjectURL(url)
    },
  },

  settings: {
    getAi: () => request<AiSettings>('/settings/ai'),
    saveAi: (data: AiSettingsWrite) => request<AiSettings>('/settings/ai', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
    clearAiKey: () => request<AiSettings>('/settings/ai/key', { method: 'DELETE' }),
    listOllamaModels: (baseUrl: string) =>
      request<{ reachable: boolean; installed: string[]; popular: Array<{ name: string; display: string; params: string; size_gb: number }> }>(
        `/settings/ollama/models?base_url=${encodeURIComponent(baseUrl)}`
      ),
    pullOllamaModel: (model: string, baseUrl: string) =>
      `${BASE}/settings/ollama/pull?model=${encodeURIComponent(model)}&base_url=${encodeURIComponent(baseUrl)}`,
    testAi: (data?: AiSettingsWrite) => request<{ status: string; message: string }>('/settings/ai/test', {
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
    }),
    getLogo: () => request<{ api_key: string | null }>('/settings/logo'),
    saveLogo: (api_key: string | null) => request<{ api_key: string | null }>('/settings/logo', {
      method: 'POST',
      body: JSON.stringify({ api_key }),
    }),
    getMaps: () => request<MapsSettings>('/settings/maps'),
    saveMaps: (api_key: string | null) => request<MapsSettings>('/settings/maps', {
      method: 'POST',
      body: JSON.stringify({ api_key }),
    }),
    clearMapsKey: () => request<MapsSettings>('/settings/maps/key', { method: 'DELETE' }),
    getAgent: () => request<AgentSettings>('/settings/agent'),
    saveAgent: (data: { url?: string | null; token?: string | null }) => request<AgentSettings>('/settings/agent', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
    clearAgentToken: () => request<AgentSettings>('/settings/agent/token', { method: 'DELETE' }),
    getAgentHealth: () => request<AgentHealth>('/settings/agent/health'),
    getSync: () => request<SyncSettings>('/settings/sync'),
    saveSync: (data: Partial<SyncSettings>) => request<SyncSettings>('/settings/sync', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
    getFiles: () => request<FilesConfig>('/settings/files'),
    saveFiles: (data: Partial<FilesConfig>) => request<FilesConfig>('/settings/files', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  },

  files: {
    status: () => request<FilesConfig>('/sync/files/status'),
    sync: () => request<SyncResult>('/sync/files', { method: 'POST' }),
    reset: () => authFetch(`${BASE}/sync/files/reset`, { method: 'POST' }),
    browse: (path?: string) => {
      const qs = path ? `?path=${encodeURIComponent(path)}` : ''
      return request<FileBrowseResult>(`/sync/files/browse${qs}`)
    },
    attach: (appId: number, path: string, name: string, isFolder = false) =>
      request<{ event_id?: number; created: number; titel: string }>('/sync/files/attach', {
        method: 'POST',
        body: JSON.stringify({ app_id: appId, path, name, is_folder: isFolder }),
      }),
    openFile: (path: string) =>
      request<{ success: boolean }>('/sync/files/open', {
        method: 'POST',
        body: JSON.stringify({ path }),
      }),
  },

  schedule: {
    status: () => request<{ interval_minutes: number; running_sources: string[] }>('/sync/schedule/status'),
  },

  sync: {
    progress: () => request<Record<string, { label: string; step: string; current: number; total: number; percent: number; done: boolean }>>('/sync/google/progress'),
    batchResults: () => request<Record<string, { done: boolean; processed?: number; created?: number; skipped?: number; errors?: string[] }>>('/sync/google/batch/results'),
    googleStatus: () => request<GoogleSyncStatus>('/sync/google/status'),
    googleSaveCredentials: (data: { client_id: string; client_secret: string }) =>
      request<GoogleSyncStatus>('/sync/google/credentials', { method: 'POST', body: JSON.stringify(data) }),
    googleAuthUrl: () => request<{ url: string }>('/sync/google/auth'),
    googleDisconnect: () => authFetch(`${BASE}/sync/google`, { method: 'DELETE' }),
    resetGmailSync: () => authFetch(`${BASE}/sync/google/gmail/reset`, { method: 'POST' }),
    resetCalendarSync: () => authFetch(`${BASE}/sync/google/calendar/reset`, { method: 'POST' }),
    syncGmail: () => request<SyncResult>('/sync/google/gmail', { method: 'POST' }),
    syncCalendar: () => request<SyncResult>('/sync/google/calendar', { method: 'POST' }),
  },

  icloud: {
    status: () => request<ICloudSyncStatus>('/sync/icloud/status'),
    saveCredentials: (data: { apple_id: string; app_password: string; icloud_email?: string; web_password?: string }) =>
      request<ICloudSyncStatus>('/sync/icloud/credentials', { method: 'POST', body: JSON.stringify(data) }),
    test: () => request<{ status: string; message: string }>('/sync/icloud/test', { method: 'POST' }),
    disconnect: () => authFetch(`${BASE}/sync/icloud`, { method: 'DELETE' }),
    syncMail: () => request<SyncResult>('/sync/icloud/mail', { method: 'POST' }),
    resetMail: () => authFetch(`${BASE}/sync/icloud/mail/reset`, { method: 'POST' }),
    syncCalendar: () => request<SyncResult>('/sync/icloud/calendar', { method: 'POST' }),
    resetCalendar: () => authFetch(`${BASE}/sync/icloud/calendar/reset`, { method: 'POST' }),
    syncReminders: () => request<SyncResult>('/sync/icloud/reminders', { method: 'POST' }),
    resetReminders: () => authFetch(`${BASE}/sync/icloud/reminders/reset`, { method: 'POST' }),
    syncContacts: () => request<SyncResult>('/sync/icloud/contacts', { method: 'POST' }),
    syncNotes: () => request<SyncResult>('/sync/icloud/notes', { method: 'POST' }),
    resetNotes: () => authFetch(`${BASE}/sync/icloud/notes/reset`, { method: 'POST' }),
    verify2fa: (code: string) => request<SyncResult>('/sync/icloud/notes/verify-2fa', { method: 'POST', body: JSON.stringify({ code }) }),
    saveWebPassword: (password: string) => authFetch(`${BASE}/sync/icloud/web-password`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code: password }) }),
    syncCalls: () => request<SyncResult>('/sync/icloud/calls', { method: 'POST' }),
    resetCalls: () => authFetch(`${BASE}/sync/icloud/calls/reset`, { method: 'POST' }),
    callsStatus: () => request<CallsStatus>('/sync/icloud/calls/status'),
    callsSettings: (enabled: boolean) => request<CallsStatus>('/sync/icloud/calls/settings', {
      method: 'POST',
      body: JSON.stringify({ enabled }),
    }),
  },

  targeted: {
    syncForApp: (appId: number) => request<SyncResult>(`/sync/targeted/${appId}`, { method: 'POST' }),
    resetForApp: (appId: number) => request<{ deleted_events: number; deleted_items: number }>(`/sync/targeted/${appId}/reset`, { method: 'POST' }),
    getResult: (appId: number) => request<{ done: boolean; created?: number; processed?: number; errors?: string[] }>(`/sync/targeted/${appId}/result`),
    candidates: (appId: number, q?: string) => request<ManualCandidate[]>(`/sync/targeted/${appId}/candidates${q ? `?q=${encodeURIComponent(q)}` : ''}`),
    assign: (appId: number, data: { match_id: number; external_id?: string; source?: string; event_type?: string; datum?: string; titel?: string; remove_from_other?: boolean }) =>
      request<{ conflict: boolean; conflict_app_id?: number; conflict_app_firma?: string; conflict_event_id?: number; event_id?: number }>(`/sync/targeted/${appId}/assign`, { method: 'POST', body: JSON.stringify(data) }),
  },

  review: {
    count: () => request<{ count: number }>('/review/count'),
    list: () => request<PendingMatch[]>('/review/'),
    approve: (id: number, data: { application_id?: number; event_type?: string; datum?: string; titel?: string; linkedin_url?: string }) =>
      request<{ status: string; event_id: number }>(`/review/${id}/approve`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    reject: (id: number) => authFetch(`${BASE}/review/${id}`, { method: 'DELETE' }),
  },

  cleanup: {
    preview: (scope?: CleanupScope) => request<CleanupPreview>(`/cleanup/preview${scope ? `?scope=${scope}` : ''}`),
    run: (scope?: CleanupScope) => request<CleanupResult>(`/cleanup/run${scope ? `?scope=${scope}` : ''}`, { method: 'POST' }),
    progress: () => request<Record<string, { label: string; step: string; current: number; total: number; percent: number; done: boolean }>>('/cleanup/progress'),
  },

  linkedin: {
    getConfig: () => request<{ configured: boolean; email?: string; has_session: boolean; last_sync?: string }>('/sync/linkedin/config'),
    saveConfig: (email: string, password: string) =>
      request('/sync/linkedin/config', { method: 'POST', body: JSON.stringify({ email, password }) }),
    deleteConfig: () => request('/sync/linkedin/config', { method: 'DELETE' }),
    run: (targetAppId?: number) => request('/sync/linkedin/run', { method: 'POST', body: JSON.stringify({ target_app_id: targetAppId ?? null }) }),
    status: () => request<LinkedInSyncStatus>('/sync/linkedin/status'),
    clearSession: () => request('/sync/linkedin/clear-session', { method: 'POST' }),
    submitTwoFa: (code: string) => request('/sync/linkedin/submit-2fa', { method: 'POST', body: JSON.stringify({ code }) }),
    // Scrapes and caches the account's own LinkedIn profile text (headline/
    // about/experience) — fed into the AI assessment prompt alongside the
    // CV. Reuses the existing LinkedIn session cookies (getConfig/saveConfig
    // above), not a separate login.
    syncOwnProfile: () => request<{ synced_at: string; chars: number }>('/sync/linkedin/profile', { method: 'POST' }),
  },

  attachments: {
    // Kein direkter <a href>-Link mehr möglich, da der Download jetzt einen
    // Authorization-Header braucht (Browser-Navigation kann keine Header
    // mitschicken) — stattdessen Blob laden und Download programmatisch
    // auslösen, analog zu export.excel/export.pdf.
    download: async (id: number, filename: string): Promise<void> => {
      const res = await authFetch(`${BASE}/attachments/${id}/download`)
      if (!res.ok) throw new Error(await res.text())
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
    },
    upload: async (eventId: number, file: File): Promise<{ id: number; filename: string; size_bytes: number }> => {
      const form = new FormData()
      form.append('file', file)
      const res = await authFetch(`${BASE}/attachments/${eventId}/upload`, { method: 'POST', body: form })
      if (!res.ok) throw new Error(await res.text())
      return res.json()
    },
    delete: (id: number) => request<void>(`/attachments/${id}`, { method: 'DELETE' }),
  },

  calendar: {
    events: (from?: string, to?: string) => {
      const qs = new URLSearchParams()
      if (from) qs.set('from_date', from)
      if (to) qs.set('to_date', to)
      return request<CalendarEvent[]>(`/calendar/events?${qs}`)
    },
  },

  import: {
    excel: async (file: File): Promise<ImportResult> => {
      const form = new FormData()
      form.append('file', file)
      const res = await authFetch(`${BASE}/import/excel`, { method: 'POST', body: form })
      if (!res.ok) throw new Error(await res.text())
      return res.json()
    },
  },

  merge: {
    applications: (req: MergeRequest) =>
      request<MergeResult>('/merge/applications', {
        method: 'POST',
        body: JSON.stringify(req),
      }),
    contacts: (req: MergeRequest) =>
      request<MergeResult>('/merge/contacts', {
        method: 'POST',
        body: JSON.stringify(req),
      }),
    companies: (req: { winner_id: number; loser_ids: number[]; field_overrides?: Record<string, number> }) =>
      request<MergeResult>('/merge/companies', {
        method: 'POST',
        body: JSON.stringify(req),
      }),
  },

  backup: {
    status: () => request<BackupStatus>('/backup/status'),
    saveSettings: (data: { enabled: boolean; backup_folder?: string; frequency_hours: number; keep_count: number }) =>
      request<BackupStatus>('/backup/settings', { method: 'POST', body: JSON.stringify(data) }),
    run: () => request<{ success: boolean; filename: string }>('/backup/run', { method: 'POST' }),
    pickFolder: () => request<{ path: string }>('/backup/pick-folder'),
    restore: (filename: string, folder: string) => request<{ success: boolean; filename: string }>('/backup/restore', { method: 'POST', body: JSON.stringify({ filename, folder }) }),
    pickFile: () => request<{ path: string }>('/backup/pick-file'),
    restoreFromFile: (path: string) => request<{ success: boolean; filename: string }>('/backup/restore-file', { method: 'POST', body: JSON.stringify({ path }) }),
  },

  analytics: {
    summary: () => request<AnalyticsSummary>('/analytics/summary'),
  },

  companySync: {
    status: () => request<import('../types').CompanySyncStatus>('/sync/company/status'),
    run: (force = false, companyIds?: number[]) => {
      const qs = new URLSearchParams()
      if (force) qs.set('force', 'true')
      for (const id of companyIds ?? []) qs.append('company_ids', String(id))
      const s = qs.toString()
      return request<{ started: boolean; count: number; message?: string }>(`/sync/company/run${s ? '?' + s : ''}`, { method: 'POST' })
    },
    cancel: () => request<{ ok: boolean }>('/sync/company/cancel', { method: 'POST' }),
    resetLock: () => request<{ ok: boolean }>('/sync/company/reset-lock', { method: 'POST' }),
    resetFailed: () => request<{ reset: number }>('/sync/company/reset-failed', { method: 'POST' }),
  },

  audit: {
    list: (params?: { app_id?: number; contact_id?: number; company_profile_id?: number; event_id?: number; entity_type?: string; limit?: number; offset?: number }) => {
      const qs = params ? '?' + new URLSearchParams(
        Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined).map(([k, v]) => [k, String(v)]))
      ).toString() : ''
      return request<AuditLogResponse>(`/audit/${qs}`)
    },
    clear: () => authFetch(`${BASE}/audit/`, { method: 'DELETE' }).then(r => r.json()),
  },

  companies: {
    list: (params?: { search?: string; sort?: string; order?: string }) =>
      request<CompanyProfile[]>(`/companies${params ? '?' + new URLSearchParams(Object.entries(params).filter(([, v]) => v != null) as [string, string][]).toString() : ''}`),
    get: (id: number) => request<CompanyProfile>(`/companies/${id}`),
    update: (id: number, data: Partial<CompanyProfile>) =>
      request<CompanyProfile>(`/companies/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    create: (name: string) => request<CompanyProfile>('/companies', { method: 'POST', body: JSON.stringify({ name }) }),
    linkContacts: (companyIds?: number[]) => {
      const qs = new URLSearchParams()
      for (const id of companyIds ?? []) qs.append('company_ids', String(id))
      const s = qs.toString()
      return request<{started: boolean; total?: number; message?: string}>(`/companies/link-contacts${s ? '?' + s : ''}`, {method: 'POST'})
    },
    linkContactsStatus: () => request<{running: boolean; linked: number; created: number; total: number; done: boolean; cancelled: boolean}>('/companies/link-contacts/status'),
    linkContactsCancel: () => request<{ok: boolean}>('/companies/link-contacts/cancel', {method: 'POST'}),
    uploadLogo: async (id: number, file: File): Promise<void> => {
      const form = new FormData()
      form.append('file', file)
      await authFetch(`/api/companies/${id}/logo`, {method: 'POST', body: form})
    },
    deleteLogo: (id: number) => request<{ok: boolean}>(`/companies/${id}/logo`, {method: 'DELETE'}),
    assignContact: (companyId: number, contactId: number) =>
      request<{ok: boolean}>(`/companies/${companyId}/contacts/${contactId}`, {method: 'POST'}),
    unassignContact: (companyId: number, contactId: number) =>
      request<{ok: boolean}>(`/companies/${companyId}/contacts/${contactId}`, {method: 'DELETE'}),
    bulkDelete: (ids: number[]) =>
      request<{ deleted: number }>('/companies/bulk', { method: 'DELETE', body: JSON.stringify({ ids }) }),

    searchLinkedIn: (q: string) =>
      request<import('../types').LinkedInCompanyCandidate[]>(`/sync/linkedin/companies/search?q=${encodeURIComponent(q)}`),
    importFromLinkedIn: (candidates: import('../types').LinkedInCompanyCandidate[]) =>
      request<{ imported: number; skipped: number }>('/sync/linkedin/companies/import', {
        method: 'POST',
        body: JSON.stringify({ candidates }),
      }),
  },

  startup: {
    check: () => request<{ checks: StartupCheck[]; all_ok: boolean; errors: StartupCheck[] }>('/startup-check'),
  },

  geo: {
    search: (q: string) => request<{ label: string }[]>(`/geo/search?q=${encodeURIComponent(q)}`),
  },

  auth: {
    register: (email: string, password: string, ui_language: string = 'en') =>
      request<{ message: string }>('/auth/register', {
        method: 'POST', body: JSON.stringify({ email, password, ui_language }),
      }),
    verifyEmail: (email: string, code: string) =>
      request<AuthTokenResponse>('/auth/verify-email', {
        method: 'POST', body: JSON.stringify({ email, code }),
      }),
    resendCode: (email: string) =>
      request<{ message: string }>('/auth/resend-code', {
        method: 'POST', body: JSON.stringify({ email }),
      }),
    login: (email: string, password: string) =>
      request<AuthTokenResponse>('/auth/login', {
        method: 'POST', body: JSON.stringify({ email, password }),
      }),
    forgotPassword: (email: string) =>
      request<{ message: string }>('/auth/forgot-password', {
        method: 'POST', body: JSON.stringify({ email }),
      }),
    resetPassword: (email: string, code: string, new_password: string) =>
      request<{ message: string }>('/auth/reset-password', {
        method: 'POST', body: JSON.stringify({ email, code, new_password }),
      }),
    me: () => request<AuthUser>('/auth/me'),
    changePassword: (old_password: string, new_password: string) =>
      request<{ message: string }>('/auth/change-password', {
        method: 'POST', body: JSON.stringify({ old_password, new_password }),
        skipAuthHandling: true, // 401 hier heißt "altes Passwort falsch", nicht "Session abgelaufen"
      }),
    updateProfile: (vorname: string, nachname: string, linkedin_url: string, ui_language?: string) =>
      request<AuthUser>('/auth/profile', {
        method: 'PATCH', body: JSON.stringify({ vorname, nachname, linkedin_url, ui_language }),
      }),
    uploadCv: async (file: File): Promise<AuthUser> => {
      const form = new FormData()
      form.append('file', file)
      const res = await authFetch(`${BASE}/auth/cv`, { method: 'POST', body: form })
      if (!res.ok) throw new Error(await res.text())
      return res.json()
    },
    downloadCv: async (filename: string): Promise<void> => {
      const res = await authFetch(`${BASE}/auth/cv`)
      if (!res.ok) throw new Error(await res.text())
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
    },
    deleteCv: () => request<void>('/auth/cv', { method: 'DELETE' }),
  },
}

export interface AuthTokenResponse {
  access_token: string
  token_type: string
}

export interface AuthUser {
  id: number
  email: string
  email_verified: boolean
  vorname: string | null
  nachname: string | null
  linkedin_url: string | null
  cv_filename: string | null
  cv_size_bytes: number | null
  linkedin_profile_synced_at: string | null
  ui_language: string
}

export interface StartupCheck {
  name: string
  group: 'bridges' | 'connections'
  ok: boolean
  message: string | null
}
