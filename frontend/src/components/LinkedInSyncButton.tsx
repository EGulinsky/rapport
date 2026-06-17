import { useState, useEffect, useRef } from 'react'
import { Linkedin, Loader2, X, CheckCircle, AlertCircle, Eye, EyeOff, RefreshCw, Trash2, Sheet } from 'lucide-react'
import { api } from '../api/client'
import type { LinkedInSyncStatus, LinkedInSyncLogEntry } from '../types'

interface Props {
  onSynced: () => void
}

type View = 'config' | 'running'

export function LinkedInSyncButton({ onSynced }: Props) {
  const [showModal, setShowModal] = useState(false)
  const [view, setView] = useState<View>('config')
  const [config, setConfig] = useState<{ configured: boolean; email?: string; has_session: boolean; last_sync?: string } | null>(null)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [saving, setSaving] = useState(false)
  const [syncState, setSyncState] = useState<LinkedInSyncStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  function stopPolling() {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
  }

  async function loadConfig() {
    try {
      const c = await api.linkedin.getConfig() as { configured: boolean; email?: string; has_session: boolean; last_sync?: string }
      setConfig(c)
    } catch { /* ignore */ }
  }

  useEffect(() => {
    loadConfig()
    return () => stopPolling()
  }, [])

  async function openModal() {
    await loadConfig()
    setView('config')
    setError(null)
    setSyncState(null)
    setShowModal(true)
  }

  function closeModal() {
    stopPolling()
    setShowModal(false)
  }

  async function handleSaveConfig() {
    if (!email.trim() || !password.trim()) return
    setSaving(true)
    setError(null)
    try {
      await api.linkedin.saveConfig(email.trim(), password.trim())
      await loadConfig()
      setPassword('')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  async function handleDeleteConfig() {
    await api.linkedin.deleteConfig()
    setConfig(null)
    setEmail('')
    setPassword('')
  }

  async function handleStartSync() {
    setError(null)
    try {
      const s = await api.linkedin.run() as LinkedInSyncStatus
      setSyncState(s)
      setView('running')
      stopPolling()
      pollRef.current = setInterval(async () => {
        try {
          const s2 = await api.linkedin.status() as LinkedInSyncStatus
          setSyncState(s2)
          if (s2.status === 'done') {
            stopPolling()
            onSynced()
          } else if (s2.status === 'error' || s2.status === 'needs_login') {
            stopPolling()
          }
        } catch { /* ignore */ }
      }, 2000)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function handleClearSession() {
    await api.linkedin.clearSession()
    await loadConfig()
  }

  const isConfigured = config?.configured
  const isRunning = syncState?.status === 'running'
  const isDone = syncState?.status === 'done'
  const isError = syncState?.status === 'error'
  const needsLogin = syncState?.status === 'needs_login'

  function logLabel(e: LinkedInSyncLogEntry) {
    if (e.aktion === 'neu') return { text: 'Neu', cls: 'bg-indigo-50 text-indigo-700' }
    if (e.aktion === 'abgesagt') return { text: 'Abgesagt', cls: 'bg-red-50 text-red-700' }
    if (e.aktion === 'aktualisiert') return { text: 'Aktualisiert', cls: 'bg-blue-50 text-blue-700' }
    return { text: 'Unverändert', cls: 'bg-gray-50 text-gray-500' }
  }

  return (
    <>
      <button
        onClick={openModal}
        title="LinkedIn-Bewerbungen synchronisieren"
        className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-700 rounded-lg border border-gray-200 bg-white hover:bg-gray-50 transition-colors"
      >
        <Linkedin className="h-4 w-4 text-[#0077B5]" />
        LinkedIn
      </button>

      {showModal && (
        <div
          className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/30 p-4"
          onClick={e => e.target === e.currentTarget && closeModal()}
        >
          <div className="w-full max-w-md rounded-2xl bg-white shadow-2xl overflow-hidden">
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
              <div className="flex items-center gap-2">
                <Linkedin className="h-4 w-4 text-[#0077B5]" />
                <h2 className="text-sm font-semibold text-gray-900">LinkedIn Sync</h2>
              </div>
              <button onClick={closeModal} className="p-1 rounded-lg hover:bg-gray-100 text-gray-400">
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Body */}
            <div className="px-5 py-4 space-y-4">

              {/* ── Config view ── */}
              {view === 'config' && (
                <>
                  {isConfigured ? (
                    <div className="space-y-3">
                      <div className="flex items-center justify-between rounded-lg bg-green-50 border border-green-200 px-3 py-2">
                        <div>
                          <p className="text-xs font-medium text-green-800">{config!.email}</p>
                          <p className="text-[10px] text-green-600">
                            {config!.has_session ? 'Session aktiv' : 'Kein gespeichertes Login'}
                            {config!.last_sync ? ` · Letzter Sync: ${new Date(config!.last_sync).toLocaleDateString('de-DE')}` : ''}
                          </p>
                        </div>
                        <button onClick={handleDeleteConfig} className="p-1 text-green-400 hover:text-red-500">
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>

                      {config!.has_session && (
                        <button
                          onClick={handleClearSession}
                          className="text-xs text-gray-400 hover:text-gray-600 flex items-center gap-1"
                        >
                          <RefreshCw className="h-3 w-3" /> Session zurücksetzen (erzwingt Neu-Login)
                        </button>
                      )}

                      <p className="text-xs text-gray-500">
                        Synchronisiert deine eingereichten Bewerbungen von LinkedIn
                        ("Meine Jobs → Beworben"). Neue Bewerbungen werden angelegt,
                        bestehende Statusänderungen übernommen.
                      </p>

                      {error && <p className="text-xs text-red-600">{error}</p>}
                    </div>
                  ) : (
                    <div className="space-y-3">
                      <p className="text-xs text-gray-500">
                        Gib deine LinkedIn-Zugangsdaten ein. Das Passwort wird
                        verschlüsselt gespeichert und nur für den automatischen Login verwendet.
                      </p>
                      <div className="space-y-2">
                        <input
                          type="email"
                          placeholder="E-Mail"
                          value={email}
                          onChange={e => setEmail(e.target.value)}
                          className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#0077B5]/30"
                        />
                        <div className="relative">
                          <input
                            type={showPw ? 'text' : 'password'}
                            placeholder="Passwort"
                            value={password}
                            onChange={e => setPassword(e.target.value)}
                            onKeyDown={e => e.key === 'Enter' && handleSaveConfig()}
                            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm pr-9 focus:outline-none focus:ring-2 focus:ring-[#0077B5]/30"
                          />
                          <button
                            type="button"
                            onClick={() => setShowPw(v => !v)}
                            className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                          >
                            {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                          </button>
                        </div>
                      </div>
                      {error && <p className="text-xs text-red-600">{error}</p>}
                    </div>
                  )}
                </>
              )}

              {/* ── Running view ── */}
              {view === 'running' && syncState && (
                <div className="space-y-3">
                  {isRunning && (
                    <div className="flex items-center gap-2 text-sm text-gray-600">
                      <Loader2 className="h-4 w-4 animate-spin text-[#0077B5]" />
                      <span>{syncState.step || 'Läuft…'}</span>
                    </div>
                  )}

                  {isDone && (
                    <div className="flex items-center gap-2 text-sm text-green-700">
                      <CheckCircle className="h-4 w-4" />
                      <span>Sync abgeschlossen</span>
                    </div>
                  )}

                  {(isError || needsLogin) && (
                    <div className="flex items-start gap-2 text-sm text-red-700">
                      <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                      <span>{syncState.step || 'Unbekannter Fehler'}</span>
                    </div>
                  )}

                  {(isDone || isError) && syncState.processed > 0 && (
                    <div className="flex gap-2 flex-wrap">
                      <div className="flex flex-col items-center px-3 py-1.5 rounded-lg bg-gray-50 text-gray-600">
                        <span className="text-lg font-bold leading-tight">{syncState.processed}</span>
                        <span className="text-[10px] font-medium">Gefunden</span>
                      </div>
                      {syncState.created > 0 && (
                        <div className="flex flex-col items-center px-3 py-1.5 rounded-lg bg-indigo-50 text-indigo-700">
                          <span className="text-lg font-bold leading-tight">{syncState.created}</span>
                          <span className="text-[10px] font-medium">Neu</span>
                        </div>
                      )}
                      {syncState.updated > 0 && (
                        <div className="flex flex-col items-center px-3 py-1.5 rounded-lg bg-blue-50 text-blue-700">
                          <span className="text-lg font-bold leading-tight">{syncState.updated}</span>
                          <span className="text-[10px] font-medium">Aktualisiert</span>
                        </div>
                      )}
                      {syncState.skipped > 0 && (
                        <div className="flex flex-col items-center px-3 py-1.5 rounded-lg bg-gray-50 text-gray-500">
                          <span className="text-lg font-bold leading-tight">{syncState.skipped}</span>
                          <span className="text-[10px] font-medium">Unverändert</span>
                        </div>
                      )}
                    </div>
                  )}

                  {isDone && syncState.log && syncState.log.filter(e => e.aktion !== 'unverändert').length > 0 && (
                    <details open className="text-xs">
                      <summary className="cursor-pointer text-gray-500 hover:text-gray-700 font-medium mb-1">
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
                                {entry.rolle ? <span className="text-gray-400"> · {entry.rolle}</span> : null}
                                {entry.aktion === 'aktualisiert' && entry.von && entry.zu
                                  ? <span className="text-gray-400"> ({entry.von} → {entry.zu})</span>
                                  : null}
                                {entry.aktion === 'abgesagt' && entry.von
                                  ? <span className="text-gray-400"> (war: {entry.von})</span>
                                  : null}
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
                      <summary className="cursor-pointer text-gray-500 hover:text-gray-700">
                        {syncState.errors.length} Fehler
                      </summary>
                      <ul className="mt-1 space-y-0.5 ml-2">
                        {syncState.errors.map((e, i) => <li key={i}>{e}</li>)}
                      </ul>
                    </details>
                  )}

                  {needsLogin && (
                    <p className="text-xs text-gray-500">
                      Tipp: LinkedIn verlangt manchmal eine Verifizierung. Logge dich einmal
                      manuell auf linkedin.com ein, dann erneut versuchen.
                    </p>
                  )}
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="flex justify-end gap-2 px-5 py-3 border-t border-gray-100">
              {view === 'config' && !isConfigured && (
                <>
                  <button onClick={closeModal} className="text-xs font-medium px-3 py-1.5 rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50">
                    Abbrechen
                  </button>
                  <button
                    onClick={handleSaveConfig}
                    disabled={saving || !email.trim() || !password.trim()}
                    className="text-xs font-medium px-3 py-1.5 rounded-lg bg-[#0077B5] text-white hover:bg-[#005f91] disabled:opacity-50"
                  >
                    {saving ? 'Speichern…' : 'Speichern'}
                  </button>
                </>
              )}
              {view === 'config' && isConfigured && (
                <>
                  <button onClick={closeModal} className="text-xs font-medium px-3 py-1.5 rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50">
                    Schließen
                  </button>
                  <button
                    onClick={handleStartSync}
                    className="text-xs font-medium px-3 py-1.5 rounded-lg bg-[#0077B5] text-white hover:bg-[#005f91] flex items-center gap-1.5"
                  >
                    <Linkedin className="h-3.5 w-3.5" />
                    Jetzt synchronisieren
                  </button>
                </>
              )}
              {view === 'running' && !isRunning && (
                <>
                  {isDone && (
                    <button
                      onClick={async () => { try { await api.export.linkedinDebugExcel() } catch (e) { alert(String(e)) } }}
                      title="Debug-Excel mit allen gefundenen LI-Stellen herunterladen"
                      className="text-xs font-medium px-3 py-1.5 rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50 flex items-center gap-1.5"
                    >
                      <Sheet className="h-3.5 w-3.5 text-green-600" />
                      Debug-Excel
                    </button>
                  )}
                  <button
                    onClick={closeModal}
                    className="text-xs font-medium px-3 py-1.5 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700"
                  >
                    Schließen
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
