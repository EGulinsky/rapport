import { useState, useRef, useEffect, useCallback } from 'react'
import { RefreshCw, ChevronDown, CheckCircle, AlertCircle, X, ArrowRight, Linkedin } from 'lucide-react'
import { api } from '../api/client'
import clsx from 'clsx'

interface Props {
  onSynced: () => void
  onReviewOpen?: () => void
  onLinkedIn?: () => void
}

interface SourceResult {
  label: string
  created: number
  processed: number
  skipped: number
  errors: string[]
}

interface SyncSummary {
  sources: SourceResult[]
  totalCreated: number
  newPending: number
  totalErrors: number
}

interface ProgressEntry {
  label: string
  step: string
  current: number
  total: number
  percent: number
  done: boolean
}

const SOURCE_CONFIGS: { key: string; label: string }[] = [
  { key: 'gmail',              label: 'Gmail' },
  { key: 'gcal',               label: 'Google Kalender' },
  { key: 'icloud_mail',        label: 'iCloud Mail' },
  { key: 'icloud_cal',         label: 'iCloud Kalender' },
  { key: 'icloud_notes',       label: 'iCloud Notizen' },
  { key: 'icloud_reminders',   label: 'iCloud Erinnerungen' },
  { key: 'icloud_calls',       label: 'Anrufliste' },
  { key: 'local_files',        label: 'Dokumente' },
]

