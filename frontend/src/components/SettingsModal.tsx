import { useState, useEffect, useRef, useCallback } from 'react'
import { X, CheckCircle, XCircle, Loader, Eye, EyeOff, ExternalLink, RefreshCw, Unlink, Phone, Wifi, WifiOff, FolderOpen, Linkedin, Loader2, AlertCircle, Trash2, Database, Save, Download, Check, RotateCcw } from 'lucide-react'
import { api } from '../api/client'
import { useLogoKey } from '../context/LogoContext'
import type { AiSettingsWrite, GoogleSyncStatus, SyncResult, ICloudSyncStatus, CallsStatus, SyncSettings, FilesConfig, LinkedInSyncStatus, LinkedInSyncLogEntry, BackupStatus } from '../types'
import clsx from 'clsx'

interface Props { onClose: () => void }

// ── AI Provider config ────────────────────────────────────────────────────────
interface ProviderModel {
  model: string
  label: string
  sublabel?: string
  badge?: string
  badgeColor?: string
}

interface AiProvider {
  id: string
  name: string
  badge: string
  badgeColor: string
  model: string
  keyPh: string
  keyUrl: string
  needsUrl: boolean
  defaultUrl?: string
  models?: ProviderModel[]
}

const PROVIDERS: AiProvider[] = [
  {
    id: 'groq', name: 'Groq', badge: 'kostenlos', badgeColor: 'bg-green-100 text-green-700',
    model: 'groq/llama-3.3-70b-versatile', keyPh: 'gsk_…', keyUrl: 'https://console.groq.com/keys', needsUrl: false,
    models: [
      { model: 'groq/llama-3.3-70b-versatile', label: 'Llama 3.3 70B',  sublabel: 'Versatile', badge: 'Empfohlen', badgeColor: 'bg-indigo-100 text-indigo-700' },
      { model: 'groq/llama-3.1-8b-instant',    label: 'Llama 3.1 8B',   sublabel: 'Instant',   badge: 'Schnell',   badgeColor: 'bg-gray-100 text-gray-600' },
      { model: 'groq/llama3-70b-8192',          label: 'Llama 3 70B',    sublabel: '8192 ctx' },
      { model: 'groq/gemma2-9b-it',             label: 'Gemma 2 9B' },
      { model: 'groq/mixtral-8x7b-32768',       label: 'Mixtral 8×7B',   sublabel: '32k ctx' },
    ],
  },
  {
    id: 'anthropic', name: 'Anthropic Claude', badge: 'kostenpflichtig', badgeColor: 'bg-orange-100 text-orange-700',
    model: 'anthropic/claude-haiku-4-5-20251001', keyPh: 'sk-ant-…', keyUrl: 'https://console.anthropic.com', needsUrl: false,
    models: [
      { model: 'anthropic/claude-haiku-4-5-20251001', label: 'Claude Haiku 4.5',  badge: 'Günstig',    badgeColor: 'bg-green-100 text-green-700' },
      { model: 'anthropic/claude-sonnet-4-6',          label: 'Claude Sonnet 4.6', badge: 'Empfohlen', badgeColor: 'bg-indigo-100 text-indigo-700' },
    ],
  },
  {
    id: 'openai', name: 'OpenAI', badge: 'kostenpflichtig', badgeColor: 'bg-orange-100 text-orange-700',
    model: 'gpt-4o-mini', keyPh: 'sk-…', keyUrl: 'https://platform.openai.com/api-keys', needsUrl: false,
    models: [
      { model: 'gpt-4o-mini', label: 'GPT-4o Mini', badge: 'Günstig',    badgeColor: 'bg-green-100 text-green-700' },
      { model: 'gpt-4o',      label: 'GPT-4o',      badge: 'Empfohlen', badgeColor: 'bg-indigo-100 text-indigo-700' },
    ],
  },
  {
    id: 'gemini', name: 'Google Gemini', badge: 'kostenlos', badgeColor: 'bg-green-100 text-green-700',
    model: 'gemini/gemini-2.0-flash', keyPh: 'AIza…', keyUrl: 'https://aistudio.google.com/app/apikey', needsUrl: false,
    models: [
      { model: 'gemini/gemini-2.0-flash',               label: 'Gemini 2.0 Flash',      badge: 'Empfohlen',       badgeColor: 'bg-indigo-100 text-indigo-700' },
      { model: 'gemini/gemini-2.0-flash-lite',          label: 'Gemini 2.0 Flash Lite', badge: 'Schnell',          badgeColor: 'bg-gray-100 text-gray-600' },
      { model: 'gemini/gemini-1.5-flash',               label: 'Gemini 1.5 Flash' },
      { model: 'gemini/gemini-1.5-pro',                 label: 'Gemini 1.5 Pro',        badge: 'kostenpflichtig', badgeColor: 'bg-orange-100 text-orange-700' },
      { model: 'gemini/gemini-2.5-flash-preview-05-20', label: 'Gemini 2.5 Flash',      badge: 'Preview',         badgeColor: 'bg-purple-100 text-purple-700' },
    ],
  },
  {
    id: 'ollama', name: 'Ollama', badge: 'offline', badgeColor: 'bg-yellow-100 text-yellow-700',
    model: 'ollama/llama3.2', keyPh: '', keyUrl: 'https://ollama.com', needsUrl: true,
    defaultUrl: 'http://host.docker.internal:11434',
  },
] as const

interface OllamaModel { name: string; display: string; params: string; size_gb: number }
interface PullProgress { model: string; status: string; pct: number | null }

