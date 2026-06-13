import type { Application, Contact, ContactWithApp, Event, Stats, ImportResult, AiSettings, AiSettingsWrite, GoogleSyncStatus, SyncResult, PendingMatch, ICloudSyncStatus, CallsStatus, CleanupPreview, CleanupResult, LinkedInSyncStatus } from '../types'

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
  },

  settings: {
    getAi: () => request<AiSettings>('/settings/ai'),
    saveAi: (data: AiSettingsWrite) => request<AiSettings>('/settings/ai', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
    clearAiKey: () => request<AiSettings>('/settings/ai/key', { method: 'DELETE' }),
    testAi: (data?: AiSettingsWrite) => request<{ status: string; message: string }>('/settings/ai/test', {
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
    }),
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
}