export function SyncButton({ onSynced, onReviewOpen, onLinkedIn }: Props) {
  const [syncing, setSyncing] = useState(false)
  const [open, setOpen] = useState(false)
  const [summary, setSummary] = useState<SyncSummary | null>(null)
  const [progress, setProgress] = useState<Record<string, ProgressEntry>>({})
  const dropdownRef = useRef<HTMLDivElement>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  const startPolling = useCallback(() => {
    stopPolling()
    pollRef.current = setInterval(async () => {
      try {
        const data = await api.sync.progress()
        setProgress(data)
      } catch {
        // ignore polling errors
      }
    }, 1000)
  }, [stopPolling])

  async function runSync(reset: boolean) {
    setSyncing(true)
    setOpen(false)
    setSummary(null)
    setProgress({})
    startPolling()

    try {
      if (reset) {
        await Promise.allSettled([
          api.sync.resetGmailSync(),
          api.sync.resetCalendarSync(),
          api.icloud.resetMail(),
          api.icloud.resetCalendar(),
          api.icloud.resetNotes(),
          api.icloud.resetReminders(),
          api.icloud.resetCalls(),
        ])
      }

      const pendingBefore = await api.review.count().then(r => r.count).catch(() => 0)

      // Load sync settings to skip disabled sources
      const syncCfg = await api.settings.getSync().catch(() => null)
      const filesCfg = await api.settings.getFiles().catch(() => null)
      const googleOn  = syncCfg?.google_enabled  ?? true
      const icloudOn  = syncCfg?.icloud_enabled  ?? true
      const filesOn   = (syncCfg?.files_enabled ?? true) && (filesCfg?.enabled ?? false) && !!(filesCfg?.folder_path)

      // Contacts first (fast, no AI) — calls matching depends on them being present
      if (icloudOn && (syncCfg?.icloud_contacts_enabled ?? true)) {
        await api.icloud.syncContacts().catch(() => null)
      }

      // Fire all syncs as background tasks — they return immediately
      const FIRE_SOURCES = [
        { key: 'gmail',            enabled: googleOn && (syncCfg?.gmail_enabled            ?? true), fn: () => api.sync.syncGmail() },
        { key: 'gcal',             enabled: googleOn && (syncCfg?.gcal_enabled             ?? true), fn: () => api.sync.syncCalendar() },
        { key: 'icloud_mail',      enabled: icloudOn && (syncCfg?.icloud_mail_enabled      ?? true), fn: () => api.icloud.syncMail() },
        { key: 'icloud_cal',       enabled: icloudOn && (syncCfg?.icloud_cal_enabled       ?? true), fn: () => api.icloud.syncCalendar() },
        { key: 'icloud_notes',     enabled: icloudOn && (syncCfg?.icloud_notes_enabled     ?? true), fn: () => api.icloud.syncNotes() },
        { key: 'icloud_reminders', enabled: icloudOn && (syncCfg?.icloud_reminders_enabled ?? true), fn: () => api.icloud.syncReminders() },
        { key: 'icloud_calls',     enabled: icloudOn && (syncCfg?.icloud_calls_enabled     ?? true), fn: () => api.icloud.syncCalls() },
        { key: 'local_files',      enabled: filesOn,                                                  fn: () => api.files.sync() },
      ].filter(s => s.enabled)

      const startedSources = new Set<string>()
      await Promise.all(FIRE_SOURCES.map(async ({ key, fn }) => {
        try {
          await fn()
          startedSources.add(key)
        } catch {
          // source not configured or error on fire — don't wait for it
        }
      }))

      // Poll batch results until all started sources are done (max 20 min)
      let batchData: Record<string, { done: boolean; processed?: number; created?: number; skipped?: number; errors?: string[] }> = {}
      for (let i = 0; i < 600; i++) {
        await new Promise(r => setTimeout(r, 2000))
        try {
          batchData = await api.sync.batchResults()
        } catch {
          continue
        }
        if ([...startedSources].every(src => batchData[src]?.done)) break
      }

      const pendingAfter = await api.review.count().then(r => r.count).catch(() => 0)

      const sources: SourceResult[] = []
      let totalCreated = 0

      SOURCE_CONFIGS.forEach(sc => {
        const r = batchData[sc.key]
        if (r?.done) {
          const src: SourceResult = {
            label: sc.label,
            created: r.created ?? 0,
            processed: r.processed ?? 0,
            skipped: r.skipped ?? 0,
            errors: r.errors ?? [],
          }
          sources.push(src)
          totalCreated += src.created
        }
      })

      const newPending = Math.max(0, pendingAfter - pendingBefore)
      const totalErrors = sources.reduce((s, r) => s + r.errors.length, 0)

      onSynced()
      setSummary({ sources, totalCreated, newPending, totalErrors })
    } catch {
      setSummary({
        sources: [],
        totalCreated: 0,
        newPending: 0,
        totalErrors: 1,
      })
    } finally {
      stopPolling()
      setSyncing(false)
      setProgress({})
    }
  }

  const progressEntries = Object.values(progress).filter(p => p.total > 0 || p.done)

  return (
    <>
      <div className="relative" ref={dropdownRef}>
        <div className="flex rounded-lg border border-gray-200 bg-white overflow-hidden">
          <button
            onClick={() => runSync(false)}
            disabled={syncing}
            title="Alle konfigurierten Quellen synchronisieren"
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 transition-colors"
          >
            <RefreshCw className={clsx('h-4 w-4 text-indigo-500', syncing && 'animate-spin')} />
            {syncing ? 'Sync…' : 'Sync'}
          </button>
          <button
            onClick={() => setOpen(o => !o)}
            disabled={syncing}
            className="px-1.5 border-l border-gray-200 text-gray-400 hover:bg-gray-50 disabled:opacity-50 transition-colors"
          >
            <ChevronDown className={clsx('h-3.5 w-3.5 transition-transform', open && 'rotate-180')} />
          </button>
        </div>

        {open && (
          <div className="absolute right-0 top-full mt-1 z-40 w-52 rounded-lg border border-gray-200 bg-white shadow-lg py-1">
            <button
              onClick={() => { setOpen(false); runSync(false) }}
              className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-2"
            >
              <RefreshCw className="h-3.5 w-3.5 text-indigo-400" />
              Sync all
            </button>
            <button
              onClick={() => { setOpen(false); runSync(true) }}
              className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-2"
            >
              <RefreshCw className="h-3.5 w-3.5 text-amber-400" />
              <span>
                Re-sync all
                <span className="block text-xs text-gray-400">Reset + neu einlesen</span>
              </span>
            </button>
            {onLinkedIn && (
              <>
                <div className="my-1 border-t border-gray-100" />
                <button
                  onClick={() => { setOpen(false); onLinkedIn() }}
                  className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-2"
                >
                  <Linkedin className="h-3.5 w-3.5 text-blue-600" />
                  LinkedIn-Sync
                </button>
              </>
            )}
          </div>
        )}
      </div>

      {/* Progress overlay while syncing */}
      {syncing && progressEntries.length > 0 && (
        <div className="fixed bottom-6 right-6 z-50 w-80 rounded-xl border border-gray-200 bg-white shadow-2xl overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100 bg-gray-50">
            <RefreshCw className="h-3.5 w-3.5 text-indigo-500 animate-spin shrink-0" />
            <span className="text-xs font-semibold text-gray-700">Sync läuft…</span>
          </div>
          <div className="px-4 py-3 space-y-3">
            {progressEntries.map(p => (
              <ProgressRow key={p.label} entry={p} />
            ))}
          </div>
        </div>
      )}

      {summary && (
        <SyncSummaryModal
          summary={summary}
          onClose={() => setSummary(null)}
          onReviewOpen={onReviewOpen}
        />
      )}
    </>
  )
}

// ── Progress row ──────────────────────────────────────────────────────────────

