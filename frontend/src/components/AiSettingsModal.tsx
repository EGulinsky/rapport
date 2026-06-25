import { useState, useEffect, useCallback } from 'react'
import { X, CheckCircle, XCircle, Loader, Eye, EyeOff, ExternalLink, Download, Check } from 'lucide-react'
import { api } from '../api/client'
import type { AiSettingsWrite } from '../types'
import clsx from 'clsx'

interface Props { onClose: () => void }

const PROVIDERS = [
  {
    id: 'groq',
    name: 'Groq',
    badge: 'kostenlos',
    badgeColor: 'bg-green-100 text-green-700',
    model: 'groq/llama-3.3-70b-versatile',
    keyPlaceholder: 'gsk_...',
    keyUrl: 'https://console.groq.com/keys',
    needsUrl: false,
  },
  {
    id: 'anthropic',
    name: 'Anthropic Claude',
    badge: 'kostenpflichtig',
    badgeColor: 'bg-orange-100 text-orange-700',
    model: 'anthropic/claude-haiku-4-5-20251001',
    keyPlaceholder: 'sk-ant-...',
    keyUrl: 'https://console.anthropic.com',
    needsUrl: false,
  },
  {
    id: 'openai',
    name: 'OpenAI',
    badge: 'kostenpflichtig',
    badgeColor: 'bg-orange-100 text-orange-700',
    model: 'gpt-4o-mini',
    keyPlaceholder: 'sk-...',
    keyUrl: 'https://platform.openai.com/api-keys',
    needsUrl: false,
  },
  {
    id: 'gemini',
    name: 'Google Gemini',
    badge: 'kostenlos',
    badgeColor: 'bg-green-100 text-green-700',
    model: 'gemini/gemini-2.0-flash',
    keyPlaceholder: 'AIza...',
    keyUrl: 'https://aistudio.google.com/app/apikey',
    needsUrl: false,
  },
  {
    id: 'ollama',
    name: 'Ollama',
    badge: 'offline',
    badgeColor: 'bg-yellow-100 text-yellow-700',
    model: 'ollama/llama3.2',
    keyPlaceholder: '',
    keyUrl: 'https://ollama.com',
    needsUrl: true,
    defaultUrl: 'http://host.docker.internal:11434',
  },
] as const

interface OllamaModel {
  name: string
  display: string
  params: string
  size_gb: number
}

const POPULAR_OLLAMA_MODELS: OllamaModel[] = [
  { name: 'llama3.2',       display: 'Llama 3.2',    params: '3B',   size_gb: 2.0 },
  { name: 'llama3.2:1b',   display: 'Llama 3.2',    params: '1B',   size_gb: 0.8 },
  { name: 'llama3.1:8b',   display: 'Llama 3.1',    params: '8B',   size_gb: 4.7 },
  { name: 'qwen2.5:7b',    display: 'Qwen 2.5',     params: '7B',   size_gb: 4.4 },
  { name: 'qwen2.5:14b',   display: 'Qwen 2.5',     params: '14B',  size_gb: 9.0 },
  { name: 'mistral',        display: 'Mistral',       params: '7B',   size_gb: 4.1 },
  { name: 'mistral-nemo',  display: 'Mistral Nemo',  params: '12B',  size_gb: 7.1 },
  { name: 'phi4-mini',     display: 'Phi-4 Mini',    params: '3.8B', size_gb: 2.5 },
  { name: 'phi4',           display: 'Phi-4',         params: '14B',  size_gb: 9.1 },
  { name: 'gemma3:4b',     display: 'Gemma 3',       params: '4B',   size_gb: 3.3 },
  { name: 'gemma3:12b',    display: 'Gemma 3',       params: '12B',  size_gb: 8.1 },
  { name: 'deepseek-r1:7b', display: 'DeepSeek-R1', params: '7B',   size_gb: 4.7 },
]

interface PullProgress {
  model: string
  status: string
  pct: number | null
}