const POPULAR_OLLAMA_MODELS: OllamaModel[] = [
  { name: 'llama3.2',        display: 'Llama 3.2',    params: '3B',   size_gb: 2.0 },
  { name: 'llama3.2:1b',    display: 'Llama 3.2',    params: '1B',   size_gb: 0.8 },
  { name: 'llama3.1:8b',    display: 'Llama 3.1',    params: '8B',   size_gb: 4.7 },
  { name: 'qwen2.5:7b',     display: 'Qwen 2.5',     params: '7B',   size_gb: 4.4 },
  { name: 'qwen2.5:14b',    display: 'Qwen 2.5',     params: '14B',  size_gb: 9.0 },
  { name: 'mistral',         display: 'Mistral',       params: '7B',   size_gb: 4.1 },
  { name: 'mistral-nemo',   display: 'Mistral Nemo',  params: '12B',  size_gb: 7.1 },
  { name: 'phi4-mini',      display: 'Phi-4 Mini',    params: '3.8B', size_gb: 2.5 },
  { name: 'phi4',            display: 'Phi-4',         params: '14B',  size_gb: 9.1 },
  { name: 'gemma3:4b',      display: 'Gemma 3',       params: '4B',   size_gb: 3.3 },
  { name: 'gemma3:12b',     display: 'Gemma 3',       params: '12B',  size_gb: 8.1 },
  { name: 'deepseek-r1:7b', display: 'DeepSeek-R1',  params: '7B',   size_gb: 4.7 },
]

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
  const [saveResult, setSaveResult] = useState<'saving' | 'saved' | 'error' | null>(null)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null)
  const [loading, setLoading] = useState(true)
  const [ollamaReachable, setOllamaReachable] = useState<boolean | null>(null)
  const [ollamaInstalled, setOllamaInstalled] = useState<string[]>([])
  const [loadingModels, setLoadingModels] = useState(false)
  const [pulling, setPulling] = useState<PullProgress | null>(null)

  useEffect(() => {
    api.settings.getAi().then(d => {
      setForm({ provider: d.provider, model: d.model, api_key: '', base_url: d.base_url ?? '', enabled: d.enabled })
      setHasStoredKey(d.has_key)
    }).finally(() => setLoading(false))
  }, [])

  const prov = PROVIDERS.find(p => p.id === form.provider) ?? PROVIDERS[0]

  const loadOllamaModels = useCallback(async (baseUrl: string) => {
    setLoadingModels(true)
    try {
      const r = await api.settings.listOllamaModels(baseUrl || 'http://host.docker.internal:11434')
      setOllamaReachable(r.reachable)
      setOllamaInstalled(r.installed)
    } catch {
      setOllamaReachable(false)
      setOllamaInstalled([])
    } finally {
      setLoadingModels(false)
    }
  }, [])

  useEffect(() => {
    if (form.provider === 'ollama' && !loading) {
      loadOllamaModels(form.base_url || 'http://host.docker.internal:11434')
    }
  }, [loading]) // eslint-disable-line react-hooks/exhaustive-deps

  async function autoSave(patch: Partial<AiSettingsWrite>, currentForm = form) {
    const merged = { ...currentForm, ...patch }
    setSaveResult('saving')
    try {
      const updated = await api.settings.saveAi({
        ...merged,
        api_key: merged.api_key?.trim() || undefined,
        base_url: merged.base_url?.trim() || undefined,
      })
      setHasStoredKey(updated.has_key)
      setSaveResult('saved')
      setTimeout(() => setSaveResult(null), 2000)
    } catch {
      setSaveResult('error')
    }
  }

  function selectProvider(p: AiProvider) {
    const defaultUrl = p.defaultUrl ?? 'http://host.docker.internal:11434'
    const baseUrl = p.needsUrl ? (form.base_url || defaultUrl) : ''
    const patch = { provider: p.id, model: p.model, base_url: baseUrl }
    setForm(f => ({ ...f, ...patch }))
    setTestResult(null)
    autoSave(patch)
    if (p.needsUrl) loadOllamaModels(baseUrl)
  }

  function selectOllamaModel(name: string) {
    const patch = { model: `ollama/${name}` }
    setForm(f => ({ ...f, ...patch }))
    autoSave(patch)
  }

  async function pullModel(modelName: string) {
    setPulling({ model: modelName, status: 'Starte Download…', pct: null })
    const url = api.settings.pullOllamaModel(modelName, form.base_url || 'http://host.docker.internal:11434')
    try {
      const resp = await fetch(url)
      if (!resp.body) throw new Error('Kein Stream')
      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop() ?? ''
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const d = JSON.parse(line.slice(6))
            if (d.status === 'error') { setPulling({ model: modelName, status: `Fehler: ${d.error}`, pct: null }); return }
            if (d.status === 'done' || d.status === 'success') {
              setPulling(null)
              loadOllamaModels(form.base_url || 'http://host.docker.internal:11434')
              setForm(f => ({ ...f, model: `ollama/${modelName}` }))
              return
            }
            const pct = d.total ? d.completed / d.total : null
            setPulling({ model: modelName, status: d.status ?? 'Lädt…', pct })
          } catch { /* ignore parse errors */ }
        }
      }
    } catch (e) {
      setPulling({ model: modelName, status: `Fehler: ${e instanceof Error ? e.message : String(e)}`, pct: null })
    } finally {
      setPulling(prev => prev?.model === modelName ? null : prev)
    }
  }

  async function saveApiKey() {
    setSaving(true)
    try {
      await autoSave({}, form)
      setForm(f => ({ ...f, api_key: '' }))
    } finally { setSaving(false) }
  }

  async function test() {
    setTesting(true); setTestResult(null)
    try {
      const payload: AiSettingsWrite = { ...form, api_key: form.api_key?.trim() || undefined, base_url: form.base_url?.trim() || undefined }
      const r = await api.settings.testAi(payload)
      setTestResult({ ok: true, msg: `Verbindung OK — ${r.message}` })
    } catch (e: unknown) {
      setTestResult({ ok: false, msg: e instanceof Error ? e.message : String(e) })
    } finally { setTesting(false) }
  }

  const selectedModelBase = form.model.replace(/^ollama\//, '')
  const providerModels = prov.needsUrl ? null : (prov.models ?? null)
  const isKnownModel = providerModels?.some(m => m.model === form.model) ?? false

  if (loading) return <div className="py-8 text-center text-gray-400 text-sm">Lädt…</div>

  return (
    <div className="space-y-5">

      {/* Save status indicator */}
      <div className="flex items-center justify-between">
        <p className="text-xs text-gray-400">Änderungen werden automatisch gespeichert</p>
        <div className="flex items-center gap-1.5">
          {saveResult === 'saving' && <Loader className="h-3.5 w-3.5 animate-spin text-gray-400" />}
          {saveResult === 'saved' && <CheckCircle className="h-3.5 w-3.5 text-green-500" />}
          {saveResult === 'error' && <XCircle className="h-3.5 w-3.5 text-red-500" />}
        </div>
      </div>

      <label className="flex items-center justify-between">
        <span className="text-sm font-medium text-gray-700">KI-Analyse aktiviert</span>
        <button type="button" onClick={() => { const patch = { enabled: !form.enabled }; setForm(f => ({ ...f, ...patch })); autoSave(patch) }}
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

      {/* Ollama: Base URL + Model Picker */}
      {prov.needsUrl && (
        <>
          <div>
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">Base URL</p>
            <input className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder="http://host.docker.internal:11434" value={form.base_url ?? ''}
              onChange={e => setForm(f => ({ ...f, base_url: e.target.value }))}
              onBlur={() => { autoSave({ base_url: form.base_url }); loadOllamaModels(form.base_url || 'http://host.docker.internal:11434') }} />
            <p className="mt-1 text-xs text-gray-400">Mac-Host aus Docker: <code className="bg-gray-100 px-1 rounded">host.docker.internal:11434</code></p>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Modell</p>
              {ollamaReachable === false && <span className="text-xs text-red-500">Ollama nicht erreichbar</span>}
              {loadingModels && <Loader className="h-3.5 w-3.5 animate-spin text-gray-400" />}
            </div>

            {ollamaInstalled.length > 0 && (
              <div className="mb-3">
                <p className="text-xs text-gray-400 mb-1.5">Installiert</p>
                <div className="flex flex-wrap gap-2">
                  {ollamaInstalled.map(name => (
                    <button key={name} type="button" onClick={() => selectOllamaModel(name)}
                      className={clsx('flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-sm font-medium transition-all',
                        selectedModelBase === name ? 'border-indigo-500 bg-indigo-50 text-indigo-700 ring-2 ring-indigo-200' : 'border-gray-200 bg-white text-gray-700 hover:border-gray-300')}>
                      {selectedModelBase === name && <Check className="h-3.5 w-3.5" />}
                      {name}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div>
              <p className="text-xs text-gray-400 mb-1.5">Verfügbar zum Download</p>
              <div className="space-y-1.5 max-h-52 overflow-y-auto pr-1">
                {POPULAR_OLLAMA_MODELS
                  .filter(m => !ollamaInstalled.some(i => i === m.name || i.startsWith(m.name + ':')))
                  .map(m => {
                    const isPulling = pulling?.model === m.name
                    return (
                      <div key={m.name} className="flex items-center justify-between rounded-lg border border-gray-100 bg-gray-50 px-3 py-2 gap-3">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium text-gray-800">{m.display}</span>
                            <span className="text-xs text-gray-400 font-mono">{m.params}</span>
                            <span className="text-xs text-gray-400">{m.size_gb} GB</span>
                          </div>
                          {isPulling && (
                            <div className="mt-1.5 space-y-1">
                              <p className="text-xs text-indigo-500 truncate">{pulling.status}</p>
                              {pulling.pct !== null && (
                                <div className="h-1.5 rounded-full bg-gray-200 overflow-hidden">
                                  <div className="h-full bg-indigo-500 rounded-full transition-all duration-300" style={{ width: `${(pulling.pct * 100).toFixed(0)}%` }} />
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                        <button type="button" disabled={!!pulling} onClick={() => pullModel(m.name)}
                          className={clsx('flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium transition-colors shrink-0',
                            isPulling ? 'bg-indigo-100 text-indigo-500 cursor-wait' : pulling ? 'bg-gray-100 text-gray-400 cursor-not-allowed' : 'bg-indigo-600 text-white hover:bg-indigo-700')}>
                          {isPulling ? <Loader className="h-3 w-3 animate-spin" /> : <Download className="h-3 w-3" />}
                          {isPulling ? 'Lädt…' : 'Herunterladen'}
                        </button>
                      </div>
                    )
                  })}
              </div>
            </div>

            <div className="mt-3">
              <p className="text-xs text-gray-400 mb-1">Oder manuell eingeben:</p>
              <input className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
                value={form.model} onChange={e => setForm(f => ({ ...f, model: e.target.value }))}
                onBlur={() => autoSave({ model: form.model })} placeholder="ollama/llama3.2" />
            </div>
          </div>
        </>
      )}

      {/* Model (non-Ollama) */}
      {!prov.needsUrl && (
        <div>
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Modell</p>
          {providerModels && (
            <div className="flex flex-wrap gap-2 mb-3">
              {providerModels.map(m => (
                <button key={m.model} type="button"
                  onClick={() => { setForm(f => ({ ...f, model: m.model })); autoSave({ model: m.model }) }}
                  className={clsx(
                    'flex flex-col items-start rounded-xl border px-3 py-2 text-left transition-all',
                    form.model === m.model ? 'border-indigo-500 ring-2 ring-indigo-200 bg-indigo-50' : 'border-gray-200 hover:border-gray-300 bg-white'
                  )}
                >
                  <div className="flex items-center gap-1.5">
                    {form.model === m.model && <Check className="h-3 w-3 text-indigo-600 shrink-0" />}
                    <span className="text-sm font-medium text-gray-800">{m.label}</span>
                  </div>
                  {(m.sublabel || m.badge) && (
                    <div className="flex items-center gap-1.5 mt-0.5">
                      {m.sublabel && <span className="text-xs text-gray-400">{m.sublabel}</span>}
                      {m.badge && (
                        <span className={clsx('text-[10px] px-1.5 py-0.5 rounded-full font-medium', m.badgeColor ?? 'bg-gray-100 text-gray-600')}>
                          {m.badge}
                        </span>
                      )}
                    </div>
                  )}
                </button>
              ))}
            </div>
          )}
          {(!providerModels || !isKnownModel) && (
            <>
              {providerModels && <p className="text-xs text-gray-400 mb-1">Oder manuell eingeben:</p>}
              <input className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
                value={form.model} onChange={e => setForm(f => ({ ...f, model: e.target.value }))}
                onBlur={() => autoSave({ model: form.model })} placeholder="z.B. groq/llama-3.3-70b-versatile" />
            </>
          )}
          {providerModels && isKnownModel && (
            <p className="text-xs text-gray-400 mt-1 font-mono">{form.model}</p>
          )}
        </div>
      )}

      {/* API Key (not for Ollama) */}
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
              <button type="button" onClick={() => { api.settings.clearAiKey(); setHasStoredKey(false) }} className="text-xs text-red-500 hover:text-red-600 whitespace-nowrap">Löschen</button>
              <button type="button" onClick={() => setForm(f => ({ ...f, api_key: ' ' }))} className="text-xs text-indigo-600 hover:text-indigo-700 whitespace-nowrap">Ändern</button>
            </div>
          ) : (
            <div className="flex gap-2">
              <div className="relative flex-1">
                <input type={showKey ? 'text' : 'password'}
                  className="w-full rounded-lg border border-gray-200 px-3 py-2 pr-10 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder={prov.keyPh || 'API Key'} value={form.api_key ?? ''}
                  onChange={e => setForm(f => ({ ...f, api_key: e.target.value }))} />
                <button type="button" onClick={() => setShowKey(s => !s)} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
                  {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
              <button type="button" onClick={saveApiKey} disabled={saving || !form.api_key?.trim()}
                className="px-3 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-40 shrink-0">
                {saving ? <Loader className="h-4 w-4 animate-spin" /> : 'OK'}
              </button>
            </div>
          )}
        </div>
      )}

      {testResult && (
        <div className={clsx('flex items-start gap-2 rounded-lg px-3 py-2.5 text-sm',
          testResult.ok ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800')}>
          {testResult.ok ? <CheckCircle className="h-4 w-4 mt-0.5 shrink-0" /> : <XCircle className="h-4 w-4 mt-0.5 shrink-0" />}
          <span>{testResult.msg}</span>
        </div>
      )}

      <div className="pt-1">
        <button type="button" onClick={test} disabled={testing}
          className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 disabled:opacity-50">
          {testing && <Loader className="h-4 w-4 animate-spin" />} Verbindung testen
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
  audit_log_level: 'normal',
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

  async function toggle(key: keyof SyncSettings, val: boolean | string) {
    const next = { ...settings, [key]: val }
    setSettings(next as SyncSettings)
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

      <div className="border border-gray-200 rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 bg-gray-50">
          <span className="text-sm font-semibold text-gray-800">Audit-Log</span>
        </div>
        <div className="flex items-center justify-between px-4 py-3">
          <div>
            <span className="text-sm text-gray-700">Log-Stufe</span>
            <p className="text-xs text-gray-400 mt-0.5">Normal: Status, Erstellen, Löschen, Merge, Import · Ausführlich: + alle Feldänderungen</p>
          </div>
          <select
            value={settings.audit_log_level}
            onChange={e => toggle('audit_log_level', e.target.value)}
            className="text-sm border border-gray-200 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-indigo-300 bg-white"
          >
            <option value="off">Aus</option>
            <option value="normal">Normal</option>
            <option value="verbose">Ausführlich</option>
          </select>
        </div>
      </div>

      {(saving || saved) && (
        <p className="text-xs text-center text-indigo-500">{saving ? 'Speichert…' : '✓ Gespeichert'}</p>
      )}
    </div>
  )
}

function LinkedInPanel({ onSynced }: { onSynced: () => void }) {
  const [liConfig, setLiConfig] = useState<{ configured: boolean; email?: string; has_session: boolean; last_sync?: string } | null>(null)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [saving, setSaving] = useState(false)
  const [syncState, setSyncState] = useState<LinkedInSyncStatus | null>(null)
  const [liError, setLiError] = useState<string | null>(null)
  const [twoFaCode, setTwoFaCode] = useState('')
  const [submitting2fa, setSubmitting2fa] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  function stopPolling() {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
  }

  async function loadConfig() {
    try {
      const c = await api.linkedin.getConfig() as typeof liConfig
      setLiConfig(c)
    } catch { /* ignore */ }
  }

  useEffect(() => { loadConfig(); return () => stopPolling() }, [])

  async function handleSave() {
    if (!email.trim() || !password.trim()) return
    setSaving(true); setLiError(null)
    try {
      await api.linkedin.saveConfig(email.trim(), password.trim())
      await loadConfig(); setPassword('')
    } catch (e: unknown) { setLiError(e instanceof Error ? e.message : String(e)) }
    finally { setSaving(false) }
  }

  async function handleDelete() {
    await api.linkedin.deleteConfig(); setLiConfig(null); setEmail(''); setPassword('')
  }

  async function handleClearSession() {
    await api.linkedin.clearSession(); await loadConfig()
  }

  async function handleSync() {
    setLiError(null)
    try {
      const s = await api.linkedin.run() as LinkedInSyncStatus
      setSyncState(s); stopPolling()
      pollRef.current = setInterval(async () => {
        try {
          const s2 = await api.linkedin.status() as LinkedInSyncStatus
          setSyncState(s2)
          if (s2.status === 'done') { stopPolling(); onSynced() }
          else if (s2.status === 'error' || s2.status === 'needs_login') { stopPolling() }
        } catch { /* ignore */ }
      }, 2000)
    } catch (e: unknown) { setLiError(e instanceof Error ? e.message : String(e)) }
  }

  function logLabel(e: LinkedInSyncLogEntry) {
    if (e.aktion === 'neu') return { text: 'Neu', cls: 'bg-indigo-50 text-indigo-700' }
    if (e.aktion === 'abgesagt') return { text: 'Abgesagt', cls: 'bg-red-50 text-red-700' }
    if (e.aktion === 'aktualisiert') return { text: 'Aktualisiert', cls: 'bg-blue-50 text-blue-700' }
    return { text: 'Unverändert', cls: 'bg-gray-50 text-gray-500' }
  }

  async function handleSubmit2fa() {
    if (!twoFaCode.trim()) return
    setSubmitting2fa(true); setLiError(null)
    try {
      await api.linkedin.submitTwoFa(twoFaCode.trim())
      setTwoFaCode('')
    } catch (e: unknown) { setLiError(e instanceof Error ? e.message : String(e)) }
    finally { setSubmitting2fa(false) }
  }

  const isRunning = syncState?.status === 'running'
  const isDone = syncState?.status === 'done'
  const isError = syncState?.status === 'error'
  const needsLogin = syncState?.status === 'needs_login'
  const needs2fa = syncState?.status === 'needs_2fa'

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-gray-800 flex items-center gap-2">
        <Linkedin className="h-4 w-4 text-[#0077B5]" /> LinkedIn Sync
      </h3>

      {/* Config */}
      {liConfig?.configured ? (
        <div className="space-y-3">
          <div className="flex items-center justify-between rounded-lg bg-green-50 border border-green-200 px-3 py-2">
            <div>
              <p className="text-xs font-medium text-green-800">{liConfig.email}</p>
              <p className="text-[10px] text-green-600">
                {liConfig.has_session ? 'Session aktiv' : 'Kein gespeichertes Login'}
                {liConfig.last_sync ? ` · Letzter Sync: ${new Date(liConfig.last_sync).toLocaleDateString('de-DE')}` : ''}
              </p>
            </div>
            <button onClick={handleDelete} className="p-1 text-green-400 hover:text-red-500">
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
          {liConfig.has_session && (
            <button onClick={handleClearSession} className="text-xs text-gray-400 hover:text-gray-600 flex items-center gap-1">
              <RefreshCw className="h-3 w-3" /> Session zurücksetzen
            </button>
          )}
          <p className="text-xs text-gray-500">
            Synchronisiert eingereichte Bewerbungen von LinkedIn. Neue werden angelegt,
            Archivierte (in früher Phase) als Absage markiert.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-xs text-gray-500">
            LinkedIn-Zugangsdaten eingeben. Das Passwort wird verschlüsselt gespeichert.
          </p>
          <div className="space-y-2">
            <input type="email" placeholder="E-Mail" value={email} onChange={e => setEmail(e.target.value)}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#0077B5]/30" />
            <div className="relative">
              <input type={showPw ? 'text' : 'password'} placeholder="Passwort" value={password}
                onChange={e => setPassword(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleSave()}
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm pr-9 focus:outline-none focus:ring-2 focus:ring-[#0077B5]/30" />
              <button type="button" onClick={() => setShowPw(v => !v)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
                {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>
          <button onClick={handleSave} disabled={saving || !email.trim() || !password.trim()}
            className="text-xs font-medium px-3 py-1.5 rounded-lg bg-[#0077B5] text-white hover:bg-[#005f91] disabled:opacity-50">
            {saving ? 'Speichern…' : 'Speichern'}
          </button>
        </div>
      )}

      {liError && <p className="text-xs text-red-600">{liError}</p>}

      {/* Sync button */}
      {liConfig?.configured && (
        <button onClick={handleSync} disabled={isRunning}
          className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-[#0077B5] text-white hover:bg-[#005f91] disabled:opacity-50">
          {isRunning ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Linkedin className="h-3.5 w-3.5" />}
          {isRunning ? 'Läuft…' : 'Jetzt synchronisieren'}
        </button>
      )}

      {/* Sync status */}
      {syncState && (
        <div className="space-y-3 border border-gray-100 rounded-lg p-3">
          {(isRunning || needs2fa) && (
            <div className="flex items-center gap-2 text-xs text-gray-600">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-[#0077B5]" />
              <span>{syncState.step || 'Läuft…'}</span>
            </div>
          )}
          {needs2fa && (
            <div className="rounded-lg bg-amber-50 border border-amber-200 p-3 space-y-2">
              <p className="text-xs font-semibold text-amber-800">LinkedIn Bestätigung erforderlich</p>
              <p className="text-xs text-amber-700">
                <strong>Option A:</strong> LinkedIn-App auf dem Handy öffnen und die Anmeldeanfrage bestätigen — der Sync läuft danach automatisch weiter.<br />
                <strong>Option B:</strong> 6-stelligen Code aus E-Mail oder SMS eingeben:
              </p>
              <div className="flex gap-2">
                <input
                  className="flex-1 rounded-lg border border-amber-300 px-3 py-1.5 text-sm font-mono tracking-widest focus:outline-none focus:ring-2 focus:ring-amber-400"
                  placeholder="000000"
                  maxLength={6}
                  value={twoFaCode}
                  onChange={e => setTwoFaCode(e.target.value.replace(/\D/g, ''))}
                  onKeyDown={e => e.key === 'Enter' && handleSubmit2fa()}
                />
                <button onClick={handleSubmit2fa} disabled={submitting2fa || twoFaCode.length < 6}
                  className="rounded-lg bg-amber-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-amber-700 disabled:opacity-50">
                  {submitting2fa ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Code senden'}
                </button>
              </div>
            </div>
          )}
          {isDone && (
            <div className="flex items-center gap-2 text-xs text-green-700">
              <CheckCircle className="h-3.5 w-3.5" /> Sync abgeschlossen
            </div>
          )}
          {(isError || needsLogin) && (
            <div className="flex items-start gap-2 text-xs text-red-700">
              <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
              <span>{syncState.step || 'Fehler'}</span>
            </div>
          )}
          {needsLogin && (
            <p className="text-xs text-gray-400">
              Tipp: Einmal manuell auf linkedin.com einloggen, dann erneut versuchen.
            </p>
          )}

          {(isDone || isError) && syncState.processed > 0 && (
            <div className="flex gap-2 flex-wrap">
              {[
                { n: syncState.processed, label: 'Gefunden', cls: 'bg-gray-50 text-gray-600' },
                { n: syncState.created, label: 'Neu', cls: 'bg-indigo-50 text-indigo-700' },
                { n: syncState.updated, label: 'Aktualisiert', cls: 'bg-blue-50 text-blue-700' },
                { n: syncState.skipped, label: 'Unverändert', cls: 'bg-gray-50 text-gray-400' },
              ].filter(x => x.n > 0).map(x => (
                <div key={x.label} className={`flex flex-col items-center px-2.5 py-1 rounded-lg ${x.cls}`}>
                  <span className="text-base font-bold leading-tight">{x.n}</span>
                  <span className="text-[10px] font-medium">{x.label}</span>
                </div>
              ))}
            </div>
          )}

          {isDone && syncState.log && syncState.log.filter(e => e.aktion !== 'unverändert').length > 0 && (
            <details open className="text-xs">
              <summary className="cursor-pointer text-gray-500 hover:text-gray-700 font-medium">
                Aktionslog ({syncState.log.filter(e => e.aktion !== 'unverändert').length} Änderungen)
              </summary>
              <div className="mt-1 max-h-48 overflow-y-auto space-y-1">
                {syncState.log.filter(e => e.aktion !== 'unverändert').map((entry, i) => {
                  const { text, cls } = logLabel(entry)
                  return (
                    <div key={i} className="flex items-start gap-2">
                      <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold ${cls}`}>{text}</span>
                      <span className="text-gray-700 leading-tight">
                        <span className="font-medium">{entry.firma}</span>
                        {entry.rolle && <span className="text-gray-400"> · {entry.rolle}</span>}
                        {entry.aktion === 'aktualisiert' && entry.von && entry.zu && <span className="text-gray-400"> ({entry.von} → {entry.zu})</span>}
                        {entry.aktion === 'abgesagt' && entry.von && <span className="text-gray-400"> (war: {entry.von})</span>}
                      </span>
                    </div>
                  )
                })}
              </div>
            </details>
          )}

          {isDone && syncState.log && syncState.log.filter(e => e.aktion === 'unverändert').length > 0 && (
            <details className="text-xs">
              <summary className="cursor-pointer text-gray-400 hover:text-gray-600">
                {syncState.log.filter(e => e.aktion === 'unverändert').length} unverändert
              </summary>
              <div className="mt-1 max-h-32 overflow-y-auto space-y-0.5 ml-2">
                {syncState.log.filter(e => e.aktion === 'unverändert').map((entry, i) => (
                  <div key={i} className="text-gray-400">{entry.firma} · {entry.rolle}</div>
                ))}
              </div>
            </details>
          )}

          {syncState.errors.length > 0 && (
            <details className="text-xs text-red-600">
              <summary className="cursor-pointer text-gray-500 hover:text-gray-700">{syncState.errors.length} Fehler</summary>
              <ul className="mt-1 space-y-0.5 ml-2">{syncState.errors.map((e, i) => <li key={i}>{e}</li>)}</ul>
            </details>
          )}
        </div>
      )}
    </div>
  )
}

function BackupPanel() {
  const [status, setStatus] = useState<BackupStatus | null>(null)
  const [folder, setFolder] = useState('')
  const [frequencyHours, setFrequencyHours] = useState(24)
  const [keepCount, setKeepCount] = useState(7)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [running, setRunning] = useState(false)
  const [pickingFolder, setPickingFolder] = useState(false)
  const [runResult, setRunResult] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [restoring, setRestoring] = useState<string | null>(null)
  const [restoreConfirm, setRestoreConfirm] = useState<string | null>(null)
  const [restoreResult, setRestoreResult] = useState<string | null>(null)

  useEffect(() => {
    api.backup.status().then(s => {
      setStatus(s)
      setFolder(s.backup_folder ?? '')
      setFrequencyHours(s.frequency_hours)
      setKeepCount(s.keep_count)
    }).catch(() => {})
  }, [])

  async function save(enabled?: boolean) {
    setSaving(true); setSaved(false); setError(null)
    try {
      const s = await api.backup.saveSettings({
        enabled: enabled ?? status?.enabled ?? false,
        backup_folder: folder.trim() || undefined,
        frequency_hours: frequencyHours,
        keep_count: keepCount,
      })
      setStatus(prev => prev ? { ...prev, ...s } : { ...s, backups: [] })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally { setSaving(false) }
  }

  async function toggleEnabled() {
    const next = !(status?.enabled ?? false)
    setStatus(s => s ? { ...s, enabled: next } : null)
    await save(next)
  }

  async function runNow() {
    setRunning(true); setRunResult(null); setError(null)
    try {
      const r = await api.backup.run()
      setRunResult(r.filename)
      const s = await api.backup.status()
      setStatus(s)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally { setRunning(false) }
  }

  async function pickFolder() {
    setPickingFolder(true); setError(null)
    try {
      const r = await api.backup.pickFolder()
      setFolder(r.path)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally { setPickingFolder(false) }
  }

  async function doRestore(filename: string) {
    if (!status?.backup_folder) return
    setRestoring(filename); setRestoreConfirm(null); setError(null); setRestoreResult(null)
    try {
      await api.backup.restore(filename, status.backup_folder)
      setRestoreResult(filename)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally { setRestoring(null) }
  }

  const fmtDate = (ts?: string | number) => {
    if (!ts) return 'noch nie'
    const d = typeof ts === 'number' ? new Date(ts * 1000) : new Date(ts)
    return d.toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
  }

  const fmtSize = (bytes: number) =>
    bytes > 1_000_000 ? `${(bytes / 1_000_000).toFixed(1)} MB` : `${(bytes / 1024).toFixed(0)} KB`

  const FREQUENCY_OPTIONS = [
    { value: 1,   label: 'Stündlich' },
    { value: 6,   label: 'Alle 6 Stunden' },
    { value: 12,  label: 'Alle 12 Stunden' },
    { value: 24,  label: 'Täglich' },
    { value: 168, label: 'Wöchentlich' },
  ]

  return (
    <div className="space-y-5">
      <div className="rounded-lg bg-gray-50 border border-gray-100 p-4 space-y-1.5 text-xs text-gray-600">
        <div className="flex items-center gap-2 font-semibold text-gray-800">
          <Database className="h-4 w-4 text-indigo-500" />
          Datenbank-Backup
        </div>
        <p>Erstellt regelmäßige Kopien der SQLite-Datenbank (enthält alle Bewerbungen und Einstellungen) in einem konfigurierbaren Ordner auf deinem Mac.</p>
      </div>

      {/* Enable toggle */}
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-gray-700">Automatisches Backup</span>
        <button onClick={toggleEnabled}
          className={clsx('relative inline-flex h-5 w-9 items-center rounded-full transition-colors',
            status?.enabled ? 'bg-indigo-600' : 'bg-gray-200')}>
          <span className={clsx('inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform',
            status?.enabled ? 'translate-x-4.5' : 'translate-x-0.5')} />
        </button>
      </div>

      {/* Backup folder */}
      <div className="space-y-1.5">
        <label className="text-xs font-medium text-gray-700">Backup-Ordner</label>
        <div className="flex gap-2">
          <input
            type="text"
            value={folder}
            onChange={e => setFolder(e.target.value)}
            placeholder="/Users/…/Backups/JobTracker"
            className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
          />
          <button
            onClick={pickFolder}
            disabled={pickingFolder}
            title="Ordner auswählen"
            className="shrink-0 flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-2 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            {pickingFolder ? <Loader className="h-3.5 w-3.5 animate-spin" /> : <FolderOpen className="h-3.5 w-3.5 text-indigo-500" />}
            Wählen
          </button>
        </div>
      </div>

      {/* Frequency + Keep count */}
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-gray-700">Frequenz</label>
          <select value={frequencyHours} onChange={e => setFrequencyHours(Number(e.target.value))}
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300">
            {FREQUENCY_OPTIONS.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-gray-700">Backups behalten</label>
          <input
            type="number"
            min={1}
            max={99}
            value={keepCount}
            onChange={e => setKeepCount(Number(e.target.value))}
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
          />
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-2">
        <button onClick={() => save()} disabled={saving}
          className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50">
          {saving ? <Loader className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
          {saved ? 'Gespeichert' : 'Speichern'}
        </button>
        <button onClick={runNow} disabled={running || !folder.trim()}
          className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-40">
          {running ? <Loader className="h-3.5 w-3.5 animate-spin" /> : <Database className="h-3.5 w-3.5" />}
          Jetzt sichern
        </button>
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-100 px-3 py-2 text-xs text-red-700">
          <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
          {error}
        </div>
      )}
      {runResult && (
        <div className="flex items-center gap-2 text-xs text-green-700">
          <CheckCircle className="h-3.5 w-3.5" />
          Backup erstellt: {runResult}
        </div>
      )}

      {restoreResult && (
        <div className="flex items-start gap-2 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-800">
          <CheckCircle className="h-3.5 w-3.5 mt-0.5 shrink-0 text-amber-600" />
          <span>Wiederhergestellt aus <strong>{restoreResult}</strong> — bitte Seite neu laden.</span>
        </div>
      )}

      {restoreConfirm && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2.5 space-y-2">
          <p className="text-xs font-semibold text-red-800">Backup wirklich wiederherstellen?</p>
          <p className="text-xs text-red-700">Alle aktuellen Daten werden durch <strong>{restoreConfirm}</strong> ersetzt. Diese Aktion kann nicht rückgängig gemacht werden.</p>
          <div className="flex gap-2">
            <button onClick={() => doRestore(restoreConfirm)}
              className="rounded-lg bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700">
              Ja, wiederherstellen
            </button>
            <button onClick={() => setRestoreConfirm(null)}
              className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50">
              Abbrechen
            </button>
          </div>
        </div>
      )}

      {/* Existing backups */}
      {status && status.backups.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-xs font-medium text-gray-700">Vorhandene Backups ({status.backups.length})</div>
          <div className="rounded-lg border border-gray-100 divide-y divide-gray-50 max-h-56 overflow-y-auto">
            {status.backups.map(b => (
              <div key={b.name} className="flex items-center justify-between px-3 py-2 text-xs gap-2">
                <div className="min-w-0">
                  <p className="text-gray-700 font-mono truncate">{b.name}</p>
                  <p className="text-gray-400">{fmtDate(b.modified)} · {fmtSize(b.size)}</p>
                </div>
                <button
                  onClick={() => setRestoreConfirm(b.name)}
                  disabled={restoring === b.name}
                  className="shrink-0 flex items-center gap-1 rounded-lg border border-gray-200 px-2 py-1 text-xs text-gray-600 hover:bg-red-50 hover:border-red-200 hover:text-red-700 disabled:opacity-50"
                >
                  {restoring === b.name
                    ? <Loader className="h-3 w-3 animate-spin" />
                    : <RotateCcw className="h-3 w-3" />}
                  Restore
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {status?.last_backup && (
        <div className="text-xs text-gray-400">Letztes Backup: {fmtDate(status.last_backup)}</div>
      )}
    </div>
  )
}

type Tab = 'sync' | 'ai' | 'google' | 'icloud' | 'calls' | 'files' | 'linkedin' | 'backup' | 'logos'

const TABS: [Tab, string][] = [
  ['sync',       'Sync'],
  ['ai',         'KI / API'],
  ['google',     'Google'],
  ['icloud',     'iCloud'],
  ['calls',      'Anrufe'],
  ['files',      'Dokumente'],
  ['linkedin',   'LinkedIn'],
  ['backup',     'Backup'],
  ['logos',      'Logos'],
]

function LogoPanel() {
  const { logoDevKey, setLogoDevKey } = useLogoKey()
  const [key, setKey] = useState(logoDevKey ?? '')
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)

  async function save() {
    setSaving(true)
    try {
      const r = await api.settings.saveLogo(key.trim() || null)
      setLogoDevKey(r.api_key)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-sm font-semibold text-gray-800 mb-1">Firmenlogos</h3>
        <p className="text-xs text-gray-400">
          Logo.dev liefert hochwertige Firmenlogos (inkl. Headhunter). Kostenlos bis 10.000 Abrufe/Monat.
          Ohne Key wird Google Favicons als Fallback verwendet.
        </p>
      </div>

      <div className="space-y-3">
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">
            Logo.dev Public Key{' '}
            <a href="https://logo.dev" target="_blank" rel="noreferrer"
               className="text-indigo-500 hover:underline font-normal">logo.dev →</a>
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={key}
              onChange={e => setKey(e.target.value)}
              placeholder="pk_…"
              className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            <button
              onClick={save}
              disabled={saving}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50 flex items-center gap-1.5"
            >
              {saved ? <Check className="h-4 w-4" /> : saving ? <Loader className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              {saved ? 'Gespeichert' : 'Speichern'}
            </button>
          </div>
        </div>

        {logoDevKey && (
          <div className="flex items-center gap-1.5 text-xs text-emerald-600">
            <CheckCircle className="h-3.5 w-3.5" />
            Logo.dev aktiv — Logos werden bevorzugt geladen
          </div>
        )}
        {!logoDevKey && (
          <div className="flex items-center gap-1.5 text-xs text-gray-400">
            <XCircle className="h-3.5 w-3.5" />
            Kein Key — nur Google Favicons als Fallback
          </div>
        )}
      </div>
    </div>
  )
}

export function SettingsModal({ onClose }: Props) {
  const [tab, setTab] = useState<Tab>('sync')

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="w-full max-w-2xl rounded-2xl bg-white shadow-2xl flex flex-col max-h-[90vh]">

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100 shrink-0">
          <h2 className="text-sm font-semibold text-gray-800">Einstellungen</h2>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-gray-100 text-gray-400">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body: sidebar + content */}
        <div className="flex flex-1 min-h-0">
          {/* Sidebar */}
          <nav className="w-36 shrink-0 border-r border-gray-100 py-2 flex flex-col gap-0.5 overflow-y-auto">
            {TABS.map(([t, label]) => (
              <button key={t} onClick={() => setTab(t)}
                className={clsx(
                  'w-full text-left px-4 py-2 text-xs font-medium transition-colors rounded-none',
                  tab === t
                    ? 'bg-indigo-50 text-indigo-700 border-r-2 border-indigo-500'
                    : 'text-gray-600 hover:bg-gray-50'
                )}>
                {label}
              </button>
            ))}
          </nav>

          {/* Content */}
          <div className="flex-1 overflow-y-auto p-6 min-w-0">
            {tab === 'sync'     && <SyncControlPanel />}
            {tab === 'ai'       && <AiPanel />}
            {tab === 'google'   && <GoogleSyncPanel />}
            {tab === 'icloud'   && <ICloudSyncPanel />}
            {tab === 'calls'    && <CallsPanel />}
            {tab === 'files'    && <FilesPanel />}
            {tab === 'linkedin' && <LinkedInPanel onSynced={onClose} />}
            {tab === 'backup'     && <BackupPanel />}
            {tab === 'logos'      && <LogoPanel />}
          </div>
        </div>
      </div>
    </div>
  )
}
