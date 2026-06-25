import type { Application, Contact, ContactWithApp, Event, Stats, ImportResult, AiSettings, AiSettingsWrite, GoogleSyncStatus, SyncResult, PendingMatch, ICloudSyncStatus, CallsStatus, CleanupPreview, CleanupResult, LinkedInSyncStatus, CalendarEvent, SyncSettings, FilesConfig, ManualCandidate, MergeRequest, MergeResult, AuditLogResponse, FileBrowseResult, BackupStatus, AnalyticsSummary } from '../types'

const BASE = '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(`${res.status}: ${err}`)
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

    create: (data: Partial<Application>) =>
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
      fetch(`${BASE}/applications/${id}`, { method: 'DELETE' }),

    stats: () => request<Stats>('/applications/stats'),

    deleteEvent: (appId: number, eventId: number) =>
      fetch(`${BASE}/applications/${appId}/events/${eventId}`, { method: 'DELETE' }).then(r => {
        if (!r.ok) throw new Error(`${r.status}`)
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

    update: (appId: number, contactId: number, data: Partial<Contact>) =>
      request<Contact>(`/applications/${appId}/contacts/${contactId}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),

    delete: (appId: number, contactId: number) =>
      fetch(`${BASE}/applications/${appId}/contacts/${contactId}`, { method: 'DELETE' }),

    bulkDelete: (ids: number[], all = false) =>
      request<{ deleted: number }>('/contacts/bulk', {
        method: 'DELETE',
        body: JSON.stringify({ ids, all }),
      }),
  },

  export: {
    excel: async (showRejected = true): Promise<void> => {
      const qs = `?show_rejected=${showRejected}`
      const res = await fetch(`${BASE}/export/excel${qs}`)
      if (!res.ok) throw new Error(await res.text())
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const disposition = res.headers.get('Content-Disposition') ?? ''
      const match = disposition.match(/filename="([^"]+)"/)
      a.download = match?.[1] ?? 'jobtracker_export.xlsx'
      a.click()
      URL.revokeObjectURL(url)
    },
    linkedinDebugExcel: async (): Promise<void> => {
      const res = await fetch(`${BASE}/sync/linkedin/debug-excel`)
      if (!res.ok) throw new Error(await res.text())
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const disposition = res.headers.get('Content-Disposition') ?? ''
      const match = disposition.match(/filename="([^"]+)"/)
      a.download = match?.[1] ?? 'linkedin_sync_debug.xlsx'
      a.click()
      URL.revokeObjectURL(url)
    },
    pdf: async (since?: string): Promise<void> => {
      const qs = since ? `?since=${since}` : ''
      const res = await fetch(`${BASE}/export/pdf${qs}`)
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
    reset: () => fetch(`${BASE}/sync/files/reset`, { method: 'POST' }),
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
    googleDisconnect: () => fetch(`${BASE}/sync/google`, { method: 'DELETE' }),
    resetGmailSync: () => fetch(`${BASE}/sync/google/gmail/reset`, { method: 'POST' }),
    resetCalendarSync: () => fetch(`${BASE}/sync/google/calendar/reset`, { method: 'POST' }),
    syncGmail: () => request<SyncResult>('/sync/google/gmail', { method: 'POST' }),
    syncCalendar: () => request<SyncResult>('/sync/google/calendar', { method: 'POST' }),
  },

  icloud: {
    status: () => request<ICloudSyncStatus>('/sync/icloud/status'),
    saveCredentials: (data: { apple_id: string; app_password: string; icloud_email?: string; web_password?: string }) =>
      request<ICloudSyncStatus>('/sync/icloud/credentials', { method: 'POST', body: JSON.stringify(data) }),
    test: () => request<{ status: string; message: string }>('/sync/icloud/test', { method: 'POST' }),
    disconnect: () => fetch(`${BASE}/sync/icloud`, { method: 'DELETE' }),
    syncMail: () => request<SyncResult>('/sync/icloud/mail', { method: 'POST' }),
    resetMail: () => fetch(`${BASE}/sync/icloud/mail/reset`, { method: 'POST' }),
    syncCalendar: () => request<SyncResult>('/sync/icloud/calendar', { method: 'POST' }),
    resetCalendar: () => fetch(`${BASE}/sync/icloud/calendar/reset`, { method: 'POST' }),
    syncReminders: () => request<SyncResult>('/sync/icloud/reminders', { method: 'POST' }),
    resetReminders: () => fetch(`${BASE}/sync/icloud/reminders/reset`, { method: 'POST' }),
    syncContacts: () => request<SyncResult>('/sync/icloud/contacts', { method: 'POST' }),
    syncNotes: () => request<SyncResult>('/sync/icloud/notes', { method: 'POST' }),
    resetNotes: () => fetch(`${BASE}/sync/icloud/notes/reset`, { method: 'POST' }),
    verify2fa: (code: string) => request<SyncResult>('/sync/icloud/notes/verify-2fa', { method: 'POST', body: JSON.stringify({ code }) }),
    saveWebPassword: (password: string) => fetch(`${BASE}/sync/icloud/web-password`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code: password }) }),
    syncCalls: () => request<SyncResult>('/sync/icloud/calls', { method: 'POST' }),
    resetCalls: () => fetch(`${BASE}/sync/icloud/calls/reset`, { method: 'POST' }),
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
    approve: (id: number, data: { application_id: number; event_type?: string; datum?: string; titel?: string }) =>
      request<{ status: string; event_id: number }>(`/review/${id}/approve`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    reject: (id: number) => fetch(`${BASE}/review/${id}`, { method: 'DELETE' }),
  },

  cleanup: {
    preview: () => request<CleanupPreview>('/cleanup/preview'),
    run: () => request<CleanupResult>('/cleanup/run', { method: 'POST' }),
    progress: () => request<Record<string, { label: string; step: string; current: number; total: number; percent: number; done: boolean }>>('/cleanup/progress'),
  },

  linkedin: {
    getConfig: () => request<{ configured: boolean; email?: string; has_session: boolean; last_sync?: string }>('/sync/linkedin/config'),
    saveConfig: (email: string, password: string) =>
      request('/sync/linkedin/config', { method: 'POST', body: JSON.stringify({ email, password }) }),
    deleteConfig: () => request('/sync/linkedin/config', { method: 'DELETE' }),
    run: () => request('/sync/linkedin/run', { method: 'POST' }),
    status: () => request<LinkedInSyncStatus>('/sync/linkedin/status'),
    clearSession: () => request('/sync/linkedin/clear-session', { method: 'POST' }),
    submitTwoFa: (code: string) => request('/sync/linkedin/submit-2fa', { method: 'POST', body: JSON.stringify({ code }) }),
  },

  attachments: {
    download: (id: number) => `${BASE}/attachments/${id}/download`,
    upload: async (eventId: number, file: File): Promise<{ id: number; filename: string; size_bytes: number }> => {
      const form = new FormData()
      form.append('file', file)
      const res = await fetch(`${BASE}/attachments/${eventId}/upload`, { method: 'POST', body: form })
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
      const res = await fetch(`${BASE}/import/excel`, { method: 'POST', body: form })
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
  },

  backup: {
    status: () => request<BackupStatus>('/backup/status'),
    saveSettings: (data: { enabled: boolean; backup_folder?: string; frequency_hours: number; keep_count: number }) =>
      request<BackupStatus>('/backup/settings', { method: 'POST', body: JSON.stringify(data) }),
    run: () => request<{ success: boolean; filename: string }>('/backup/run', { method: 'POST' }),
  },

  jobsearch: {
    portals: () => request<import('../types').JobPortal[]>('/jobsearch/portals'),
    addPortal: (data: { name: string; url_template?: string; color?: string; enabled?: boolean }) =>
      request<import('../types').JobPortal>('/jobsearch/portals', { method: 'POST', body: JSON.stringify(data) }),
    updatePortal: (id: number, data: Partial<{ name: string; url_template: string; color: string; enabled: boolean; sort_order: number }>) =>
      request<import('../types').JobPortal>(`/jobsearch/portals/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    deletePortal: (id: number) => fetch(`${BASE}/jobsearch/portals/${id}`, { method: 'DELETE' }),
    search: (q: string, location: string) => {
      const qs = new URLSearchParams({ q, location })
      return request<import('../types').JobSearchResponse>(`/jobsearch/search?${qs}`)
    },
    importJobs: (jobs: import('../types').JobResult[]) =>
      request<{ created: number; skipped: number; ids: number[] }>('/jobsearch/import', {
        method: 'POST',
        body: JSON.stringify({ jobs }),
      }),
    description: (url: string) =>
      request<{ description: string }>(`/jobsearch/description?url=${encodeURIComponent(url)}`),
  },

  analytics: {
    summary: () => request<AnalyticsSummary>('/analytics/summary'),
  },

  companySync: {
    status: () => request<import('../types').CompanySyncStatus>('/sync/company/status'),
    run: () => request<{ started: boolean; count: number; message?: string }>('/sync/company/run', { method: 'POST' }),
    resetLock: () => request<{ ok: boolean }>('/sync/company/reset-lock', { method: 'POST' }),
    resetFailed: () => request<{ reset: number }>('/sync/company/reset-failed', { method: 'POST' }),
  },

  audit: {
    list: (params?: { app_id?: number; limit?: number; offset?: number }) => {
      const qs = params ? '?' + new URLSearchParams(
        Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined).map(([k, v]) => [k, String(v)]))
      ).toString() : ''
      return request<AuditLogResponse>(`/audit/${qs}`)
    },
    clear: () => fetch(`${BASE}/audit/`, { method: 'DELETE' }).then(r => r.json()),
  },
}
