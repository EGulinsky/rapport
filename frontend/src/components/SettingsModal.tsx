import { useState, useEffect, useRef } from 'react'
import { X, CheckCircle, XCircle, Loader, Eye, EyeOff, ExternalLink, RefreshCw, Unlink, Phone, Wifi, WifiOff, FolderOpen } from 'lucide-react'
import { api } from '../api/client'
import type { AiSettingsWrite, GoogleSyncStatus, SyncResult, ICloudSyncStatus, CallsStatus, SyncSettings, FilesConfig } from '../types'
import clsx from 'clsx'

interface Props { onClose: () => void }

// ── AI Provider config ────────────────────────────────────────────────────────
const PROVIDERS = [
  { id: 'groq',      name: 'Groq',            badge: 'kostenlos',     badgeColor: 'bg-green-100 text-green-700',   model: 'groq/llama-3.3-70b-versatile',       keyPh: 'gsk_…',     keyUrl: 'https://console.groq.com/keys',              needsUrl: false },
  { id: 'anthropic', name: 'Anthropic Claude', badge: 'kostenpflichtig', badgeColor: 'bg-orange-100 text-orange-700', model: 'anthropic/claude-haiku-4-5-20251001', keyPh: 'sk-ant-…', keyUrl: 'https://console.anthropic.com',               needsUrl: false },
  { id: 'openai',    name: 'OpenAI',           badge: 'kostenpflichtig', badgeColor: 'bg-orange-100 text-orange-700', model: 'gpt-4o-mini',                         keyPh: 'sk-…',      keyUrl: 'https://platform.openai.com/api-keys',        needsUrl: false },
  { id: 'gemini',    name: 'Google Gemini',    badge: 'kostenlos',     badgeColor: 'bg-green-100 text-green-700',   model: 'gemini/gemini-2.0-flash',             keyPh: 'AIza…',     keyUrl: 'https://aistudio.google.com/app/apikey',      needsUrl: false },
  { id: 'ollama',    name: 'Ollama',           badge: 'offline',       badgeColor: 'bg-yellow-100 text-yellow-700', model: 'ollama/llama3.2',                     keyPh: '',          keyUrl: 'https://ollama.com',                          needsUrl: true  },
] as const

