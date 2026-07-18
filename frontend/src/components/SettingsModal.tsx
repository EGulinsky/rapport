import { useState, useEffect, useRef, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { X, CheckCircle, XCircle, Loader, Eye, EyeOff, ExternalLink, RefreshCw, Unlink, Phone, Wifi, WifiOff, FolderOpen, Linkedin, Loader2, AlertCircle, Trash2, Database, Save, Download, Check, RotateCcw, Upload, FileText, AlertTriangle } from 'lucide-react'
import { api, authFetch } from '../api/client'
import { useLogoKey } from '../context/LogoContext'
import { useAuth } from '../context/AuthContext'
import { SUPPORTED_LANGUAGES, LANGUAGE_NAMES, type SupportedLanguage } from '../i18n'
import { useLocale } from '../i18n/useLocale'
import { formatDate, formatDateTime } from '../i18n/formatDate'
import type { AiSettingsWrite, GoogleSyncStatus, SyncResult, ICloudSyncStatus, CallsStatus, SyncSettings, FilesConfig, LinkedInSyncStatus, LinkedInSyncLogEntry, LinkedInMessagesStatus, LinkedInMessagesImportResult, BackupStatus, AgentHealth } from '../types'
import clsx from 'clsx'

interface Props { onClose: () => void; onReviewOpen?: () => void }

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
    id: 'groq', name: 'Groq', badge: 'free', badgeColor: 'bg-green-100 text-green-700',
    model: 'groq/llama-3.3-70b-versatile', keyPh: 'gsk_…', keyUrl: 'https://console.groq.com/keys', needsUrl: false,
    models: [
      { model: 'groq/llama-3.3-70b-versatile', label: 'Llama 3.3 70B',  sublabel: 'Versatile', badge: 'recommended', badgeColor: 'bg-indigo-100 text-indigo-700' },
      { model: 'groq/llama-3.1-8b-instant',    label: 'Llama 3.1 8B',   sublabel: 'Instant',   badge: 'fast',   badgeColor: 'bg-gray-100 text-gray-600' },
      { model: 'groq/llama3-70b-8192',          label: 'Llama 3 70B',    sublabel: '8192 ctx' },
      { model: 'groq/gemma2-9b-it',             label: 'Gemma 2 9B' },
      { model: 'groq/mixtral-8x7b-32768',       label: 'Mixtral 8×7B',   sublabel: '32k ctx' },
    ],
  },
  {
    id: 'anthropic', name: 'Anthropic Claude', badge: 'paid', badgeColor: 'bg-orange-100 text-orange-700',
    model: 'anthropic/claude-haiku-4-5-20251001', keyPh: 'sk-ant-…', keyUrl: 'https://console.anthropic.com', needsUrl: false,
    models: [
      { model: 'anthropic/claude-haiku-4-5-20251001', label: 'Claude Haiku 4.5',  badge: 'cheap',    badgeColor: 'bg-green-100 text-green-700' },
      { model: 'anthropic/claude-sonnet-4-6',          label: 'Claude Sonnet 4.6', badge: 'recommended', badgeColor: 'bg-indigo-100 text-indigo-700' },
    ],
  },
  {
    id: 'openai', name: 'OpenAI', badge: 'paid', badgeColor: 'bg-orange-100 text-orange-700',
    model: 'gpt-4o-mini', keyPh: 'sk-…', keyUrl: 'https://platform.openai.com/api-keys', needsUrl: false,
    models: [
      { model: 'gpt-4o-mini', label: 'GPT-4o Mini', badge: 'cheap',    badgeColor: 'bg-green-100 text-green-700' },
      { model: 'gpt-4o',      label: 'GPT-4o',      badge: 'recommended', badgeColor: 'bg-indigo-100 text-indigo-700' },
    ],
  },
  {
    id: 'gemini', name: 'Google Gemini', badge: 'free', badgeColor: 'bg-green-100 text-green-700',
    model: 'gemini/gemini-2.0-flash', keyPh: 'AIza…', keyUrl: 'https://aistudio.google.com/app/apikey', needsUrl: false,
    models: [
      { model: 'gemini/gemini-2.0-flash',               label: 'Gemini 2.0 Flash',      badge: 'recommended',       badgeColor: 'bg-indigo-100 text-indigo-700' },
      { model: 'gemini/gemini-2.0-flash-lite',          label: 'Gemini 2.0 Flash Lite', badge: 'fast',          badgeColor: 'bg-gray-100 text-gray-600' },
      { model: 'gemini/gemini-1.5-flash',               label: 'Gemini 1.5 Flash' },
      { model: 'gemini/gemini-1.5-pro',                 label: 'Gemini 1.5 Pro',        badge: 'paid', badgeColor: 'bg-orange-100 text-orange-700' },
      { model: 'gemini/gemini-2.5-flash-preview-05-20', label: 'Gemini 2.5 Flash',      badge: 'preview',         badgeColor: 'bg-purple-100 text-purple-700' },
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
  const { t } = useTranslation(['settings', 'common'])
  const locale = useLocale()
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
    d ? formatDateTime(d, locale, { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : t('shared.never')

  return (
    <div className="space-y-5">
      {/* Credentials */}
      <div>
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
          {t('google.credentialsTitle')}
          <a href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noreferrer"
            className="ml-2 normal-case text-indigo-600 hover:underline inline-flex items-center gap-0.5">
            {t('google.cloudConsole')} <ExternalLink className="h-3 w-3" />
          </a>
        </p>
        <p className="text-xs text-gray-400 mb-3">
          {t('google.setupHint')}<br/>
          {t('google.redirectUriLabel')} <code className="bg-gray-100 px-1 rounded">http://localhost:8000/api/sync/google/callback</code>
        </p>
        <div className="space-y-2">
          <input
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder={t('google.clientIdPlaceholder')}
            value={creds.client_id}
            onChange={e => setCreds(c => ({ ...c, client_id: e.target.value }))}
          />
          <div className="relative">
            <input
              type={showSecret ? 'text' : 'password'}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 pr-10 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder={t('google.clientSecretPlaceholder')}
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
            {savingCreds ? t('common:saving') : t('google.saveCredentials')}
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
                {status.connected ? t('shared.connected') : t('shared.notConnected')}
              </span>
            </div>
            {status.connected
              ? <button onClick={disconnect} className="flex items-center gap-1 text-xs text-red-500 hover:text-red-600">
                  <Unlink className="h-3.5 w-3.5" /> {t('shared.disconnect')}
                </button>
              : <button onClick={openOAuth}
                  className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700">
                  {t('google.connectWithGoogle')}
                </button>
            }
          </div>

          {status.connected && (
            <div className="grid grid-cols-2 gap-3">
              {/* Gmail */}
              <div className="rounded-lg bg-gray-50 border border-gray-100 p-3">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs font-semibold text-gray-700">{t('google.gmail')}</p>
                  <div className="flex gap-1">
                    <button onClick={() => runSync('gmail')} disabled={!!syncing || resetting}
                      className="flex items-center gap-1 rounded-md bg-white border border-gray-200 px-2 py-1 text-xs hover:bg-gray-50 disabled:opacity-50"
                      title={t('google.syncMailTitle')}>
                      {syncing === 'gmail'
                        ? <Loader className="h-3 w-3 animate-spin" />
                        : <RefreshCw className="h-3 w-3" />}
                      {t('shared.sync')}
                    </button>
                    <button onClick={resetAndSync} disabled={!!syncing || resetting}
                      className="flex items-center gap-1 rounded-md bg-amber-50 border border-amber-200 px-2 py-1 text-xs text-amber-700 hover:bg-amber-100 disabled:opacity-50"
                      title={t('google.resyncAllTitle')}>
                      {resetting ? <Loader className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
                      {t('shared.resyncAll')}
                    </button>
                  </div>
                </div>
                <p className="text-xs text-gray-400">{t('google.lastSync', { date: fmtDate(status.gmail_last_sync) })}</p>
              </div>

              {/* Calendar */}
              <div className="rounded-lg bg-gray-50 border border-gray-100 p-3">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs font-semibold text-gray-700">{t('google.calendar')}</p>
                  <button onClick={() => runSync('gcal')} disabled={!!syncing}
                    className="flex items-center gap-1 rounded-md bg-white border border-gray-200 px-2 py-1 text-xs hover:bg-gray-50 disabled:opacity-50">
                    {syncing === 'gcal'
                      ? <Loader className="h-3 w-3 animate-spin" />
                      : <RefreshCw className="h-3 w-3" />}
                    {t('shared.sync')}
                  </button>
                </div>
                <p className="text-xs text-gray-400">{t('google.lastSync', { date: fmtDate(status.gcal_last_sync) })}</p>
              </div>
            </div>
          )}

          {/* Sync result */}
          {lastResult && (
            <div className="rounded-lg bg-green-50 border border-green-200 p-3 text-xs text-green-800 space-y-1">
              <p className="font-semibold">{t('google.syncDoneTitle', { target: lastResult.target === 'gmail' ? t('google.gmail') : t('google.calendar') })}</p>
              <p>{t('google.syncStats', { processed: lastResult.processed, created: lastResult.created, skipped: lastResult.skipped })}</p>
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
  const { t } = useTranslation(['settings', 'common'])
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
    setPulling({ model: modelName, status: t('ai.startingDownload'), pct: null })
    const url = api.settings.pullOllamaModel(modelName, form.base_url || 'http://host.docker.internal:11434')
    try {
      const resp = await authFetch(url)
      if (!resp.body) throw new Error(t('ai.noStream'))
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
            if (d.status === 'error') { setPulling({ model: modelName, status: t('ai.downloadError', { error: d.error }), pct: null }); return }
            if (d.status === 'done' || d.status === 'success') {
              setPulling(null)
              loadOllamaModels(form.base_url || 'http://host.docker.internal:11434')
              setForm(f => ({ ...f, model: `ollama/${modelName}` }))
              return
            }
            const pct = d.total ? d.completed / d.total : null
            setPulling({ model: modelName, status: d.status ?? t('ai.downloading'), pct })
          } catch { /* ignore parse errors */ }
        }
      }
    } catch (e) {
      setPulling({ model: modelName, status: t('ai.downloadError', { error: e instanceof Error ? e.message : String(e) }), pct: null })
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
      setTestResult({ ok: true, msg: t('ai.connectionOk', { message: r.message }) })
    } catch (e: unknown) {
      setTestResult({ ok: false, msg: e instanceof Error ? e.message : String(e) })
    } finally { setTesting(false) }
  }

  const selectedModelBase = form.model.replace(/^ollama\//, '')
  const providerModels = prov.needsUrl ? null : (prov.models ?? null)
  const isKnownModel = providerModels?.some(m => m.model === form.model) ?? false

  if (loading) return <div className="py-8 text-center text-gray-400 text-sm">{t('common:loading')}</div>

  return (
    <div className="space-y-5">

      {/* Save status indicator */}
      <div className="flex items-center justify-between">
        <p className="text-xs text-gray-400">{t('ai.autoSaveHint')}</p>
        <div className="flex items-center gap-1.5">
          {saveResult === 'saving' && <Loader className="h-3.5 w-3.5 animate-spin text-gray-400" />}
          {saveResult === 'saved' && <CheckCircle className="h-3.5 w-3.5 text-green-500" />}
          {saveResult === 'error' && <XCircle className="h-3.5 w-3.5 text-red-500" />}
        </div>
      </div>

      <label className="flex items-center justify-between">
        <span className="text-sm font-medium text-gray-700">{t('ai.enabledLabel')}</span>
        <button type="button" onClick={() => { const patch = { enabled: !form.enabled }; setForm(f => ({ ...f, ...patch })); autoSave(patch) }}
          className={clsx('relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500', form.enabled ? 'bg-indigo-600' : 'bg-gray-200')}>
          <span className={clsx('inline-block h-4 w-4 rounded-full bg-white shadow transition-transform', form.enabled ? 'translate-x-6' : 'translate-x-1')} />
        </button>
      </label>

      <div>
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">{t('ai.provider')}</p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {PROVIDERS.map(p => (
            <button key={p.id} type="button" onClick={() => selectProvider(p)}
              className={clsx('flex flex-col items-start rounded-xl border p-3 text-left transition-all',
                form.provider === p.id ? 'border-indigo-500 ring-2 ring-indigo-200 bg-indigo-50' : 'border-gray-200 hover:border-gray-300 bg-white')}>
              <span className="text-sm font-medium text-gray-800">{p.name}</span>
              <span className={clsx('mt-1 text-xs px-1.5 py-0.5 rounded-full font-medium', p.badgeColor)}>{t(`ai.badge.${p.badge}`)}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Ollama: Base URL + Model Picker */}
      {prov.needsUrl && (
        <>
          <div>
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">{t('ai.baseUrl')}</p>
            <input className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder="http://host.docker.internal:11434" value={form.base_url ?? ''}
              onChange={e => setForm(f => ({ ...f, base_url: e.target.value }))}
              onBlur={() => { autoSave({ base_url: form.base_url }); loadOllamaModels(form.base_url || 'http://host.docker.internal:11434') }} />
            <p className="mt-1 text-xs text-gray-400">{t('ai.baseUrlHint')} <code className="bg-gray-100 px-1 rounded">host.docker.internal:11434</code></p>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{t('ai.model')}</p>
              {ollamaReachable === false && <span className="text-xs text-red-500">{t('ai.ollamaUnreachable')}</span>}
              {loadingModels && <Loader className="h-3.5 w-3.5 animate-spin text-gray-400" />}
            </div>

            {ollamaInstalled.length > 0 && (
              <div className="mb-3">
                <p className="text-xs text-gray-400 mb-1.5">{t('ai.installed')}</p>
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
              <p className="text-xs text-gray-400 mb-1.5">{t('ai.availableForDownload')}</p>
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
                          {isPulling ? t('ai.downloading') : t('ai.download')}
                        </button>
                      </div>
                    )
                  })}
              </div>
            </div>

            <div className="mt-3">
              <p className="text-xs text-gray-400 mb-1">{t('ai.enterManually')}</p>
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
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">{t('ai.model')}</p>
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
                          {t(`ai.badge.${m.badge}`)}
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
              {providerModels && <p className="text-xs text-gray-400 mb-1">{t('ai.enterManually')}</p>}
              <input className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
                value={form.model} onChange={e => setForm(f => ({ ...f, model: e.target.value }))}
                onBlur={() => autoSave({ model: form.model })} placeholder={t('ai.modelPlaceholder')} />
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
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{t('ai.apiKey')}</p>
            {prov.keyUrl && <a href={prov.keyUrl} target="_blank" rel="noreferrer"
              className="flex items-center gap-1 text-xs text-indigo-600 hover:underline">{t('ai.getKey')} <ExternalLink className="h-3 w-3" /></a>}
          </div>
          {hasStoredKey && !form.api_key ? (
            <div className="flex items-center gap-2">
              <div className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-500 bg-gray-50">{t('ai.keyStored')}</div>
              <button type="button" onClick={() => { api.settings.clearAiKey(); setHasStoredKey(false) }} className="text-xs text-red-500 hover:text-red-600 whitespace-nowrap">{t('common:delete')}</button>
              <button type="button" onClick={() => setForm(f => ({ ...f, api_key: ' ' }))} className="text-xs text-indigo-600 hover:text-indigo-700 whitespace-nowrap">{t('ai.changeKey')}</button>
            </div>
          ) : (
            <div className="flex gap-2">
              <div className="relative flex-1">
                <input type={showKey ? 'text' : 'password'}
                  className="w-full rounded-lg border border-gray-200 px-3 py-2 pr-10 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder={prov.keyPh || t('ai.apiKey')} value={form.api_key ?? ''}
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
          {testing && <Loader className="h-4 w-4 animate-spin" />} {t('shared.testConnection')}
        </button>
      </div>
    </div>
  )
}

// ── iCloud Sync Panel ─────────────────────────────────────────────────────────
function ICloudSyncPanel() {
  const { t } = useTranslation(['settings', 'common'])
  const locale = useLocale()
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
    d ? formatDateTime(d, locale, { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : t('shared.never')

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
    { id: 'mail',      label: t('icloud.sourceMail'),      syncFn: api.icloud.syncMail,      resetFn: api.icloud.resetMail,     lastSync: status.mail_last_sync },
    { id: 'calendar',  label: t('icloud.sourceCalendar'),  syncFn: api.icloud.syncCalendar,  resetFn: api.icloud.resetCalendar, lastSync: status.calendar_last_sync },
    { id: 'reminders', label: t('icloud.sourceReminders'), syncFn: api.icloud.syncReminders, lastSync: status.reminders_last_sync },
    { id: 'contacts',  label: t('icloud.sourceContacts'),  syncFn: api.icloud.syncContacts,  lastSync: status.contacts_last_sync },
    { id: 'notes',     label: t('icloud.sourceNotes'),     syncFn: api.icloud.syncNotes,     resetFn: api.icloud.resetNotes,    lastSync: status.notes_last_sync },
  ] : []

  return (
    <div className="space-y-5">
      <div className="rounded-lg bg-blue-50 border border-blue-100 p-3 text-xs text-blue-800 space-y-1">
        <p className="font-semibold">{t('icloud.appPasswordTitle')}</p>
        <p>{t('icloud.appPasswordHint')}</p>
        <a href="https://appleid.apple.com/account/manage" target="_blank" rel="noreferrer"
          className="inline-flex items-center gap-1 text-blue-700 hover:underline font-medium">
          appleid.apple.com <ExternalLink className="h-3 w-3" />
        </a>
      </div>

      <div className="space-y-2">
        <input
          className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          placeholder={t('icloud.appleIdPlaceholder')}
          value={creds.apple_id}
          onChange={e => setCreds(c => ({ ...c, apple_id: e.target.value }))}
        />
        <input
          className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          placeholder={t('icloud.icloudEmailPlaceholder')}
          value={creds.icloud_email}
          onChange={e => setCreds(c => ({ ...c, icloud_email: e.target.value }))}
        />
        <div className="relative">
          <input
            type={showPw ? 'text' : 'password'}
            className="w-full rounded-lg border border-gray-200 px-3 py-2 pr-10 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder={t('icloud.appPasswordPlaceholder')}
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
            {saving ? t('common:saving') : t('common:save')}
          </button>
          {(status?.connected || status?.apple_id) && (
            <button onClick={testConn} disabled={testing}
              className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-4 py-2 text-xs text-gray-700 hover:bg-gray-50 disabled:opacity-50">
              {testing && <Loader className="h-3.5 w-3.5 animate-spin" />} {t('shared.testConnection')}
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
              <Unlink className="h-3.5 w-3.5" /> {t('shared.disconnect')}
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
                      title={src.disabled ? t('icloud.notAvailable') : t('shared.sync')}
                    >
                      {syncing === src.id ? <Loader className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
                    </button>
                    {src.resetFn && (
                      <button
                        onClick={() => src.resetFn!().then(() => runSync(src.id, src.syncFn))}
                        disabled={!!syncing}
                        className="rounded bg-amber-50 border border-amber-200 px-1.5 py-0.5 text-[11px] text-amber-700 hover:bg-amber-100 disabled:opacity-50"
                        title={t('icloud.resyncAllTitle')}
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
              <p className="text-xs font-semibold text-amber-800">{t('icloud.twoFaTitle')}</p>
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
                  {verifying2fa ? <Loader className="h-3.5 w-3.5 animate-spin" /> : t('icloud.twoFaConfirm')}
                </button>
              </div>
            </div>
          )}

          {lastResult && !needs2fa && (
            <div className="rounded-lg bg-green-50 border border-green-200 p-3 text-xs text-green-800 space-y-1">
              <p className="font-semibold">{t('icloud.syncDoneTitle', { target: lastResult.target })}</p>
              <p>{t('shared.processedStats', { processed: lastResult.processed, created: lastResult.created, skipped: lastResult.skipped })}</p>
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
        <p className="text-xs text-gray-400 italic">{t('icloud.enterCredentialsHint')}</p>
      )}
    </div>
  )
}

// ── Calls / Anrufliste Panel ──────────────────────────────────────────────────
function CallsPanel() {
  const { t } = useTranslation(['settings', 'common'])
  const locale = useLocale()
  const [status, setStatus] = useState<CallsStatus | null>(null)
  const [syncing, setSyncing] = useState(false)
  const [lastResult, setLastResult] = useState<SyncResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => { api.icloud.callsStatus().then(setStatus) }, [])

  const fmtDate = (d?: string) =>
    d ? formatDateTime(d, locale, { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : t('shared.never')

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

  if (!status) return <div className="py-8 text-center text-gray-400 text-sm">{t('common:loading')}</div>

  return (
    <div className="space-y-5">
      {/* Explanation */}
      <div className="rounded-lg bg-gray-50 border border-gray-100 p-4 space-y-2 text-xs text-gray-600">
        <div className="flex items-center gap-2 font-semibold text-gray-800">
          <Phone className="h-4 w-4 text-indigo-500" />
          {t('calls.title')}
        </div>
        <p>{t('calls.description')}</p>
        <p className="text-gray-400">{t('calls.requiresAgent')}</p>
      </div>

      {/* Bridge status + toggle */}
      <div className="rounded-xl border border-gray-200 p-4 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {status.bridge_reachable
              ? <Wifi className="h-4 w-4 text-green-500" />
              : <WifiOff className="h-4 w-4 text-gray-400" />}
            <span className="text-sm font-medium text-gray-800">
              {t('calls.bridge')} {status.bridge_reachable ? t('shared.reachable') : t('shared.notReachable')}
            </span>
          </div>
          <label className="flex items-center gap-2 cursor-pointer">
            <span className="text-xs text-gray-500">{t('calls.syncEnabled')}</span>
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
          <p className="text-xs text-gray-400">{t('calls.lastSync', { date: fmtDate(status.last_sync) })}</p>
          <div className="flex gap-2">
            <button
              onClick={runSync}
              disabled={syncing || !status.bridge_reachable || !status.enabled}
              className="flex items-center gap-1 rounded-md bg-white border border-gray-200 px-2.5 py-1.5 text-xs hover:bg-gray-50 disabled:opacity-50"
              title={t('calls.syncNewTitle')}
            >
              {syncing ? <Loader className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
              {t('shared.sync')}
            </button>
            <button
              onClick={reset}
              disabled={syncing || !status.bridge_reachable || !status.enabled}
              className="rounded-md bg-amber-50 border border-amber-200 px-2.5 py-1.5 text-xs text-amber-700 hover:bg-amber-100 disabled:opacity-50"
              title={t('calls.resyncAllTitle')}
            >
              ↺ {t('calls.resyncAll')}
            </button>
          </div>
        </div>

        {!status.bridge_reachable && (
          <div className="flex items-start gap-2 rounded-lg bg-amber-50 border border-amber-100 p-3 text-xs text-amber-800">
            <WifiOff className="h-3.5 w-3.5 shrink-0 mt-0.5" />
            {t('calls.agentUnreachable')}
          </div>
        )}
      </div>

      {lastResult && (
        <div className="rounded-lg bg-green-50 border border-green-200 p-3 text-xs text-green-800 space-y-1">
          <p className="font-semibold">{t('calls.syncDone')}</p>
          <p>{t('calls.syncStats', { processed: lastResult.processed, created: lastResult.created, skipped: lastResult.skipped })}</p>
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
  const { t } = useTranslation(['settings', 'common'])
  const locale = useLocale()
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
    d ? formatDateTime(d, locale, { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : t('shared.never')

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
          {t('files.title')}
        </div>
        <p>{t('files.description')}</p>
        <p className="text-gray-400">{t('files.requiresAgent')}</p>
      </div>

      {/* Agent status */}
      <div className="flex items-center gap-2">
        {bridgeOk === null
          ? <Loader className="h-4 w-4 animate-spin text-gray-400" />
          : bridgeOk
            ? <Wifi className="h-4 w-4 text-green-500" />
            : <WifiOff className="h-4 w-4 text-gray-400" />}
        <span className="text-sm text-gray-700">
          {t('files.agent')} {bridgeOk ? t('shared.reachable') : t('shared.notReachable')}
        </span>
      </div>

      {/* Folder path */}
      <div>
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">{t('files.folderPath')}</p>
        <input
          className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
          placeholder={t('files.folderPathPlaceholder')}
          value={path}
          onChange={e => setPath(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && save()}
        />
        <p className="mt-1 text-xs text-gray-400">
          {t('files.folderPathHint')}
        </p>
      </div>

      {/* Enable toggle + save */}
      <div className="flex items-center justify-between">
        <label className="flex items-center gap-2 cursor-pointer">
          <span className="text-sm text-gray-700">{t('files.syncEnabled')}</span>
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
            {saving ? t('common:saving') : saved ? `✓ ${t('common:saved')}` : t('common:save')}
          </button>
        </div>
      </div>

      {/* Sync controls */}
      {cfg.folder_path && (
        <div className="rounded-xl border border-gray-200 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-xs text-gray-400">{t('files.lastSync', { date: fmtDate(cfg.last_sync) })}</p>
            <div className="flex gap-2">
              <button
                onClick={runSync}
                disabled={syncing || !bridgeOk || !cfg.enabled}
                className="flex items-center gap-1 rounded-md bg-white border border-gray-200 px-2.5 py-1.5 text-xs hover:bg-gray-50 disabled:opacity-50"
              >
                {syncing ? <Loader className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
                {t('shared.sync')}
              </button>
              <button
                onClick={reset}
                disabled={syncing}
                className="rounded-md bg-amber-50 border border-amber-200 px-2.5 py-1.5 text-xs text-amber-700 hover:bg-amber-100 disabled:opacity-50"
                title={t('files.resyncAllTitle')}
              >
                ↺ {t('files.resyncAll')}
              </button>
            </div>
          </div>

          {!bridgeOk && (
            <div className="flex items-start gap-2 rounded-lg bg-amber-50 border border-amber-100 p-3 text-xs text-amber-800">
              <WifiOff className="h-3.5 w-3.5 shrink-0 mt-0.5" />
              {t('files.agentUnreachable')}
            </div>
          )}
        </div>
      )}

      {lastResult && (
        <div className="rounded-lg bg-green-50 border border-green-200 p-3 text-xs text-green-800">
          <p className="font-semibold">{t('files.syncStarted')}</p>
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
  const { t } = useTranslation('settings')
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
        {t('syncControl.description')}
      </p>

      <SyncGroup label={t('syncControl.google')} enabled={settings.google_enabled} onToggle={v => toggle('google_enabled', v)}>
        <SyncRow label={t('syncControl.gmail')} enabled={settings.gmail_enabled} onToggle={v => toggle('gmail_enabled', v)} />
        <SyncRow label={t('syncControl.googleCalendar')} enabled={settings.gcal_enabled} onToggle={v => toggle('gcal_enabled', v)} />
      </SyncGroup>

      <SyncGroup label={t('syncControl.appleIcloud')} enabled={settings.icloud_enabled} onToggle={v => toggle('icloud_enabled', v)}>
        <SyncRow label={t('syncControl.icloudMail')} enabled={settings.icloud_mail_enabled} onToggle={v => toggle('icloud_mail_enabled', v)} />
        <SyncRow label={t('syncControl.icloudCalendar')} enabled={settings.icloud_cal_enabled} onToggle={v => toggle('icloud_cal_enabled', v)} />
        <SyncRow label={t('syncControl.appleNotes')} enabled={settings.icloud_notes_enabled} onToggle={v => toggle('icloud_notes_enabled', v)} />
        <SyncRow label={t('syncControl.reminders')} enabled={settings.icloud_reminders_enabled} onToggle={v => toggle('icloud_reminders_enabled', v)} />
        <SyncRow label={t('syncControl.contacts')} enabled={settings.icloud_contacts_enabled} onToggle={v => toggle('icloud_contacts_enabled', v)} />
        <SyncRow label={t('syncControl.callList')} enabled={settings.icloud_calls_enabled} onToggle={v => toggle('icloud_calls_enabled', v)} />
      </SyncGroup>

      <SyncGroup label={t('syncControl.linkedin')} enabled={settings.linkedin_enabled} onToggle={v => toggle('linkedin_enabled', v)}>
        <div className="px-4 py-2.5 text-xs text-gray-400">{t('syncControl.linkedinHint')}</div>
      </SyncGroup>

      <SyncGroup label={t('syncControl.localDocuments')} enabled={settings.files_enabled} onToggle={v => toggle('files_enabled', v)}>
        <div className="px-4 py-2.5 text-xs text-gray-400">{t('syncControl.localDocumentsHint')}</div>
      </SyncGroup>

      <div className="border border-gray-200 rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 bg-gray-50">
          <span className="text-sm font-semibold text-gray-800">{t('syncControl.auditLog')}</span>
        </div>
        <div className="flex items-center justify-between px-4 py-3">
          <div>
            <span className="text-sm text-gray-700">{t('syncControl.logLevel')}</span>
            <p className="text-xs text-gray-400 mt-0.5">{t('syncControl.logLevelHint')}</p>
          </div>
          <select
            value={settings.audit_log_level}
            onChange={e => toggle('audit_log_level', e.target.value)}
            className="text-sm border border-gray-200 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-indigo-300 bg-white"
          >
            <option value="off">{t('syncControl.logLevelOff')}</option>
            <option value="normal">{t('syncControl.logLevelNormal')}</option>
            <option value="verbose">{t('syncControl.logLevelVerbose')}</option>
          </select>
        </div>
      </div>

      {(saving || saved) && (
        <p className="text-xs text-center text-indigo-500">{saving ? t('syncControl.saving') : `✓ ${t('common:saved')}`}</p>
      )}
    </div>
  )
}

function LinkedInPanel({ onSynced }: { onSynced: () => void }) {
  const { t } = useTranslation(['settings', 'common'])
  const locale = useLocale()
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
  const [messagesStatus, setMessagesStatus] = useState<LinkedInMessagesStatus | null>(null)
  const [messagesUploading, setMessagesUploading] = useState(false)
  const [messagesError, setMessagesError] = useState<string | null>(null)
  const [messagesResult, setMessagesResult] = useState<LinkedInMessagesImportResult | null>(null)

  function stopPolling() {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
  }

  async function loadConfig() {
    try {
      const c = await api.linkedin.getConfig() as typeof liConfig
      setLiConfig(c)
    } catch { /* ignore */ }
  }

  async function loadMessagesStatus() {
    try {
      const s = await api.linkedin.getMessagesStatus()
      setMessagesStatus(s)
    } catch { /* ignore */ }
  }

  useEffect(() => { loadConfig(); loadMessagesStatus(); return () => stopPolling() }, [])

  async function uploadMessages(file: File) {
    setMessagesError(null); setMessagesUploading(true); setMessagesResult(null)
    try {
      const result = await api.linkedin.importMessages(file)
      setMessagesResult(result)
      await loadMessagesStatus()
    } catch (e: unknown) { setMessagesError(e instanceof Error ? e.message : String(e)) }
    finally { setMessagesUploading(false) }
  }

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
    if (e.aktion === 'neu') return { text: t('linkedin.logNew'), cls: 'bg-indigo-50 text-indigo-700' }
    if (e.aktion === 'abgesagt') return { text: t('linkedin.logRejected'), cls: 'bg-red-50 text-red-700' }
    if (e.aktion === 'aktualisiert') return { text: t('linkedin.logUpdated'), cls: 'bg-blue-50 text-blue-700' }
    return { text: t('linkedin.logUnchanged'), cls: 'bg-gray-50 text-gray-500' }
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
        <Linkedin className="h-4 w-4 text-[#0077B5]" /> {t('linkedin.title')}
      </h3>

      {/* Config */}
      {liConfig?.configured ? (
        <div className="space-y-3">
          <div className="flex items-center justify-between rounded-lg bg-green-50 border border-green-200 px-3 py-2">
            <div>
              <p className="text-xs font-medium text-green-800">{liConfig.email}</p>
              <p className="text-[10px] text-green-600">
                {liConfig.has_session ? t('linkedin.sessionActive') : t('linkedin.noSession')}
                {liConfig.last_sync ? t('linkedin.lastSyncSuffix', { date: formatDate(liConfig.last_sync, locale) }) : ''}
              </p>
            </div>
            <button onClick={handleDelete} className="p-1 text-green-400 hover:text-red-500">
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
          {liConfig.has_session && (
            <button onClick={handleClearSession} className="text-xs text-gray-400 hover:text-gray-600 flex items-center gap-1">
              <RefreshCw className="h-3 w-3" /> {t('linkedin.resetSession')}
            </button>
          )}
          <p className="text-xs text-gray-500">
            {t('linkedin.syncDescription')}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-xs text-gray-500">
            {t('linkedin.credentialsHint')}
          </p>
          <div className="space-y-2">
            <input type="email" placeholder={t('linkedin.emailPlaceholder')} value={email} onChange={e => setEmail(e.target.value)}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#0077B5]/30" />
            <div className="relative">
              <input type={showPw ? 'text' : 'password'} placeholder={t('linkedin.passwordPlaceholder')} value={password}
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
            {saving ? t('common:saving') : t('common:save')}
          </button>
        </div>
      )}

      {liError && <p className="text-xs text-red-600">{liError}</p>}

      {/* Sync button */}
      {liConfig?.configured && (
        <button onClick={handleSync} disabled={isRunning}
          className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-[#0077B5] text-white hover:bg-[#005f91] disabled:opacity-50">
          {isRunning ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Linkedin className="h-3.5 w-3.5" />}
          {isRunning ? t('linkedin.running') : t('linkedin.syncNow')}
        </button>
      )}

      {/* Sync status */}
      {syncState && (
        <div className="space-y-3 border border-gray-100 rounded-lg p-3">
          {(isRunning || needs2fa) && (
            <div className="flex items-center gap-2 text-xs text-gray-600">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-[#0077B5]" />
              <span>{syncState.step || t('linkedin.running')}</span>
            </div>
          )}
          {needs2fa && (
            <div className="rounded-lg bg-amber-50 border border-amber-200 p-3 space-y-2">
              <p className="text-xs font-semibold text-amber-800">{t('linkedin.confirmationRequired')}</p>
              <p className="text-xs text-amber-700">
                <strong>{t('linkedin.optionA')}</strong> {t('linkedin.optionAText')}<br />
                <strong>{t('linkedin.optionB')}</strong> {t('linkedin.optionBText')}
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
                  {submitting2fa ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : t('linkedin.sendCode')}
                </button>
              </div>
            </div>
          )}
          {isDone && (
            <div className="flex items-center gap-2 text-xs text-green-700">
              <CheckCircle className="h-3.5 w-3.5" /> {t('linkedin.syncDone')}
            </div>
          )}
          {(isError || needsLogin) && (
            <div className="flex items-start gap-2 text-xs text-red-700">
              <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
              <span>{syncState.step || t('linkedin.genericError')}</span>
            </div>
          )}
          {needsLogin && (
            <p className="text-xs text-gray-400">
              {t('linkedin.loginTip')}
            </p>
          )}

          {(isDone || isError) && syncState.processed > 0 && (
            <div className="flex gap-2 flex-wrap">
              {[
                { n: syncState.processed, label: t('linkedin.statFound'), cls: 'bg-gray-50 text-gray-600' },
                { n: syncState.created, label: t('linkedin.statNew'), cls: 'bg-indigo-50 text-indigo-700' },
                { n: syncState.updated, label: t('linkedin.statUpdated'), cls: 'bg-blue-50 text-blue-700' },
                { n: syncState.skipped, label: t('linkedin.statUnchanged'), cls: 'bg-gray-50 text-gray-400' },
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
                {t('linkedin.actionLog', { count: syncState.log.filter(e => e.aktion !== 'unverändert').length })}
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
                        {entry.aktion === 'aktualisiert' && entry.von && entry.zu && <span className="text-gray-400">{t('linkedin.logUpdateArrow', { from: entry.von, to: entry.zu })}</span>}
                        {entry.aktion === 'abgesagt' && entry.von && <span className="text-gray-400">{t('linkedin.logWasRejected', { from: entry.von })}</span>}
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
                {t('linkedin.unchangedCount', { count: syncState.log.filter(e => e.aktion === 'unverändert').length })}
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
              <summary className="cursor-pointer text-gray-500 hover:text-gray-700">{t('linkedin.errorsCount', { count: syncState.errors.length })}</summary>
              <ul className="mt-1 space-y-0.5 ml-2">{syncState.errors.map((e, i) => <li key={i}>{e}</li>)}</ul>
            </details>
          )}
        </div>
      )}

      {/* Message import (CSV, replaces the removed live inbox scraper) */}
      <div className="space-y-3 border-t border-gray-100 pt-4">
        <h4 className="text-xs font-semibold text-gray-700">{t('linkedin.messagesTitle')}</h4>
        <p className="text-xs text-gray-500">{t('linkedin.messagesHint')}</p>

        {messagesError && (
          <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-100 px-3 py-2 text-xs text-red-700">
            <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
            {messagesError}
          </div>
        )}

        {messagesResult && (
          <div className="flex gap-2 flex-wrap">
            {[
              { n: messagesResult.conversations_imported, label: t('linkedin.messagesStatNew'), cls: 'bg-indigo-50 text-indigo-700' },
              { n: messagesResult.conversations_updated, label: t('linkedin.messagesStatUpdated'), cls: 'bg-blue-50 text-blue-700' },
              { n: messagesResult.events_created, label: t('linkedin.messagesStatEvents'), cls: 'bg-green-50 text-green-700' },
            ].filter(x => x.n > 0).map(x => (
              <div key={x.label} className={`flex flex-col items-center px-2.5 py-1 rounded-lg ${x.cls}`}>
                <span className="text-base font-bold leading-tight">{x.n}</span>
                <span className="text-[10px] font-medium">{x.label}</span>
              </div>
            ))}
            {messagesResult.errors.length > 0 && (
              <details className="text-xs text-red-600 w-full">
                <summary className="cursor-pointer text-gray-500 hover:text-gray-700">{t('linkedin.errorsCount', { count: messagesResult.errors.length })}</summary>
                <ul className="mt-1 space-y-0.5 ml-2">{messagesResult.errors.map((e, i) => <li key={i}>{e}</li>)}</ul>
              </details>
            )}
          </div>
        )}

        {messagesStatus && messagesStatus.conversation_count > 0 && (
          <div className="flex items-center justify-between rounded-lg border border-gray-200 px-3 py-2">
            <div className="flex items-center gap-2 min-w-0">
              <FileText className="h-4 w-4 text-gray-400 shrink-0" />
              <p className="text-xs text-gray-600">
                {t('linkedin.messagesImportedCount', { count: messagesStatus.conversation_count })}
                {messagesStatus.last_imported_at ? t('linkedin.messagesLastImportedSuffix', { date: formatDateTime(messagesStatus.last_imported_at, locale) }) : ''}
              </p>
            </div>
          </div>
        )}

        <label className="flex flex-col items-center justify-center gap-1.5 rounded-lg border-2 border-dashed border-gray-200 px-3 py-5 text-xs text-gray-400 cursor-pointer hover:border-[#0077B5]/40 hover:text-[#0077B5]">
          {messagesUploading ? <Loader className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
          {messagesUploading
            ? t('linkedin.messagesUploading')
            : (messagesStatus && messagesStatus.conversation_count > 0 ? t('linkedin.messagesReupload') : t('linkedin.messagesUploadPrompt'))}
          <input
            type="file" accept=".csv" className="hidden" disabled={messagesUploading}
            onChange={e => { const f = e.target.files?.[0]; if (f) uploadMessages(f); e.target.value = '' }}
          />
        </label>
      </div>
    </div>
  )
}

function BackupPanel() {
  const { t } = useTranslation(['settings', 'common'])
  const locale = useLocale()
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
  const [pickingFile, setPickingFile] = useState(false)
  const [pickedFilePath, setPickedFilePath] = useState<string | null>(null)
  const [manualRestoring, setManualRestoring] = useState(false)
  const [manualRestoreConfirm, setManualRestoreConfirm] = useState(false)
  const [manualRestoreResult, setManualRestoreResult] = useState<string | null>(null)
  const [manualError, setManualError] = useState<string | null>(null)

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

  async function pickFile() {
    setPickingFile(true); setManualError(null); setManualRestoreResult(null)
    try {
      const r = await api.backup.pickFile()
      setPickedFilePath(r.path)
    } catch (e) {
      setManualError(e instanceof Error ? e.message : String(e))
    } finally { setPickingFile(false) }
  }

  async function doManualRestore() {
    if (!pickedFilePath) return
    setManualRestoring(true); setManualRestoreConfirm(false); setManualError(null); setManualRestoreResult(null)
    try {
      const r = await api.backup.restoreFromFile(pickedFilePath)
      setManualRestoreResult(r.filename)
      setPickedFilePath(null)
    } catch (e) {
      setManualError(e instanceof Error ? e.message : String(e))
    } finally { setManualRestoring(false) }
  }

  const fmtDate = (ts?: string | number) => {
    if (!ts) return t('shared.never')
    const d = typeof ts === 'number' ? new Date(ts * 1000) : new Date(ts)
    return formatDateTime(d, locale, { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
  }

  const fmtSize = (bytes: number) =>
    bytes > 1_000_000 ? `${(bytes / 1_000_000).toFixed(1)} MB` : `${(bytes / 1024).toFixed(0)} KB`

  const FREQUENCY_OPTIONS = [
    { value: 1,   label: t('backup.frequencyHourly') },
    { value: 6,   label: t('backup.frequencyEvery6h') },
    { value: 12,  label: t('backup.frequencyEvery12h') },
    { value: 24,  label: t('backup.frequencyDaily') },
    { value: 168, label: t('backup.frequencyWeekly') },
  ]

  return (
    <div className="space-y-5">
      <div className="rounded-lg bg-gray-50 border border-gray-100 p-4 space-y-1.5 text-xs text-gray-600">
        <div className="flex items-center gap-2 font-semibold text-gray-800" data-testid="backup-panel-title">
          <Database className="h-4 w-4 text-indigo-500" />
          {t('backup.title')}
        </div>
        <p>{t('backup.description')}</p>
      </div>

      {/* Enable toggle */}
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-gray-700">{t('backup.autoBackup')}</span>
        <button onClick={toggleEnabled}
          className={clsx('relative inline-flex h-5 w-9 items-center rounded-full transition-colors',
            status?.enabled ? 'bg-indigo-600' : 'bg-gray-200')}>
          <span className={clsx('inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform',
            status?.enabled ? 'translate-x-4.5' : 'translate-x-0.5')} />
        </button>
      </div>

      {/* Backup folder */}
      <div className="space-y-1.5">
        <label className="text-xs font-medium text-gray-700">{t('backup.backupFolder')}</label>
        <div className="flex gap-2">
          <input
            type="text"
            value={folder}
            onChange={e => setFolder(e.target.value)}
            placeholder={t('backup.backupFolderPlaceholder')}
            data-testid="backup-folder-input"
            className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
          />
          <button
            onClick={pickFolder}
            disabled={pickingFolder}
            title={t('backup.chooseFolderTitle')}
            className="shrink-0 flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-2 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            {pickingFolder ? <Loader className="h-3.5 w-3.5 animate-spin" /> : <FolderOpen className="h-3.5 w-3.5 text-indigo-500" />}
            {t('backup.choose')}
          </button>
        </div>
      </div>

      {/* Frequency + Keep count */}
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-gray-700">{t('backup.frequency')}</label>
          <select value={frequencyHours} onChange={e => setFrequencyHours(Number(e.target.value))}
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300">
            {FREQUENCY_OPTIONS.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-gray-700">{t('backup.keepCount')}</label>
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
        <button onClick={() => save()} disabled={saving} data-testid="backup-save-button"
          className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50">
          {saving ? <Loader className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
          {saved ? t('common:saved') : t('common:save')}
        </button>
        <button onClick={runNow} disabled={running || !folder.trim()} data-testid="backup-now-button"
          className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-40">
          {running ? <Loader className="h-3.5 w-3.5 animate-spin" /> : <Database className="h-3.5 w-3.5" />}
          {t('backup.backupNow')}
        </button>
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-100 px-3 py-2 text-xs text-red-700">
          <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
          {error}
        </div>
      )}
      {runResult && (
        <div className="flex items-center gap-2 text-xs text-green-700" data-testid="backup-run-result">
          <CheckCircle className="h-3.5 w-3.5" />
          {t('backup.backupCreated', { filename: runResult })}
        </div>
      )}

      {restoreResult && (
        <div className="flex items-start gap-2 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-800" data-testid="backup-restore-result">
          <CheckCircle className="h-3.5 w-3.5 mt-0.5 shrink-0 text-amber-600" />
          <span>{t('backup.restoredFromPrefix')} <strong>{restoreResult}</strong> {t('backup.restoredFromSuffix')}</span>
        </div>
      )}

      {restoreConfirm && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2.5 space-y-2">
          <p className="text-xs font-semibold text-red-800" data-testid="backup-restore-confirm-title">{t('backup.confirmRestoreTitle')}</p>
          <p className="text-xs text-red-700">{t('backup.confirmRestoreTextPrefix')} <strong>{restoreConfirm}</strong> {t('backup.confirmRestoreTextSuffix')}</p>
          <div className="flex gap-2">
            <button onClick={() => doRestore(restoreConfirm)} data-testid="backup-restore-confirm-yes"
              className="rounded-lg bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700">
              {t('backup.yesRestore')}
            </button>
            <button onClick={() => setRestoreConfirm(null)}
              className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50">
              {t('common:cancel')}
            </button>
          </div>
        </div>
      )}

      {/* Manuelle Wiederherstellung — unabhängig von automatischem Backup/backup_folder */}
      <div className="border-t border-gray-100 pt-4 space-y-2">
        <div className="text-xs font-medium text-gray-700">{t('backup.manualRestoreTitle')}</div>
        <p className="text-xs text-gray-400">
          {t('backup.manualRestoreHint')}
        </p>
        <div className="flex gap-2">
          <button onClick={pickFile} disabled={pickingFile}
            className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50">
            {pickingFile ? <Loader className="h-3.5 w-3.5 animate-spin" /> : <FolderOpen className="h-3.5 w-3.5 text-indigo-500" />}
            {t('backup.chooseFile')}
          </button>
          {pickedFilePath && (
            <button onClick={() => setManualRestoreConfirm(true)} disabled={manualRestoring}
              className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-red-50 hover:border-red-200 hover:text-red-700 disabled:opacity-50">
              {manualRestoring ? <Loader className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />}
              {t('backup.restore')}
            </button>
          )}
        </div>
        {pickedFilePath && (
          <p className="text-xs text-gray-500 font-mono truncate">{pickedFilePath}</p>
        )}
        {manualError && (
          <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-100 px-3 py-2 text-xs text-red-700">
            <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
            {manualError}
          </div>
        )}
        {manualRestoreResult && (
          <div className="flex items-start gap-2 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-800">
            <CheckCircle className="h-3.5 w-3.5 mt-0.5 shrink-0 text-amber-600" />
            <span>{t('backup.restoredFromPrefix')} <strong>{manualRestoreResult}</strong> {t('backup.restoredFromSuffix')}</span>
          </div>
        )}
        {manualRestoreConfirm && pickedFilePath && (
          <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2.5 space-y-2">
            <p className="text-xs font-semibold text-red-800">{t('backup.confirmRestoreTitle')}</p>
            <p className="text-xs text-red-700">{t('backup.confirmRestoreTextManual')}</p>
            <div className="flex gap-2">
              <button onClick={doManualRestore}
                className="rounded-lg bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700">
                {t('backup.yesRestore')}
              </button>
              <button onClick={() => setManualRestoreConfirm(false)}
                className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50">
                {t('common:cancel')}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Existing backups */}
      {status && status.backups.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-xs font-medium text-gray-700" data-testid="backup-existing-title">{t('backup.existingBackups', { count: status.backups.length })}</div>
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
                  data-testid="backup-restore-button"
                  className="shrink-0 flex items-center gap-1 rounded-lg border border-gray-200 px-2 py-1 text-xs text-gray-600 hover:bg-red-50 hover:border-red-200 hover:text-red-700 disabled:opacity-50"
                >
                  {restoring === b.name
                    ? <Loader className="h-3 w-3 animate-spin" />
                    : <RotateCcw className="h-3 w-3" />}
                  {t('backup.restoreButton')}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {status?.last_backup && (
        <div className="text-xs text-gray-400">{t('backup.lastBackup', { date: fmtDate(status.last_backup) })}</div>
      )}
    </div>
  )
}

function AccountPanel() {
  const { t } = useTranslation(['settings', 'common'])
  const locale = useLocale()
  const { user, logout, refreshUser } = useAuth()
  const [oldPassword, setOldPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)

  const [vorname, setVorname] = useState('')
  const [nachname, setNachname] = useState('')
  const [linkedinUrl, setLinkedinUrl] = useState('')
  const [profileError, setProfileError] = useState<string | null>(null)
  const [profileSaving, setProfileSaving] = useState(false)
  const [profileSaved, setProfileSaved] = useState(false)
  const [cvUploading, setCvUploading] = useState(false)
  const [cvError, setCvError] = useState<string | null>(null)
  const [profileSyncing, setProfileSyncing] = useState(false)
  const [profileSyncError, setProfileSyncError] = useState<string | null>(null)

  const [uiLanguage, setUiLanguage] = useState<SupportedLanguage>('en')
  const [languageError, setLanguageError] = useState<string | null>(null)
  const [languageSaving, setLanguageSaving] = useState(false)
  const [languageSaved, setLanguageSaved] = useState(false)

  useEffect(() => {
    setVorname(user?.vorname ?? '')
    setNachname(user?.nachname ?? '')
    setLinkedinUrl(user?.linkedin_url ?? '')
    if (user?.ui_language === 'de' || user?.ui_language === 'en') setUiLanguage(user.ui_language)
  }, [user])

  async function saveProfile() {
    setProfileError(null)
    setProfileSaving(true)
    try {
      await api.auth.updateProfile(vorname, nachname, linkedinUrl)
      await refreshUser()
      setProfileSaved(true)
      setTimeout(() => setProfileSaved(false), 2000)
    } catch (e: unknown) {
      setProfileError(e instanceof Error ? e.message : String(e))
    } finally {
      setProfileSaving(false)
    }
  }

  async function syncLinkedinProfile() {
    setProfileSyncError(null)
    setProfileSyncing(true)
    try {
      await api.linkedin.syncOwnProfile()
      await refreshUser()
    } catch (e: unknown) {
      setProfileSyncError(e instanceof Error ? e.message : String(e))
    } finally {
      setProfileSyncing(false)
    }
  }

  async function saveLanguage() {
    setLanguageError(null)
    setLanguageSaving(true)
    try {
      // Sends the current profile fields alongside the language so this save
      // doesn't rely on the backend's "only overwrite if provided" behavior
      // for ui_language while still reflecting the profile section's own state.
      await api.auth.updateProfile(vorname, nachname, linkedinUrl, uiLanguage)
      await refreshUser()
      setLanguageSaved(true)
      setTimeout(() => setLanguageSaved(false), 2000)
    } catch (e: unknown) {
      setLanguageError(e instanceof Error ? e.message : String(e))
    } finally {
      setLanguageSaving(false)
    }
  }

  async function uploadCv(file: File) {
    setCvError(null)
    setCvUploading(true)
    try {
      await api.auth.uploadCv(file)
      await refreshUser()
    } catch (e: unknown) {
      setCvError(e instanceof Error ? e.message : String(e))
    } finally {
      setCvUploading(false)
    }
  }

  async function deleteCv() {
    setCvError(null)
    try {
      await api.auth.deleteCv()
      await refreshUser()
    } catch (e: unknown) {
      setCvError(e instanceof Error ? e.message : String(e))
    }
  }

  async function changePassword() {
    setError(null)
    if (newPassword.length < 8) {
      setError(t('account.passwordTooShort'))
      return
    }
    if (newPassword !== confirm) {
      setError(t('account.passwordMismatch'))
      return
    }
    setSaving(true)
    try {
      await api.auth.changePassword(oldPassword, newPassword)
      setOldPassword('')
      setNewPassword('')
      setConfirm('')
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-sm font-semibold text-gray-800 mb-1">{t('account.title')}</h3>
        <p className="text-xs text-gray-400">{t('account.loggedInAs')}</p>
        <p className="text-sm text-gray-800 font-medium mt-0.5">{user?.email}</p>
      </div>

      <div className="space-y-3 border-t border-gray-100 pt-4">
        <h4 className="text-xs font-semibold text-gray-700">{t('account.profile')}</h4>
        {profileError && (
          <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-100 px-3 py-2 text-xs text-red-700">
            <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
            {profileError}
          </div>
        )}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">{t('account.firstName')}</label>
            <input
              type="text" value={vorname} onChange={e => setVorname(e.target.value)}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">{t('account.lastName')}</label>
            <input
              type="text" value={nachname} onChange={e => setNachname(e.target.value)}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">{t('account.linkedinProfile')}</label>
          <input
            type="text" value={linkedinUrl} onChange={e => setLinkedinUrl(e.target.value)}
            placeholder="https://www.linkedin.com/in/..."
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        {user?.linkedin_url && (
          <div className="flex items-center justify-between rounded-lg border border-gray-200 px-3 py-2">
            <div className="flex items-center gap-2 min-w-0">
              <Linkedin className="h-4 w-4 text-gray-400 shrink-0" />
              <p className="text-xs text-gray-500 truncate">
                {user.linkedin_profile_synced_at
                  ? t('account.linkedinProfileSynced', { date: formatDateTime(new Date(user.linkedin_profile_synced_at), locale, { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) })
                  : t('account.linkedinProfileNotSynced')}
              </p>
            </div>
            <button
              onClick={syncLinkedinProfile}
              disabled={profileSyncing}
              title={t('account.linkedinProfileSyncButton')}
              className="flex items-center gap-1.5 shrink-0 rounded-lg text-xs font-medium px-2.5 py-1.5 text-indigo-600 hover:bg-indigo-50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {profileSyncing ? <Loader className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              {t('account.linkedinProfileSyncButton')}
            </button>
          </div>
        )}
        {profileSyncError && (
          <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-100 px-3 py-2 text-xs text-red-700">
            <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
            {profileSyncError}
          </div>
        )}
        <button
          onClick={saveProfile}
          disabled={profileSaving}
          className="flex items-center gap-1.5 rounded-lg bg-indigo-600 text-white text-xs font-medium px-3 py-2 hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {profileSaving ? <Loader className="h-3.5 w-3.5 animate-spin" /> : profileSaved ? <Check className="h-3.5 w-3.5" /> : <Save className="h-3.5 w-3.5" />}
          {profileSaved ? t('common:saved') : t('account.saveProfile')}
        </button>
      </div>

      <div className="space-y-3 border-t border-gray-100 pt-4">
        <h4 className="text-xs font-semibold text-gray-700">{t('account.language')}</h4>
        {languageError && (
          <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-100 px-3 py-2 text-xs text-red-700">
            <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
            {languageError}
          </div>
        )}
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">{t('account.uiLanguage')}</label>
          <select
            value={uiLanguage}
            onChange={e => setUiLanguage(e.target.value as SupportedLanguage)}
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            {SUPPORTED_LANGUAGES.map(lang => (
              <option key={lang} value={lang}>{LANGUAGE_NAMES[lang]}</option>
            ))}
          </select>
        </div>
        <button
          onClick={saveLanguage}
          disabled={languageSaving}
          className="flex items-center gap-1.5 rounded-lg bg-indigo-600 text-white text-xs font-medium px-3 py-2 hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {languageSaving ? <Loader className="h-3.5 w-3.5 animate-spin" /> : languageSaved ? <Check className="h-3.5 w-3.5" /> : <Save className="h-3.5 w-3.5" />}
          {languageSaved ? t('common:saved') : t('account.saveLanguage')}
        </button>
      </div>

      <div className="space-y-3 border-t border-gray-100 pt-4">
        <h4 className="text-xs font-semibold text-gray-700">{t('account.cv')}</h4>
        {cvError && (
          <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-100 px-3 py-2 text-xs text-red-700">
            <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
            {cvError}
          </div>
        )}
        {user?.cv_filename ? (
          <div className="flex items-center justify-between rounded-lg border border-gray-200 px-3 py-2">
            <div className="flex items-center gap-2 min-w-0">
              <FileText className="h-4 w-4 text-gray-400 shrink-0" />
              <div className="min-w-0">
                <p className="text-sm text-gray-800 truncate">{user.cv_filename}</p>
                <p className="text-xs text-gray-400">{((user.cv_size_bytes ?? 0) / 1024).toFixed(0)} KB</p>
              </div>
            </div>
            <div className="flex items-center gap-1 shrink-0">
              <button
                onClick={() => api.auth.downloadCv(user.cv_filename!)}
                title={t('account.download')}
                className="p-1.5 rounded-lg text-gray-400 hover:text-indigo-600 hover:bg-indigo-50"
              >
                <Download className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={deleteCv}
                title={t('common:delete')}
                className="p-1.5 rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        ) : (
          <label className="flex flex-col items-center justify-center gap-1.5 rounded-lg border-2 border-dashed border-gray-200 px-3 py-5 text-xs text-gray-400 cursor-pointer hover:border-indigo-300 hover:text-indigo-500">
            {cvUploading ? <Loader className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
            {cvUploading ? t('account.cvUploading') : t('account.cvUploadPrompt')}
            <input
              type="file" accept=".pdf,.doc,.docx" className="hidden"
              onChange={e => { const f = e.target.files?.[0]; if (f) uploadCv(f); e.target.value = '' }}
            />
          </label>
        )}
      </div>

      <div className="space-y-3 border-t border-gray-100 pt-4">
        <h4 className="text-xs font-semibold text-gray-700">{t('account.changePassword')}</h4>
        {error && (
          <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-100 px-3 py-2 text-xs text-red-700">
            <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
            {error}
          </div>
        )}
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">{t('account.currentPassword')}</label>
          <input
            type="password" value={oldPassword} onChange={e => setOldPassword(e.target.value)}
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">{t('account.newPassword')}</label>
          <input
            type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)}
            placeholder={t('account.newPasswordPlaceholder')}
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">{t('account.confirmNewPassword')}</label>
          <input
            type="password" value={confirm} onChange={e => setConfirm(e.target.value)}
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <button
          onClick={changePassword}
          disabled={saving || !oldPassword || !newPassword}
          className="flex items-center gap-1.5 rounded-lg bg-indigo-600 text-white text-xs font-medium px-3 py-2 hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {saving ? <Loader className="h-3.5 w-3.5 animate-spin" /> : saved ? <Check className="h-3.5 w-3.5" /> : <Save className="h-3.5 w-3.5" />}
          {saved ? t('common:saved') : t('account.changePassword')}
        </button>
      </div>

      <div className="border-t border-gray-100 pt-4">
        <button
          onClick={logout}
          className="text-xs text-red-500 hover:text-red-600 font-medium"
        >
          {t('account.logout')}
        </button>
      </div>
    </div>
  )
}

type Tab = 'sync' | 'ai' | 'google' | 'icloud' | 'calls' | 'files' | 'linkedin' | 'backup' | 'logos' | 'maps' | 'agent' | 'account'

const TABS: Tab[] = ['account', 'sync', 'ai', 'google', 'icloud', 'calls', 'files', 'linkedin', 'backup', 'logos', 'maps', 'agent']

function LogoPanel() {
  const { t } = useTranslation(['settings', 'common'])
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
        <h3 className="text-sm font-semibold text-gray-800 mb-1">{t('logos.title')}</h3>
        <p className="text-xs text-gray-400">
          {t('logos.description')}
        </p>
      </div>

      <div className="space-y-3">
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">
            {t('logos.publicKeyLabel')}{' '}
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
              {saved ? t('common:saved') : t('common:save')}
            </button>
          </div>
        </div>

        {logoDevKey && (
          <div className="flex items-center gap-1.5 text-xs text-emerald-600">
            <CheckCircle className="h-3.5 w-3.5" />
            {t('logos.active')}
          </div>
        )}
        {!logoDevKey && (
          <div className="flex items-center gap-1.5 text-xs text-gray-400">
            <XCircle className="h-3.5 w-3.5" />
            {t('logos.inactive')}
          </div>
        )}
      </div>
    </div>
  )
}

function MapsPanel() {
  const { t } = useTranslation(['settings', 'common'])
  const [hasKey, setHasKey] = useState(false)
  const [key, setKey] = useState('')
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.settings.getMaps().then(r => setHasKey(r.has_key)).finally(() => setLoading(false))
  }, [])

  async function save() {
    if (!key.trim()) return
    setSaving(true)
    try {
      const r = await api.settings.saveMaps(key.trim())
      setHasKey(r.has_key)
      setKey('')
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } finally {
      setSaving(false)
    }
  }

  async function clearKey() {
    await api.settings.clearMapsKey()
    setHasKey(false)
  }

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-sm font-semibold text-gray-800 mb-1">{t('maps.title')}</h3>
        <p className="text-xs text-gray-400">
          {t('maps.description')}
        </p>
      </div>

      <div className="space-y-3">
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">
            {t('maps.apiKeyLabel')}{' '}
            <a href="https://console.cloud.google.com/google/maps-apis/credentials" target="_blank" rel="noreferrer"
               className="text-indigo-500 hover:underline font-normal inline-flex items-center gap-0.5">
              Google Cloud Console <ExternalLink className="h-2.5 w-2.5" />
            </a>
          </label>
          <div className="flex gap-2">
            <input
              type="password"
              value={key}
              onChange={e => setKey(e.target.value)}
              placeholder={hasKey ? t('maps.keyStoredPlaceholder') : 'AIza…'}
              className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            <button
              onClick={save}
              disabled={saving || !key.trim()}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50 flex items-center gap-1.5"
            >
              {saved ? <Check className="h-4 w-4" /> : saving ? <Loader className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              {saved ? t('common:saved') : t('common:save')}
            </button>
          </div>
        </div>

        {!loading && hasKey && (
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5 text-xs text-emerald-600">
              <CheckCircle className="h-3.5 w-3.5" />
              {t('maps.active')}
            </div>
            <button onClick={clearKey} className="text-xs text-red-500 hover:text-red-600 whitespace-nowrap">{t('common:delete')}</button>
          </div>
        )}
        {!loading && !hasKey && (
          <div className="flex items-center gap-1.5 text-xs text-gray-400">
            <XCircle className="h-3.5 w-3.5" />
            {t('maps.inactive')}
          </div>
        )}
      </div>
    </div>
  )
}

function AgentPanel() {
  const { t } = useTranslation(['settings', 'common'])
  const [url, setUrl] = useState('')
  const [hasToken, setHasToken] = useState(false)
  const [token, setToken] = useState('')
  const [health, setHealth] = useState<AgentHealth | null>(null)
  const [loading, setLoading] = useState(true)
  const [checking, setChecking] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function refreshHealth() {
    setChecking(true)
    try {
      setHealth(await api.settings.getAgentHealth())
    } catch {
      setHealth({ reachable: false, modules: {}, error: t('agent.requestFailed') })
    } finally {
      setChecking(false)
    }
  }

  useEffect(() => {
    api.settings.getAgent().then(r => {
      setUrl(r.url ?? '')
      setHasToken(r.has_token)
    }).finally(() => setLoading(false))
    refreshHealth()
  }, [])

  async function save() {
    setSaving(true); setSaved(false); setError(null)
    try {
      const r = await api.settings.saveAgent({ url: url.trim() || null, token: token.trim() || undefined })
      setHasToken(r.has_token)
      setToken('')
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
      await refreshHealth()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  async function clearToken() {
    await api.settings.clearAgentToken()
    setHasToken(false)
    await refreshHealth()
  }

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-sm font-semibold text-gray-800 mb-1">{t('agent.title')}</h3>
        <p className="text-xs text-gray-400">
          {t('agent.description')}
        </p>
      </div>

      {/* Status */}
      <div className="rounded-lg border border-gray-100 bg-gray-50 p-3 space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-xs font-medium">
            {health?.reachable ? (
              <span className="flex items-center gap-1.5 text-emerald-600"><Wifi className="h-3.5 w-3.5" /> {t('agent.agentReachable')}</span>
            ) : (
              <span className="flex items-center gap-1.5 text-red-500"><WifiOff className="h-3.5 w-3.5" /> {t('agent.agentNotReachable')}</span>
            )}
          </div>
          <button onClick={refreshHealth} disabled={checking} title={t('agent.refreshStatusTitle')}
            className="p-1 rounded hover:bg-gray-200 text-gray-400 disabled:opacity-50">
            <RefreshCw className={clsx('h-3.5 w-3.5', checking && 'animate-spin')} />
          </button>
        </div>
        {health?.reachable && (
          <>
            <p className="text-[11px] text-gray-500">
              {t('agent.versionInfo', { version: health.version ?? '?', platform: health.platform ?? '?' })}
            </p>
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(health.modules).map(([key, mod]) => (
                <span key={key}
                  className={clsx(
                    'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium border',
                    mod.ok
                      ? 'bg-emerald-50 text-emerald-700 border-emerald-100'
                      : mod.platform_limited
                        ? 'bg-amber-50 text-amber-700 border-amber-100'
                        : 'bg-red-50 text-red-600 border-red-100',
                  )}>
                  {mod.ok ? <CheckCircle className="h-2.5 w-2.5" /> : mod.platform_limited ? <AlertTriangle className="h-2.5 w-2.5" /> : <XCircle className="h-2.5 w-2.5" />}
                  {t(`agent.module${key.charAt(0).toUpperCase()}${key.slice(1)}`, { defaultValue: key })}
                </span>
              ))}
            </div>
            {Object.values(health.modules).some(m => m.platform_limited) && (
              <p className="text-[10px] text-amber-600 mt-1">{t('agent.platformLimited')}</p>
            )}
          </>
        )}
        {!health?.reachable && health?.error && (
          <p className="text-[11px] text-red-500">{health.error}</p>
        )}
      </div>

      {/* URL override */}
      <div className="space-y-1.5">
        <label className="text-xs font-medium text-gray-700">{t('agent.urlLabel')}</label>
        <input
          type="text"
          value={url}
          onChange={e => setUrl(e.target.value)}
          placeholder={t('agent.urlPlaceholder')}
          className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
        />
      </div>

      {/* Token */}
      <div className="space-y-1.5">
        <label className="text-xs font-medium text-gray-700">{t('agent.tokenLabel')}</label>
        <div className="flex gap-2">
          <input
            type="password"
            value={token}
            onChange={e => setToken(e.target.value)}
            placeholder={hasToken ? t('agent.tokenStoredPlaceholder') : t('agent.tokenPlaceholder')}
            className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-300"
          />
          <button
            onClick={save}
            disabled={saving || loading}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50 flex items-center gap-1.5"
          >
            {saved ? <Check className="h-4 w-4" /> : saving ? <Loader className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            {saved ? t('common:saved') : t('common:save')}
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-100 px-3 py-2 text-xs text-red-700">
          <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
          {error}
        </div>
      )}

      {!loading && hasToken && (
        <button onClick={clearToken} className="text-xs text-red-500 hover:text-red-600">{t('agent.deleteToken')}</button>
      )}
    </div>
  )
}

export function SettingsModal({ onClose, onReviewOpen }: Props) {
  const { t } = useTranslation('settings')
  const [tab, setTab] = useState<Tab>('sync')

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="w-full max-w-2xl rounded-2xl bg-white shadow-2xl flex flex-col max-h-[90vh]">

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100 shrink-0">
          <h2 className="text-sm font-semibold text-gray-800">{t('title')}</h2>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-gray-100 text-gray-400">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body: sidebar + content */}
        <div className="flex flex-1 min-h-0">
          {/* Sidebar */}
          <nav className="w-36 shrink-0 border-r border-gray-100 py-2 flex flex-col gap-0.5 overflow-y-auto">
            {TABS.map(tb => (
              <button key={tb} onClick={() => setTab(tb)}
                data-testid={`settings-tab-${tb}`}
                className={clsx(
                  'w-full text-left px-4 py-2 text-xs font-medium transition-colors rounded-none',
                  tab === tb
                    ? 'bg-indigo-50 text-indigo-700 border-r-2 border-indigo-500'
                    : 'text-gray-600 hover:bg-gray-50'
                )}>
                {t(`tabs.${tb}`)}
              </button>
            ))}
          </nav>

          {/* Content */}
          <div className="flex-1 overflow-y-auto p-6 min-w-0">
            {tab === 'account'  && <AccountPanel />}
            {tab === 'sync'     && <SyncControlPanel />}
            {tab === 'ai'       && <AiPanel />}
            {tab === 'google'   && <GoogleSyncPanel />}
            {tab === 'icloud'   && <ICloudSyncPanel />}
            {tab === 'calls'    && <CallsPanel />}
            {tab === 'files'    && <FilesPanel />}
            {tab === 'linkedin' && <LinkedInPanel onSynced={() => { onClose(); onReviewOpen?.() }} />}
            {tab === 'backup'     && <BackupPanel />}
            {tab === 'logos'      && <LogoPanel />}
            {tab === 'maps'       && <MapsPanel />}
            {tab === 'agent'      && <AgentPanel />}
          </div>
        </div>
      </div>
    </div>
  )
}