export function AiSettingsModal({ onClose }: Props) {
  const [form, setForm] = useState<AiSettingsWrite>({
    provider: 'groq',
    model: 'groq/llama-3.3-70b-versatile',
    api_key: '',
    base_url: '',
    enabled: true,
  })
  const [hasStoredKey, setHasStoredKey] = useState(false)
  const [showKey, setShowKey] = useState(false)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null)
  const [saveResult, setSaveResult] = useState<'saving' | 'saved' | 'error' | null>(null)
  const [loading, setLoading] = useState(true)

  // Ollama model picker state
  const [ollamaReachable, setOllamaReachable] = useState<boolean | null>(null)
  const [ollamaInstalled, setOllamaInstalled] = useState<string[]>([])
  const [loadingModels, setLoadingModels] = useState(false)
  const [pulling, setPulling] = useState<PullProgress | null>(null)

  useEffect(() => {
    api.settings.getAi().then(data => {
      setForm({
        provider: data.provider,
        model: data.model,
        api_key: '',
        base_url: data.base_url ?? '',
        enabled: data.enabled,
      })
      setHasStoredKey(data.has_key)
    }).finally(() => setLoading(false))
  }, [])

  const provider = PROVIDERS.find(p => p.id === form.provider) ?? PROVIDERS[0]

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

  // Load installed models when modal opens with Ollama selected
  useEffect(() => {
    if (form.provider === 'ollama' && !loading) {
      loadOllamaModels(form.base_url || 'http://host.docker.internal:11434')
    }
  }, [loading]) // only on initial load — selectProvider handles the rest

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

  function selectProvider(p: typeof PROVIDERS[number]) {
    const defaultUrl = 'defaultUrl' in p ? p.defaultUrl : 'http://host.docker.internal:11434'
    const baseUrl = p.needsUrl ? (form.base_url || defaultUrl) : ''
    const patch = { provider: p.id, model: p.model, base_url: baseUrl }
    setForm(f => ({ ...f, ...patch }))
    setTestResult(null)
    autoSave(patch)
    if (p.needsUrl) {
      loadOllamaModels(baseUrl)
    }
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
            if (d.status === 'error') {
              setPulling({ model: modelName, status: `Fehler: ${d.error}`, pct: null })
              return
            }
            if (d.status === 'done' || d.status === 'success') {
              setPulling(null)
              loadOllamaModels(form.base_url || 'http://host.docker.internal:11434')
              // Auto-select newly downloaded model
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
      if (pulling?.model === modelName) setPulling(null)
    }
  }

  async function saveApiKey() {
    setSaving(true)
    try {
      await autoSave({}, form)
      setForm(f => ({ ...f, api_key: '' }))
    } finally {
      setSaving(false)
    }
  }

  async function test() {
    setTesting(true)
    setTestResult(null)
    try {
      const payload: AiSettingsWrite = {
        ...form,
        api_key: form.api_key?.trim() || undefined,
        base_url: form.base_url?.trim() || undefined,
      }
      const r = await api.settings.testAi(payload)
      setTestResult({ ok: true, msg: `Verbindung OK — Anbieter antwortet (${r.message})` })
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      setTestResult({ ok: false, msg })
    } finally {
      setTesting(false)
    }
  }

  async function clearKey() {
    await api.settings.clearAiKey()
    setHasStoredKey(false)
  }

  const selectedModelBase = form.model.replace(/^ollama\//, '')

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="w-full max-w-lg rounded-2xl bg-white shadow-2xl flex flex-col max-h-[90vh]">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div>
            <h2 className="text-base font-semibold text-gray-900">KI-Einstellungen</h2>
            <p className="text-xs text-gray-500 mt-0.5">Änderungen werden automatisch gespeichert</p>
          </div>
          <div className="flex items-center gap-3">
            {saveResult === 'saving' && <Loader className="h-4 w-4 animate-spin text-gray-400" />}
            {saveResult === 'saved' && <CheckCircle className="h-4 w-4 text-green-500" />}
            {saveResult === 'error' && <XCircle className="h-4 w-4 text-red-500" />}
            <button onClick={onClose} className="p-1 rounded-lg hover:bg-gray-100 text-gray-400">
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        {loading ? (
          <div className="p-8 text-center text-gray-400 text-sm">Lädt…</div>
        ) : (
          <div className="overflow-y-auto flex-1 p-6 space-y-5">

            {/* Enabled toggle */}
            <label className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-700">KI-Analyse aktiviert</span>
              <button
                type="button"
                onClick={() => {
                  const patch = { enabled: !form.enabled }
                  setForm(f => ({ ...f, ...patch }))
                  autoSave(patch)
                }}
                className={clsx(
                  'relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500',
                  form.enabled ? 'bg-indigo-600' : 'bg-gray-200'
                )}
              >
                <span className={clsx(
                  'inline-block h-4 w-4 rounded-full bg-white shadow transition-transform',
                  form.enabled ? 'translate-x-6' : 'translate-x-1'
                )} />
              </button>
            </label>

            {/* Provider selector */}
            <div>
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Anbieter</p>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                {PROVIDERS.map(p => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => selectProvider(p)}
                    className={clsx(
                      'flex flex-col items-start rounded-xl border p-3 text-left transition-all',
                      form.provider === p.id
                        ? 'border-indigo-500 ring-2 ring-indigo-200 bg-indigo-50'
                        : 'border-gray-200 hover:border-gray-300 bg-white'
                    )}
                  >
                    <span className="text-sm font-medium text-gray-800">{p.name}</span>
                    <span className={clsx('mt-1 text-xs px-1.5 py-0.5 rounded-full font-medium', p.badgeColor)}>
                      {p.badge}
                    </span>
                  </button>
                ))}
              </div>
            </div>

            {/* Ollama: Base URL + Model Picker */}
            {provider.needsUrl && (
              <>
                <div>
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">Base URL</p>
                  <input
                    className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    placeholder="http://host.docker.internal:11434"
                    value={form.base_url ?? ''}
                    onChange={e => setForm(f => ({ ...f, base_url: e.target.value }))}
                    onBlur={() => {
                      autoSave({ base_url: form.base_url })
                      loadOllamaModels(form.base_url || 'http://host.docker.internal:11434')
                    }}
                  />
                  <p className="mt-1 text-xs text-gray-400">Mac-Host aus Docker: <code className="bg-gray-100 px-1 rounded">host.docker.internal:11434</code></p>
                </div>

                {/* Ollama model picker */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Modell</p>
                    {ollamaReachable === false && (
                      <span className="text-xs text-red-500">Ollama nicht erreichbar</span>
                    )}
                    {loadingModels && (
                      <Loader className="h-3.5 w-3.5 animate-spin text-gray-400" />
                    )}
                  </div>

                  {/* Installed models */}
                  {ollamaInstalled.length > 0 && (
                    <div className="mb-3">
                      <p className="text-xs text-gray-400 mb-1.5">Installiert</p>
                      <div className="flex flex-wrap gap-2">
                        {ollamaInstalled.map(name => (
                          <button
                            key={name}
                            type="button"
                            onClick={() => selectOllamaModel(name)}
                            className={clsx(
                              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-sm font-medium transition-all',
                              selectedModelBase === name
                                ? 'border-indigo-500 bg-indigo-50 text-indigo-700 ring-2 ring-indigo-200'
                                : 'border-gray-200 bg-white text-gray-700 hover:border-gray-300'
                            )}
                          >
                            {selectedModelBase === name && <Check className="h-3.5 w-3.5" />}
                            {name}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Popular models to download */}
                  {POPULAR_OLLAMA_MODELS.length > 0 && (
                    <div>
                      <p className="text-xs text-gray-400 mb-1.5">Verfügbar zum Download</p>
                      <div className="space-y-1.5 max-h-52 overflow-y-auto pr-1">
                        {POPULAR_OLLAMA_MODELS
                          .filter(m => !ollamaInstalled.some(i => i === m.name || i.startsWith(m.name + ':')))
                          .map(m => {
                            const isPulling = pulling?.model === m.name
                            return (
                              <div
                                key={m.name}
                                className="flex items-center justify-between rounded-lg border border-gray-100 bg-gray-50 px-3 py-2 gap-3"
                              >
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
                                          <div
                                            className="h-full bg-indigo-500 rounded-full transition-all duration-300"
                                            style={{ width: `${(pulling.pct * 100).toFixed(0)}%` }}
                                          />
                                        </div>
                                      )}
                                    </div>
                                  )}
                                </div>
                                <button
                                  type="button"
                                  disabled={!!pulling}
                                  onClick={() => pullModel(m.name)}
                                  className={clsx(
                                    'flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium transition-colors shrink-0',
                                    isPulling
                                      ? 'bg-indigo-100 text-indigo-500 cursor-wait'
                                      : pulling
                                        ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                                        : 'bg-indigo-600 text-white hover:bg-indigo-700'
                                  )}
                                >
                                  {isPulling
                                    ? <Loader className="h-3 w-3 animate-spin" />
                                    : <Download className="h-3 w-3" />}
                                  {isPulling ? 'Lädt…' : 'Herunterladen'}
                                </button>
                              </div>
                            )
                          })}
                      </div>
                    </div>
                  )}

                  {/* Manual model input always shown */}
                  <div className="mt-3">
                    <p className="text-xs text-gray-400 mb-1">Oder manuell eingeben:</p>
                    <input
                      className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      value={form.model}
                      onChange={e => setForm(f => ({ ...f, model: e.target.value }))}
                      onBlur={() => autoSave({ model: form.model })}
                      placeholder="ollama/llama3.2"
                    />
                  </div>
                </div>
              </>
            )}

            {/* Model (non-Ollama providers) */}
            {!provider.needsUrl && (
              <div>
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">Modell</p>
                <input
                  className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  value={form.model}
                  onChange={e => setForm(f => ({ ...f, model: e.target.value }))}
                  onBlur={() => autoSave({ model: form.model })}
                  placeholder="z.B. groq/llama-3.3-70b-versatile"
                />
              </div>
            )}

            {/* API Key (not for Ollama) */}
            {!provider.needsUrl && (
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">API Key</p>
                  {provider.keyUrl && (
                    <a href={provider.keyUrl} target="_blank" rel="noreferrer"
                      className="flex items-center gap-1 text-xs text-indigo-600 hover:underline">
                      Key holen <ExternalLink className="h-3 w-3" />
                    </a>
                  )}
                </div>
                {hasStoredKey && !form.api_key ? (
                  <div className="flex items-center gap-2">
                    <div className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-500 bg-gray-50">
                      ●●●●●●●●●●●● (gespeichert)
                    </div>
                    <button type="button" onClick={clearKey}
                      className="text-xs text-red-500 hover:text-red-600 whitespace-nowrap">
                      Löschen
                    </button>
                    <button type="button" onClick={() => setForm(f => ({ ...f, api_key: ' ' }))}
                      className="text-xs text-indigo-600 hover:text-indigo-700 whitespace-nowrap">
                      Ändern
                    </button>
                  </div>
                ) : (
                  <div className="flex gap-2">
                    <div className="relative flex-1">
                      <input
                        type={showKey ? 'text' : 'password'}
                        className="w-full rounded-lg border border-gray-200 px-3 py-2 pr-10 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
                        placeholder={provider.keyPlaceholder || 'API Key'}
                        value={form.api_key ?? ''}
                        onChange={e => setForm(f => ({ ...f, api_key: e.target.value }))}
                      />
                      <button type="button" onClick={() => setShowKey(s => !s)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
                        {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                    <button
                      type="button"
                      onClick={saveApiKey}
                      disabled={saving || !form.api_key?.trim()}
                      className="px-3 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-40 shrink-0"
                    >
                      {saving ? <Loader className="h-4 w-4 animate-spin" /> : 'OK'}
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Test result */}
            {testResult && (
              <div className={clsx(
                'flex items-start gap-2 rounded-lg px-3 py-2.5 text-sm',
                testResult.ok ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'
              )}>
                {testResult.ok
                  ? <CheckCircle className="h-4 w-4 mt-0.5 shrink-0" />
                  : <XCircle className="h-4 w-4 mt-0.5 shrink-0" />}
                <span>{testResult.msg}</span>
              </div>
            )}
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-gray-100 bg-gray-50 rounded-b-2xl">
          <button
            type="button"
            onClick={test}
            disabled={testing || loading}
            className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 disabled:opacity-50"
          >
            {testing ? <Loader className="h-4 w-4 animate-spin" /> : null}
            Verbindung testen
          </button>
          <button onClick={onClose} className="rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50">
            Schließen
          </button>
        </div>
      </div>
    </div>
  )
}