// ── Google Sync Panel ─────────────────────────────────────────────────────────
function GoogleSyncPanel() {
  const [status, setStatus] = useState<GoogleSyncStatus | null>(null)
  const [creds, setCreds] = useState({ client_id: '', client_secret: '' })
  const [showSecret, setShowSecret] = useState(false)
  const [savingCreds, setSavingCreds] = useState(false)
  const [syncing, setSyncing] = useState<'gmail' | 'gcal' | null>(null)
  const [resetting, setResetting] = useState(false)
  const [lastResult, setLastResult] = useState<(SyncResult & { target: string }) | null>(null)
  const [error, setError] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    api.sync.googleStatus().then(setStatus)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [])

  useEffect(() => {
    const handler = (e: MessageEvent) => {
      if (e.data?.type === 'google_connected') {
        api.sync.googleStatus().then(setStatus)
      }
    }
    window.addEventListener('message', handler)
    return () => window.removeEventListener('message', handler)
  }, [])

  async function saveCreds() {
    if (!creds.client_id || !creds.client_secret) return
    setSavingCreds(true)
    try {
      const s = await api.sync.googleSaveCredentials(creds)
      setStatus(s)
      setCreds(c => ({ ...c, client_secret: '' }))
    } finally {
      setSavingCreds(false)
    }
  }

  function openOAuth() {
    api.sync.googleAuthUrl().then(({ url }) => {
      window.open(url, 'google_oauth', 'width=600,height=700,left=200,top=100')
    }).catch(e => setError(String(e)))
  }

  async function disconnect() {
    await api.sync.googleDisconnect()
    const s = await api.sync.googleStatus()
    setStatus(s)
  }

  async function resetAndSync() {
    setResetting(true)
    setError(null)
    setLastResult(null)
    try {
      await api.sync.resetGmailSync()
      const res = await api.sync.syncGmail()
      setLastResult({ ...res, target: 'gmail' })
      const s = await api.sync.googleStatus()
      setStatus(s)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setResetting(false)
    }
  }

  async function runSync(target: 'gmail' | 'gcal') {
    setSyncing(target)
    setError(null)
    setLastResult(null)
    try {
      const res = target === 'gmail'
        ? await api.sync.syncGmail()
        : await api.sync.syncCalendar()
      setLastResult({ ...res, target })
      const s = await api.sync.googleStatus()
      setStatus(s)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSyncing(null)
    }
  }

  const fmtDate = (d?: string) =>
    d ? new Date(d).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : 'noch nie'

  return (
    <div className="space-y-5">
      {/* Credentials */}
      <div>
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
          Google OAuth 2.0 Credentials
          <a href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noreferrer"
            className="ml-2 normal-case text-indigo-600 hover:underline inline-flex items-center gap-0.5">
            Cloud Console <ExternalLink className="h-3 w-3" />
          </a>
        </p>
        <p className="text-xs text-gray-400 mb-3">
          Projekt anlegen → APIs aktivieren (Gmail + Calendar) → OAuth-Client erstellen (Typ: Webanwendung)<br/>
          Autorisierte Redirect-URI: <code className="bg-gray-100 px-1 rounded">http://localhost:8000/api/sync/google/callback</code>
        </p>
        <div className="space-y-2">
          <input
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="Client ID"
            value={creds.client_id}
            onChange={e => setCreds(c => ({ ...c, client_id: e.target.value }))}
          />
          <div className="relative">
            <input
              type={showSecret ? 'text' : 'password'}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 pr-10 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder="Client Secret"
              value={creds.client_secret}
              onChange={e => setCreds(c => ({ ...c, client_secret: e.target.value }))}
            />
            <button type="button" onClick={() => setShowSecret(s => !s)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400">
              {showSecret ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
          <button onClick={saveCreds} disabled={savingCreds || !creds.client_id}
            className="rounded-lg bg-gray-800 px-4 py-2 text-xs font-medium text-white hover:bg-gray-700 disabled:opacity-50">
            {savingCreds ? 'Speichern…' : 'Credentials speichern'}
          </button>
        </div>
      </div>

      {/* Connect / status */}
      {status?.client_id && (
        <div className="rounded-xl border border-gray-200 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className={clsx('h-2.5 w-2.5 rounded-full', status.connected ? 'bg-green-500' : 'bg-gray-300')} />
              <span className="text-sm font-medium text-gray-800">
                {status.connected ? 'Verbunden' : 'Nicht verbunden'}
              </span>
            </div>
            {status.connected
              ? <button onClick={disconnect} className="flex items-center gap-1 text-xs text-red-500 hover:text-red-600">
                  <Unlink className="h-3.5 w-3.5" /> Trennen
                </button>
              : <button onClick={openOAuth}
                  className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700">
                  Mit Google verbinden
                </button>
            }
          </div>

          {status.connected && (
            <div className="grid grid-cols-2 gap-3">
              {/* Gmail */}
              <div className="rounded-lg bg-gray-50 border border-gray-100 p-3">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs font-semibold text-gray-700">Gmail</p>
                  <div className="flex gap-1">
                    <button onClick={() => runSync('gmail')} disabled={!!syncing || resetting}
                      className="flex items-center gap-1 rounded-md bg-white border border-gray-200 px-2 py-1 text-xs hover:bg-gray-50 disabled:opacity-50"
                      title="Neue Mails seit letztem Sync holen">
                      {syncing === 'gmail'
                        ? <Loader className="h-3 w-3 animate-spin" />
                        : <RefreshCw className="h-3 w-3" />}
                      Sync
                    </button>
                    <button onClick={resetAndSync} disabled={!!syncing || resetting}
                      className="flex items-center gap-1 rounded-md bg-amber-50 border border-amber-200 px-2 py-1 text-xs text-amber-700 hover:bg-amber-100 disabled:opacity-50"
                      title="Letzte 90 Tage erneut durchsuchen">
                      {resetting ? <Loader className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
                      Alles neu
                    </button>
                  </div>
                </div>
                <p className="text-xs text-gray-400">Letzter Sync: {fmtDate(status.gmail_last_sync)}</p>
              </div>

              {/* Calendar */}
              <div className="rounded-lg bg-gray-50 border border-gray-100 p-3">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs font-semibold text-gray-700">Kalender</p>
                  <button onClick={() => runSync('gcal')} disabled={!!syncing}
                    className="flex items-center gap-1 rounded-md bg-white border border-gray-200 px-2 py-1 text-xs hover:bg-gray-50 disabled:opacity-50">
                    {syncing === 'gcal'
                      ? <Loader className="h-3 w-3 animate-spin" />
                      : <RefreshCw className="h-3 w-3" />}
                    Sync
                  </button>
                </div>
                <p className="text-xs text-gray-400">Letzter Sync: {fmtDate(status.gcal_last_sync)}</p>
              </div>
            </div>
          )}

          {/* Sync result */}
          {lastResult && (
            <div className="rounded-lg bg-green-50 border border-green-200 p-3 text-xs text-green-800 space-y-1">
              <p className="font-semibold">{lastResult.target === 'gmail' ? 'Gmail' : 'Kalender'} Sync abgeschlossen</p>
              <p>{lastResult.processed} verarbeitet · {lastResult.created} Events erstellt · {lastResult.skipped} übersprungen</p>
              {lastResult.errors.length > 0 && (
                <p className="text-red-600">{lastResult.errors.slice(0, 3).join(' | ')}</p>
              )}
            </div>
          )}

          {error && (
            <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-200 p-3 text-xs text-red-700">
              <XCircle className="h-4 w-4 shrink-0 mt-0.5" />
              {error}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── AI Panel ──────────────────────────────────────────────────────────────────
function AiPanel() {
  const [form, setForm] = useState<AiSettingsWrite>({ provider: 'groq', model: 'groq/llama-3.3-70b-versatile', api_key: '', base_url: '', enabled: true })
  const [hasStoredKey, setHasStoredKey] = useState(false)
  const [showKey, setShowKey] = useState(false)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.settings.getAi().then(d => {
      setForm({ provider: d.provider, model: d.model, api_key: '', base_url: d.base_url ?? '', enabled: d.enabled })
      setHasStoredKey(d.has_key)
    }).finally(() => setLoading(false))
  }, [])

  const prov = PROVIDERS.find(p => p.id === form.provider) ?? PROVIDERS[0]

  function selectProvider(p: typeof PROVIDERS[number]) {
    setForm(f => ({ ...f, provider: p.id, model: p.model, base_url: p.needsUrl ? (f.base_url || 'http://localhost:11434') : '' }))
    setTestResult(null)
  }

  async function save() {
    setSaving(true)
    try {
      const updated = await api.settings.saveAi({ ...form, api_key: form.api_key?.trim() || undefined, base_url: form.base_url?.trim() || undefined })
      setHasStoredKey(updated.has_key)
      setForm(f => ({ ...f, api_key: '' }))
    } finally { setSaving(false) }
  }

  async function test() {
    setTesting(true); setTestResult(null)
    try {
      const r = await api.settings.testAi()
      setTestResult({ ok: true, msg: `Verbindung OK — ${r.message}` })
    } catch (e: unknown) {
      setTestResult({ ok: false, msg: e instanceof Error ? e.message : String(e) })
    } finally { setTesting(false) }
  }

  if (loading) return <div className="py-8 text-center text-gray-400 text-sm">Lädt…</div>

  return (
    <div className="space-y-5">
      <label className="flex items-center justify-between">
        <span className="text-sm font-medium text-gray-700">KI-Analyse aktiviert</span>
        <button type="button" onClick={() => setForm(f => ({ ...f, enabled: !f.enabled }))}
          className={clsx('relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500', form.enabled ? 'bg-indigo-600' : 'bg-gray-200')}>
          <span className={clsx('inline-block h-4 w-4 rounded-full bg-white shadow transition-transform', form.enabled ? 'translate-x-6' : 'translate-x-1')} />
        </button>
      </label>

      <div>
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Anbieter</p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {PROVIDERS.map(p => (
            <button key={p.id} type="button" onClick={() => selectProvider(p)}
              className={clsx('flex flex-col items-start rounded-xl border p-3 text-left transition-all',
                form.provider === p.id ? 'border-indigo-500 ring-2 ring-indigo-200 bg-indigo-50' : 'border-gray-200 hover:border-gray-300 bg-white')}>
              <span className="text-sm font-medium text-gray-800">{p.name}</span>
              <span className={clsx('mt-1 text-xs px-1.5 py-0.5 rounded-full font-medium', p.badgeColor)}>{p.badge}</span>
            </button>
          ))}
        </div>
      </div>

      <div>
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">Modell</p>
        <input className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
          value={form.model} onChange={e => setForm(f => ({ ...f, model: e.target.value }))} />
      </div>

      {!prov.needsUrl && (
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">API Key</p>
            {prov.keyUrl && <a href={prov.keyUrl} target="_blank" rel="noreferrer"
              className="flex items-center gap-1 text-xs text-indigo-600 hover:underline">Key holen <ExternalLink className="h-3 w-3" /></a>}
          </div>
          {hasStoredKey && !form.api_key ? (
            <div className="flex items-center gap-2">
              <div className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-500 bg-gray-50">●●●●●●●●●●●● (gespeichert)</div>
              <button type="button" onClick={() => { api.settings.clearAiKey(); setHasStoredKey(false) }} className="text-xs text-red-500 hover:text-red-600">Löschen</button>
              <button type="button" onClick={() => setForm(f => ({ ...f, api_key: ' ' }))} className="text-xs text-indigo-600">Ändern</button>
            </div>
          ) : (
            <div className="relative">
              <input type={showKey ? 'text' : 'password'}
                className="w-full rounded-lg border border-gray-200 px-3 py-2 pr-10 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder={prov.keyPh || 'API Key'} value={form.api_key ?? ''}
                onChange={e => setForm(f => ({ ...f, api_key: e.target.value }))} />
              <button type="button" onClick={() => setShowKey(s => !s)} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400">
                {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          )}
        </div>
      )}

      {prov.needsUrl && (
        <div>
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">Base URL</p>
          <input className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="http://localhost:11434" value={form.base_url ?? ''}
            onChange={e => setForm(f => ({ ...f, base_url: e.target.value }))} />
          <p className="mt-1 text-xs text-gray-400">Ollama starten: <code className="bg-gray-100 px-1 rounded">ollama serve</code></p>
        </div>
      )}

      {testResult && (
        <div className={clsx('flex items-start gap-2 rounded-lg px-3 py-2.5 text-sm',
          testResult.ok ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800')}>
          {testResult.ok ? <CheckCircle className="h-4 w-4 mt-0.5 shrink-0" /> : <XCircle className="h-4 w-4 mt-0.5 shrink-0" />}
          <span>{testResult.msg}</span>
        </div>
      )}

      <div className="flex items-center justify-between pt-1">
        <button type="button" onClick={test} disabled={testing}
          className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 disabled:opacity-50">
          {testing && <Loader className="h-4 w-4 animate-spin" />} Verbindung testen
        </button>
        <button onClick={save} disabled={saving}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60">
          {saving ? 'Speichern…' : 'Speichern'}
        </button>
      </div>
    </div>
  )
}

// ── iCloud Sync Panel ─────────────────────────────────────────────────────────
function ICloudSyncPanel() {
  const [status, setStatus] = useState<ICloudSyncStatus | null>(null)
  const [creds, setCreds] = useState({ apple_id: '', app_password: '', icloud_email: '', web_password: '' })
  const [showPw, setShowPw] = useState(false)
  const [showWebPw, setShowWebPw] = useState(false)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null)
  const [syncing, setSyncing] = useState<string | null>(null)
  const [lastResult, setLastResult] = useState<(SyncResult & { target: string }) | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [twoFaCode, setTwoFaCode] = useState('')
  const [needs2fa, setNeeds2fa] = useState(false)
  const [twoFaMsg, setTwoFaMsg] = useState('')
  const [verifying2fa, setVerifying2fa] = useState(false)
  const [savingWebPw, setSavingWebPw] = useState(false)
  const [webPwSaved, setWebPwSaved] = useState(false)

  useEffect(() => { api.icloud.status().then(setStatus) }, [])

  const fmtDate = (d?: string) =>
    d ? new Date(d).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : 'noch nie'

  async function saveCreds() {
    if (!creds.apple_id || !creds.app_password) return
    setSaving(true)
    try {
      const s = await api.icloud.saveCredentials({
        apple_id: creds.apple_id,
        app_password: creds.app_password,
        icloud_email: creds.icloud_email || undefined,
        web_password: creds.web_password || undefined,
      })
      setStatus(s)
      setCreds(c => ({ ...c, app_password: '', web_password: '' }))
      setTestResult(null)
    } finally { setSaving(false) }
  }

  async function testConn() {
    setTesting(true); setTestResult(null)
    try {
      const r = await api.icloud.test()
      setTestResult({ ok: true, msg: r.message })
    } catch (e: unknown) {
      setTestResult({ ok: false, msg: e instanceof Error ? e.message : String(e) })
    } finally { setTesting(false) }
  }

  async function disconnect() {
    await api.icloud.disconnect()
    setStatus({ connected: false })
  }

  async function runSync(target: string, fn: () => Promise<SyncResult>) {
    setSyncing(target); setError(null); setLastResult(null); setNeeds2fa(false)
    try {
      const res = await fn()
      if (res.requires_2fa) {
        setNeeds2fa(true)
        setTwoFaCode('')
        setTwoFaMsg(res.errors[0] ?? '')
        return
      }
      setLastResult({ ...res, target })
      const s = await api.icloud.status()
      setStatus(s)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally { setSyncing(null) }
  }

  async function saveWebPassword() {
    if (!creds.web_password.trim()) return
    setSavingWebPw(true); setWebPwSaved(false)
    try {
      await api.icloud.saveWebPassword(creds.web_password.trim())
      setCreds(c => ({ ...c, web_password: '' }))
      setWebPwSaved(true)
      setTimeout(() => setWebPwSaved(false), 3000)
    } finally { setSavingWebPw(false) }
  }

  async function submit2fa() {
    if (!twoFaCode.trim()) return
    setVerifying2fa(true); setError(null)
    try {
      const res = await api.icloud.verify2fa(twoFaCode.trim())
      setNeeds2fa(false)
      setTwoFaCode('')
      setLastResult({ ...res, target: 'notes' })
      const s = await api.icloud.status()
      setStatus(s)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally { setVerifying2fa(false) }
  }

  const SOURCES: { id: string; label: string; syncFn: () => Promise<SyncResult>; resetFn?: () => Promise<Response>; lastSync?: string; disabled?: boolean }[] = status?.connected ? [
    { id: 'mail',      label: 'Mail',        syncFn: api.icloud.syncMail,      resetFn: api.icloud.resetMail,     lastSync: status.mail_last_sync },
    { id: 'calendar',  label: 'Kalender',    syncFn: api.icloud.syncCalendar,  resetFn: api.icloud.resetCalendar, lastSync: status.calendar_last_sync },
    { id: 'reminders', label: 'Erinnerungen',syncFn: api.icloud.syncReminders, lastSync: status.reminders_last_sync },
    { id: 'contacts',  label: 'Kontakte',    syncFn: api.icloud.syncContacts,  lastSync: status.contacts_last_sync },
    { id: 'notes',     label: 'Notizen',     syncFn: api.icloud.syncNotes,     resetFn: api.icloud.resetNotes,    lastSync: status.notes_last_sync },
  ] : []

  return (
    <div className="space-y-5">
      <div className="rounded-lg bg-blue-50 border border-blue-100 p-3 text-xs text-blue-800 space-y-1">
        <p className="font-semibold">App-spezifisches Passwort erforderlich</p>
        <p>Apple ID → Sicherheit → App-spezifische Passwörter → Generieren</p>
        <a href="https://appleid.apple.com/account/manage" target="_blank" rel="noreferrer"
          className="inline-flex items-center gap-1 text-blue-700 hover:underline font-medium">
          appleid.apple.com <ExternalLink className="h-3 w-3" />
        </a>
      </div>

      <div className="space-y-2">
        <input
          className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          placeholder="Apple ID (z.B. vorname@gmail.com)"
          value={creds.apple_id}
          onChange={e => setCreds(c => ({ ...c, apple_id: e.target.value }))}
        />
        <input
          className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          placeholder="iCloud-Mail-Adresse für Mail/Notizen (z.B. vorname@icloud.com) – optional"
          value={creds.icloud_email}
          onChange={e => setCreds(c => ({ ...c, icloud_email: e.target.value }))}
        />
        <div className="relative">
          <input
            type={showPw ? 'text' : 'password'}
            className="w-full rounded-lg border border-gray-200 px-3 py-2 pr-10 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="App-spezifisches Passwort (xxxx-xxxx-xxxx-xxxx)"
            value={creds.app_password}
            onChange={e => setCreds(c => ({ ...c, app_password: e.target.value }))}
          />
          <button type="button" onClick={() => setShowPw(s => !s)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400">
            {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        </div>
        <div className="flex gap-2">
          <button onClick={saveCreds} disabled={saving || !creds.apple_id || !creds.app_password}
            className="rounded-lg bg-gray-800 px-4 py-2 text-xs font-medium text-white hover:bg-gray-700 disabled:opacity-50">
            {saving ? 'Speichern…' : 'Speichern'}
          </button>
          {(status?.connected || status?.apple_id) && (
            <button onClick={testConn} disabled={testing}
              className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-4 py-2 text-xs text-gray-700 hover:bg-gray-50 disabled:opacity-50">
              {testing && <Loader className="h-3.5 w-3.5 animate-spin" />} Verbindung testen
            </button>
          )}
        </div>
      </div>

      {testResult && (
        <div className={clsx('flex items-start gap-2 rounded-lg px-3 py-2.5 text-sm',
          testResult.ok ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800')}>
          {testResult.ok ? <CheckCircle className="h-4 w-4 mt-0.5 shrink-0" /> : <XCircle className="h-4 w-4 mt-0.5 shrink-0" />}
          {testResult.msg}
        </div>
      )}

      {(status?.connected || status?.apple_id) && (
        <div className="rounded-xl border border-gray-200 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className={`h-2.5 w-2.5 rounded-full ${status.connected ? 'bg-green-500' : 'bg-yellow-400'}`} />
              <span className="text-sm font-medium text-gray-800">{status.apple_id}</span>
              {status.icloud_email && <span className="text-xs text-gray-400">· {status.icloud_email}</span>}
            </div>
            <button onClick={disconnect} className="flex items-center gap-1 text-xs text-red-500 hover:text-red-600">
              <Unlink className="h-3.5 w-3.5" /> Trennen
            </button>
          </div>

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {SOURCES.map(src => (
              <div key={src.id} className="rounded-lg bg-gray-50 border border-gray-100 p-2.5">
                <div className="flex items-center justify-between mb-1.5">
                  <p className="text-xs font-semibold text-gray-700">{src.label}</p>
                  <div className="flex gap-1">
                    <button
                      onClick={() => runSync(src.id, src.syncFn)}
                      disabled={!!syncing || src.disabled}
                      className="flex items-center gap-0.5 rounded bg-white border border-gray-200 px-1.5 py-0.5 text-[11px] hover:bg-gray-50 disabled:opacity-50"
                      title={src.disabled ? 'Nicht verfügbar' : 'Sync'}
                    >
                      {syncing === src.id ? <Loader className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
                    </button>
                    {src.resetFn && (
                      <button
                        onClick={() => src.resetFn!().then(() => runSync(src.id, src.syncFn))}
                        disabled={!!syncing}
                        className="rounded bg-amber-50 border border-amber-200 px-1.5 py-0.5 text-[11px] text-amber-700 hover:bg-amber-100 disabled:opacity-50"
                        title="Alles neu (90 Tage)"
                      >
                        ↺
                      </button>
                    )}
                  </div>
                </div>
                <p className="text-[10px] text-gray-400 leading-tight">{fmtDate(src.lastSync)}</p>
              </div>
            ))}
          </div>

          {needs2fa && (
            <div className="rounded-lg bg-amber-50 border border-amber-200 p-3 space-y-2">
              <p className="text-xs font-semibold text-amber-800">2-Faktor-Authentifizierung erforderlich</p>
              {twoFaMsg && <p className="text-xs text-amber-700">{twoFaMsg}</p>}
              <div className="flex gap-2">
                <input
                  className="flex-1 rounded-lg border border-amber-300 px-3 py-1.5 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-amber-400"
                  placeholder="000000"
                  maxLength={6}
                  value={twoFaCode}
                  onChange={e => setTwoFaCode(e.target.value.replace(/\D/g, ''))}
                  onKeyDown={e => e.key === 'Enter' && submit2fa()}
                  autoFocus
                />
                <button onClick={submit2fa} disabled={verifying2fa || twoFaCode.length < 6}
                  className="rounded-lg bg-amber-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-amber-700 disabled:opacity-50">
                  {verifying2fa ? <Loader className="h-3.5 w-3.5 animate-spin" /> : 'Bestätigen'}
                </button>
              </div>
            </div>
          )}

          {lastResult && !needs2fa && (
            <div className="rounded-lg bg-green-50 border border-green-200 p-3 text-xs text-green-800 space-y-1">
              <p className="font-semibold">{lastResult.target} Sync abgeschlossen</p>
              <p>{lastResult.processed} verarbeitet · {lastResult.created} erstellt · {lastResult.skipped} übersprungen</p>
              {lastResult.errors.length > 0 && <p className="text-red-600">{lastResult.errors.slice(0, 3).join(' | ')}</p>}
            </div>
          )}

          {error && (
            <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-200 p-3 text-xs text-red-700">
              <XCircle className="h-4 w-4 shrink-0 mt-0.5" />{error}
            </div>
          )}
        </div>
      )}

      {!status?.connected && (
        <p className="text-xs text-gray-400 italic">Credentials eingeben und speichern, dann Verbindung testen.</p>
      )}
    </div>
  )
}

// ── Calls / Anrufliste Panel ──────────────────────────────────────────────────
function CallsPanel() {
  const [status, setStatus] = useState<CallsStatus | null>(null)
  const [syncing, setSyncing] = useState(false)
  const [lastResult, setLastResult] = useState<SyncResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => { api.icloud.callsStatus().then(setStatus) }, [])

  const fmtDate = (d?: string) =>
    d ? new Date(d).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : 'noch nie'

  async function toggle() {
    if (!status) return
    const next = !status.enabled
    const updated = await api.icloud.callsSettings(next)
    setStatus(updated)
  }

  async function runSync() {
    setSyncing(true); setError(null); setLastResult(null)
    try {
      const res = await api.icloud.syncCalls()
      setLastResult(res)
      const s = await api.icloud.callsStatus()
      setStatus(s)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally { setSyncing(false) }
  }

  async function reset() {
    setSyncing(true); setError(null); setLastResult(null)
    try {
      await api.icloud.resetCalls()
      const res = await api.icloud.syncCalls()
      setLastResult(res)
      const s = await api.icloud.callsStatus()
      setStatus(s)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally { setSyncing(false) }
  }

  if (!status) return <div className="py-8 text-center text-gray-400 text-sm">Lädt…</div>

  return (
    <div className="space-y-5">
      {/* Explanation */}
      <div className="rounded-lg bg-gray-50 border border-gray-100 p-4 space-y-2 text-xs text-gray-600">
        <div className="flex items-center gap-2 font-semibold text-gray-800">
          <Phone className="h-4 w-4 text-indigo-500" />
          Anrufliste (iPhone + WhatsApp)
        </div>
        <p>Liest Anrufe aus der Mac-Anrufliste und WhatsApp und verknüpft sie mit Bewerbungen über Kontakte.</p>
        <p>Die Bridge muss lokal laufen:</p>
        <code className="block bg-white border border-gray-200 rounded px-2 py-1 text-[11px] font-mono">
          python3 calls_bridge.py
        </code>
        <p className="text-gray-400">Sie startet automatisch beim Login via LaunchAgent.</p>
      </div>

      {/* Bridge status + toggle */}
      <div className="rounded-xl border border-gray-200 p-4 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {status.bridge_reachable
              ? <Wifi className="h-4 w-4 text-green-500" />
              : <WifiOff className="h-4 w-4 text-gray-400" />}
            <span className="text-sm font-medium text-gray-800">
              Bridge {status.bridge_reachable ? 'erreichbar' : 'nicht erreichbar'}
            </span>
          </div>
          <label className="flex items-center gap-2 cursor-pointer">
            <span className="text-xs text-gray-500">Sync aktiviert</span>
            <button
              type="button"
              onClick={toggle}
              className={clsx(
                'relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500',
                status.enabled ? 'bg-indigo-600' : 'bg-gray-200'
              )}
            >
              <span className={clsx('inline-block h-4 w-4 rounded-full bg-white shadow transition-transform', status.enabled ? 'translate-x-6' : 'translate-x-1')} />
            </button>
          </label>
        </div>

        <div className="flex items-center justify-between">
          <p className="text-xs text-gray-400">Letzter Sync: {fmtDate(status.last_sync)}</p>
          <div className="flex gap-2">
            <button
              onClick={runSync}
              disabled={syncing || !status.bridge_reachable || !status.enabled}
              className="flex items-center gap-1 rounded-md bg-white border border-gray-200 px-2.5 py-1.5 text-xs hover:bg-gray-50 disabled:opacity-50"
              title="Neue Anrufe seit letztem Sync"
            >
              {syncing ? <Loader className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
              Sync
            </button>
            <button
              onClick={reset}
              disabled={syncing || !status.bridge_reachable || !status.enabled}
              className="rounded-md bg-amber-50 border border-amber-200 px-2.5 py-1.5 text-xs text-amber-700 hover:bg-amber-100 disabled:opacity-50"
              title="Alle Anrufe neu einlesen"
            >
              ↺ Alles neu
            </button>
          </div>
        </div>

        {!status.bridge_reachable && (
          <div className="flex items-start gap-2 rounded-lg bg-amber-50 border border-amber-100 p-3 text-xs text-amber-800">
            <WifiOff className="h-3.5 w-3.5 shrink-0 mt-0.5" />
            Bridge nicht erreichbar. Im Terminal starten: <code className="font-mono ml-1">python3 calls_bridge.py</code>
          </div>
        )}
      </div>

      {lastResult && (
        <div className="rounded-lg bg-green-50 border border-green-200 p-3 text-xs text-green-800 space-y-1">
          <p className="font-semibold">Sync abgeschlossen</p>
          <p>{lastResult.processed} verarbeitet · {lastResult.created} Events erstellt · {lastResult.skipped} übersprungen</p>
          {lastResult.errors.length > 0 && <p className="text-red-600">{lastResult.errors.slice(0, 3).join(' | ')}</p>}
        </div>
      )}

      {error && (
        <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-200 p-3 text-xs text-red-700">
          <XCircle className="h-4 w-4 shrink-0 mt-0.5" />{error}
        </div>
      )}
    </div>
  )
}

// ── Files / Dokumente Panel ───────────────────────────────────────────────────
function FilesPanel() {
  const [cfg, setCfg] = useState<FilesConfig>({ enabled: true, folder_path: '' })
  const [bridgeOk, setBridgeOk] = useState<boolean | null>(null)
  const [path, setPath] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [lastResult, setLastResult] = useState<SyncResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.files.status().then(s => {
      setCfg(s)
      setPath(s.folder_path ?? '')
      setBridgeOk(s.bridge_reachable ?? false)
    }).catch(() => {})
  }, [])

  const fmtDate = (d?: string) =>
    d ? new Date(d).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : 'noch nie'

  async function save() {
    setSaving(true); setSaved(false)
    try {
      await api.settings.saveFiles({ folder_path: path.trim() || undefined, enabled: cfg.enabled })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } finally { setSaving(false) }
  }

  async function toggleEnabled() {
    const next = !cfg.enabled
    setCfg(c => ({ ...c, enabled: next }))
    await api.settings.saveFiles({ enabled: next }).catch(() => {})
  }

  async function runSync() {
    setSyncing(true); setError(null); setLastResult(null)
    try {
      await api.files.sync()
      // Brief wait then poll for result
      await new Promise(r => setTimeout(r, 2000))
      const s = await api.files.status()
      setCfg(s)
      setLastResult({ processed: 0, created: 0, skipped: 0, errors: [] })
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally { setSyncing(false) }
  }

  async function reset() {
    await api.files.reset().catch(() => {})
    const s = await api.files.status()
    setCfg(s)
  }

  return (
    <div className="space-y-5">
      <div className="rounded-lg bg-gray-50 border border-gray-100 p-4 space-y-2 text-xs text-gray-600">
        <div className="flex items-center gap-2 font-semibold text-gray-800">
          <FolderOpen className="h-4 w-4 text-indigo-500" />
          Lokale Bewerbungsunterlagen
        </div>
        <p>Scannt einen Ordner nach PDF, DOCX, TXT und Markdown-Dateien und verknüpft sie anhand des Datei- und Ordnernamens mit Bewerbungen.</p>
        <p>Die Bridge muss lokal laufen:</p>
        <code className="block bg-white border border-gray-200 rounded px-2 py-1 text-[11px] font-mono">
          python3 files_bridge.py
        </code>
        <p className="text-gray-400">Für PDF/DOCX-Text: <code>pip install pdfplumber python-docx</code></p>
      </div>

      {/* Bridge status */}
      <div className="flex items-center gap-2">
        {bridgeOk === null
          ? <Loader className="h-4 w-4 animate-spin text-gray-400" />
          : bridgeOk
            ? <Wifi className="h-4 w-4 text-green-500" />
            : <WifiOff className="h-4 w-4 text-gray-400" />}
        <span className="text-sm text-gray-700">
          Bridge {bridgeOk ? 'erreichbar (Port 9998)' : 'nicht erreichbar'}
        </span>
      </div>

      {/* Folder path */}
      <div>
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">Ordnerpfad (absolut)</p>
        <input
          className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
          placeholder="/Users/dein-name/Documents/Bewerbungen"
          value={path}
          onChange={e => setPath(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && save()}
        />
        <p className="mt-1 text-xs text-gray-400">
          Unterordner-Namen (z.B. „Moog", „Siemens") werden als Firmenname erkannt.
        </p>
      </div>

      {/* Enable toggle + save */}
      <div className="flex items-center justify-between">
        <label className="flex items-center gap-2 cursor-pointer">
          <span className="text-sm text-gray-700">Sync aktiviert</span>
          <button
            type="button"
            onClick={toggleEnabled}
            className={clsx(
              'relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none',
              cfg.enabled ? 'bg-indigo-600' : 'bg-gray-200',
            )}
          >
            <span className={clsx('inline-block h-4 w-4 rounded-full bg-white shadow transition-transform', cfg.enabled ? 'translate-x-6' : 'translate-x-1')} />
          </button>
        </label>
        <div className="flex gap-2">
          <button
            onClick={save}
            disabled={saving}
            className="rounded-lg bg-gray-800 px-4 py-2 text-xs font-medium text-white hover:bg-gray-700 disabled:opacity-50"
          >
            {saving ? 'Speichern…' : saved ? '✓ Gespeichert' : 'Speichern'}
          </button>
        </div>
      </div>

      {/* Sync controls */}
      {cfg.folder_path && (
        <div className="rounded-xl border border-gray-200 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-xs text-gray-400">Letzter Sync: {fmtDate(cfg.last_sync)}</p>
            <div className="flex gap-2">
              <button
                onClick={runSync}
                disabled={syncing || !bridgeOk || !cfg.enabled}
                className="flex items-center gap-1 rounded-md bg-white border border-gray-200 px-2.5 py-1.5 text-xs hover:bg-gray-50 disabled:opacity-50"
              >
                {syncing ? <Loader className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
                Sync
              </button>
              <button
                onClick={reset}
                disabled={syncing}
                className="rounded-md bg-amber-50 border border-amber-200 px-2.5 py-1.5 text-xs text-amber-700 hover:bg-amber-100 disabled:opacity-50"
                title="Alle Dateien erneut einlesen"
              >
                ↺ Alles neu
              </button>
            </div>
          </div>

          {!bridgeOk && (
            <div className="flex items-start gap-2 rounded-lg bg-amber-50 border border-amber-100 p-3 text-xs text-amber-800">
              <WifiOff className="h-3.5 w-3.5 shrink-0 mt-0.5" />
              Bridge nicht erreichbar. Im Terminal starten: <code className="font-mono ml-1">python3 files_bridge.py</code>
            </div>
          )}
        </div>
      )}

      {lastResult && (
        <div className="rounded-lg bg-green-50 border border-green-200 p-3 text-xs text-green-800">
          <p className="font-semibold">Sync gestartet – läuft im Hintergrund</p>
        </div>
      )}

      {error && (
        <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-200 p-3 text-xs text-red-700">
          <XCircle className="h-4 w-4 shrink-0 mt-0.5" />{error}
        </div>
      )}
    </div>
  )
}

// ── Main Modal ────────────────────────────────────────────────────────────────
// ── Sync Control Panel ────────────────────────────────────────────────────────

const DEFAULT_SYNC: SyncSettings = {
  google_enabled: true, gmail_enabled: true, gcal_enabled: true,
  icloud_enabled: true, icloud_mail_enabled: true, icloud_cal_enabled: true,
  icloud_notes_enabled: true, icloud_reminders_enabled: true,
  icloud_contacts_enabled: true, icloud_calls_enabled: true,
  linkedin_enabled: true,
  files_enabled: true,
}

function Toggle({ on, onChange, disabled }: { on: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      onClick={() => !disabled && onChange(!on)}
      className={clsx(
        'relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none',
        on && !disabled ? 'bg-indigo-600' : disabled ? 'bg-gray-200 cursor-not-allowed' : 'bg-gray-300',
      )}
    >
      <span className={clsx('inline-block h-3.5 w-3.5 rounded-full bg-white shadow transition-transform',
        on ? 'translate-x-[18px]' : 'translate-x-0.5')} />
    </button>
  )
}

function SyncGroup({ label, enabled, onToggle, children }: {
  label: string; enabled: boolean; onToggle: (v: boolean) => void; children: React.ReactNode
}) {
  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 bg-gray-50">
        <span className="text-sm font-semibold text-gray-800">{label}</span>
        <Toggle on={enabled} onChange={onToggle} />
      </div>
      <div className={clsx('divide-y divide-gray-100 transition-opacity', !enabled && 'opacity-40 pointer-events-none')}>
        {children}
      </div>
    </div>
  )
}

function SyncRow({ label, enabled, onToggle }: { label: string; enabled: boolean; onToggle: (v: boolean) => void }) {
  return (
    <div className="flex items-center justify-between px-4 py-2.5">
      <span className="text-sm text-gray-700">{label}</span>
      <Toggle on={enabled} onChange={onToggle} />
    </div>
  )
}

function SyncControlPanel() {
  const [settings, setSettings] = useState<SyncSettings>(DEFAULT_SYNC)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => { api.settings.getSync().then(setSettings).catch(() => {}) }, [])

  async function toggle(key: keyof SyncSettings, val: boolean) {
    const next = { ...settings, [key]: val }
    setSettings(next)
    setSaving(true)
    try {
      await api.settings.saveSync({ [key]: val })
      setSaved(true)
      setTimeout(() => setSaved(false), 1500)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-xs text-gray-500">
        Deaktivierte Quellen werden beim nächsten globalen Sync übersprungen. Einzelne Quellen können weiterhin manuell in den jeweiligen Panels ausgelöst werden.
      </p>

      <SyncGroup label="Google" enabled={settings.google_enabled} onToggle={v => toggle('google_enabled', v)}>
        <SyncRow label="Gmail" enabled={settings.gmail_enabled} onToggle={v => toggle('gmail_enabled', v)} />
        <SyncRow label="Google Kalender" enabled={settings.gcal_enabled} onToggle={v => toggle('gcal_enabled', v)} />
      </SyncGroup>

      <SyncGroup label="Apple / iCloud" enabled={settings.icloud_enabled} onToggle={v => toggle('icloud_enabled', v)}>
        <SyncRow label="iCloud Mail" enabled={settings.icloud_mail_enabled} onToggle={v => toggle('icloud_mail_enabled', v)} />
        <SyncRow label="iCloud Kalender" enabled={settings.icloud_cal_enabled} onToggle={v => toggle('icloud_cal_enabled', v)} />
        <SyncRow label="Apple Notizen" enabled={settings.icloud_notes_enabled} onToggle={v => toggle('icloud_notes_enabled', v)} />
        <SyncRow label="Erinnerungen" enabled={settings.icloud_reminders_enabled} onToggle={v => toggle('icloud_reminders_enabled', v)} />
        <SyncRow label="Kontakte" enabled={settings.icloud_contacts_enabled} onToggle={v => toggle('icloud_contacts_enabled', v)} />
        <SyncRow label="Anrufliste" enabled={settings.icloud_calls_enabled} onToggle={v => toggle('icloud_calls_enabled', v)} />
      </SyncGroup>

      <SyncGroup label="LinkedIn" enabled={settings.linkedin_enabled} onToggle={v => toggle('linkedin_enabled', v)}>
        <div className="px-4 py-2.5 text-xs text-gray-400">LinkedIn Scraper (konfiguriert in Tab „LinkedIn")</div>
      </SyncGroup>

      <SyncGroup label="Lokale Dokumente" enabled={settings.files_enabled} onToggle={v => toggle('files_enabled', v)}>
        <div className="px-4 py-2.5 text-xs text-gray-400">Ordner-Konfiguration im Tab „Dokumente"</div>
      </SyncGroup>

      {(saving || saved) && (
        <p className="text-xs text-center text-indigo-500">{saving ? 'Speichert…' : '✓ Gespeichert'}</p>
      )}
    </div>
  )
}

type Tab = 'ai' | 'google' | 'icloud' | 'calls' | 'sync' | 'files'

export function SettingsModal({ onClose }: Props) {
  const [tab, setTab] = useState<Tab>('ai')

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="w-full max-w-lg rounded-2xl bg-white shadow-2xl flex flex-col max-h-[90vh]">

        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div className="flex gap-1 rounded-lg border border-gray-200 overflow-hidden bg-white">
            {([['sync', 'Sync-Steuerung'], ['ai', 'KI-Anbindung'], ['google', 'Google Sync'], ['icloud', 'iCloud Sync'], ['calls', 'Anrufliste'], ['files', 'Dokumente']] as [Tab, string][]).map(([t, label]) => (
              <button key={t} onClick={() => setTab(t)}
                className={clsx('px-4 py-1.5 text-xs font-medium transition-colors',
                  tab === t ? 'bg-indigo-600 text-white' : 'text-gray-600 hover:bg-gray-50')}>
                {label}
              </button>
            ))}
          </div>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-gray-100 text-gray-400">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="overflow-y-auto flex-1 p-6">
          {tab === 'sync' && <SyncControlPanel />}
          {tab === 'ai' && <AiPanel />}
          {tab === 'google' && <GoogleSyncPanel />}
          {tab === 'icloud' && <ICloudSyncPanel />}
          {tab === 'calls' && <CallsPanel />}
          {tab === 'files' && <FilesPanel />}
        </div>
      </div>
    </div>
  )
}