function ProgressRow({ entry }: { entry: ProgressEntry }) {
  const pct = entry.done ? 100 : entry.percent
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-gray-700">{entry.label}</span>
        <span className="text-xs text-gray-400 tabular-nums">
          {entry.done ? '✓' : `${pct}%`}
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-gray-100 overflow-hidden">
        <div
          className={clsx(
            'h-full rounded-full transition-all duration-300',
            entry.done ? 'bg-green-400' : 'bg-indigo-500'
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-[10px] text-gray-400 truncate">{entry.step}</p>
    </div>
  )
}

// ── Sync summary modal ────────────────────────────────────────────────────────

function SyncSummaryModal({
  summary,
  onClose,
  onReviewOpen,
}: {
  summary: SyncSummary
  onClose: () => void
  onReviewOpen?: () => void
}) {
  const { sources, totalCreated, newPending, totalErrors } = summary

  // Only show sources that actually ran (appeared in results)
  const activeSources = sources.filter(s => s.processed > 0 || s.created > 0 || s.errors.length > 0)
  const quietSources  = sources.filter(s => s.processed === 0 && s.created === 0 && s.errors.length === 0)

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/30 p-4"
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <div className="w-full max-w-md rounded-2xl bg-white shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <div className="flex items-center gap-2">
            {totalErrors > 0
              ? <AlertCircle className="h-4 w-4 text-red-500" />
              : <CheckCircle className="h-4 w-4 text-green-500" />}
            <h2 className="text-sm font-semibold text-gray-900">Sync abgeschlossen</h2>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-gray-100 text-gray-400">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Summary chips */}
        <div className="flex gap-3 px-5 py-3 border-b border-gray-100">
          <Chip label="Neue Einträge" value={totalCreated} color="indigo" />
          {newPending > 0 && <Chip label="Zur Prüfung" value={newPending} color="amber" />}
          {totalErrors > 0 && <Chip label="Fehler" value={totalErrors} color="red" />}
          {totalCreated === 0 && newPending === 0 && totalErrors === 0 && (
            <span className="text-xs text-gray-400 self-center">Alles bereits aktuell</span>
          )}
        </div>

        {/* Per-source breakdown */}
        {activeSources.length > 0 && (
          <div className="px-5 py-3 space-y-1.5 max-h-64 overflow-y-auto">
            {activeSources.map(src => (
              <SourceRow key={src.label} src={src} />
            ))}
          </div>
        )}

        {/* Quiet sources (nothing found) */}
        {quietSources.length > 0 && (
          <div className="px-5 pb-3">
            <p className="text-xs text-gray-400">
              Keine neuen Daten:{' '}
              {quietSources.map(s => s.label).join(', ')}
            </p>
          </div>
        )}

        {/* Footer */}
        <div className="flex justify-end gap-2 px-5 py-3 border-t border-gray-100">
          {newPending > 0 && onReviewOpen && (
            <button
              onClick={() => { onClose(); onReviewOpen() }}
              className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-amber-500 text-white hover:bg-amber-600"
            >
              {newPending} prüfen
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
          )}
          <button
            onClick={onClose}
            className="text-xs font-medium px-3 py-1.5 rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50"
          >
            Schließen
          </button>
        </div>
      </div>
    </div>
  )
}

function Chip({ label, value, color }: { label: string; value: number; color: 'indigo' | 'amber' | 'red' }) {
  const colors = {
    indigo: 'bg-indigo-50 text-indigo-700',
    amber:  'bg-amber-50  text-amber-700',
    red:    'bg-red-50    text-red-700',
  }
  return (
    <div className={clsx('flex flex-col items-center px-3 py-1.5 rounded-lg', colors[color])}>
      <span className="text-lg font-bold leading-tight">{value}</span>
      <span className="text-[10px] font-medium">{label}</span>
    </div>
  )
}

function SourceRow({ src }: { src: SourceResult }) {
  const [errOpen, setErrOpen] = useState(false)
  return (
    <div className="text-xs">
      <div className="flex items-center justify-between gap-2">
        <span className="text-gray-700 font-medium">{src.label}</span>
        <div className="flex items-center gap-2 text-gray-400 shrink-0">
          {src.created > 0 && (
            <span className="font-semibold text-indigo-600">+{src.created}</span>
          )}
          <span>{src.processed} geprüft</span>
          {src.errors.length > 0 && (
            <button
              onClick={() => setErrOpen(o => !o)}
              className="text-red-500 font-medium hover:text-red-700"
            >
              {src.errors.length} Fehler
            </button>
          )}
        </div>
      </div>
      {errOpen && src.errors.length > 0 && (
        <ul className="mt-1 ml-2 space-y-0.5">
          {src.errors.map((e, i) => (
            <li key={i} className="text-red-600 leading-snug">{e}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
