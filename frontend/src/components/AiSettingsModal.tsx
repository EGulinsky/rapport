import { useState, useEffect } from 'react'
import { X, CheckCircle, XCircle, Loader, Eye, EyeOff, ExternalLink } from 'lucide-react'
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
  },
] as const

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
  const [loading, setLoading] = useState(true)

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

  function selectProvider(p: typeof PROVIDERS[number]) {
    setForm(f => ({ ...f, provider: p.id, model: p.model, base_url: p.needsUrl ? (f.base_url || 'http://localhost:11434') : '' }))
    setTestResult(null)
  }

  async function save() {
    setSaving(true)
    try {
      const payload: AiSettingsWrite = {
        ...form,
        api_key: form.api_key?.trim() || undefined,
        base_url: form.base_url?.trim() || undefined,
      }
      const updated = await api.settings.saveAi(payload)
      setHasStoredKey(updated.has_key)
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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="w-full max-w-lg rounded-2xl bg-white shadow-2xl flex flex-col max-h-[90vh]">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div>
            <h2 className="text-base font-semibold text-gray-900">KI-Einstellungen</h2>
            <p className="text-xs text-gray-500 mt-0.5">Vendor-agnostische AI-Anbindung via LiteLLM</p>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-gray-100 text-gray-400">
            <X className="h-5 w-5" />
          </button>
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
                onClick={() => setForm(f => ({ ...f, enabled: !f.enabled }))}
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

            {/* Model */}
            <div>
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">Modell</p>
              <input
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
                value={form.model}
                onChange={e => setForm(f => ({ ...f, model: e.target.value }))}
                placeholder="z.B. groq/llama-3.3-70b-versatile"
              />
            </div>

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
                  <div className="relative">
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
                )}
              </div>
            )}

            {/* Base URL (Ollama / custom) */}
            {provider.needsUrl && (
              <div>
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">Base URL</p>
                <input
                  className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder="http://localhost:11434"
                  value={form.base_url ?? ''}
                  onChange={e => setForm(f => ({ ...f, base_url: e.target.value }))}
                />
                <p className="mt-1 text-xs text-gray-400">Ollama muss lokal laufen: <code className="bg-gray-100 px-1 rounded">ollama serve</code></p>
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
          <div className="flex gap-3">
            <button onClick={onClose} className="rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50">
              Schließen
            </button>
            <button
              onClick={save}
              disabled={saving || loading}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
            >
              {saving ? 'Speichern…' : 'Speichern'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
