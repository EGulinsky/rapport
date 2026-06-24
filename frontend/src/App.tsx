import { useState, useEffect, useCallback } from 'react'
import { Search, Plus, RefreshCw, Briefcase, Users, Settings, Sparkles } from 'lucide-react'
import { api } from './api/client'
import { ApplicationTable } from './components/ApplicationTable'
import { KanbanBoard } from './components/KanbanBoard'
import { ApplicationModal } from './components/ApplicationModal'
import { StatsBar } from './components/StatsBar'
import { ImportButton } from './components/ImportButton'
import { ExportButton } from './components/ExportButton'
import { PdfExportButton } from './components/PdfExportButton'
import { SyncButton } from './components/SyncButton'
import { LinkedInSyncButton } from './components/LinkedInSyncButton'
import { ContactsView } from './components/ContactsView'
import { CalendarView } from './components/CalendarView'
import { SettingsModal } from './components/SettingsModal'
import { ReviewModal } from './components/ReviewModal'
import { CleanupModal } from './components/CleanupModal'
import { ChangelogModal, CURRENT_VERSION } from './components/ChangelogModal'
import { BUILD_NUMBER } from './version'
import {
  MAIN_PIPELINE, MAIN_STATUS_LABELS,
  type Application, type Stats, type MainStatus,
} from './types'
import { Calendar } from 'lucide-react'
import clsx from 'clsx'

type ViewMode = 'table' | 'kanban'
type MainView = 'applications' | 'contacts' | 'calendar'

export default function App() {
  const [apps, setApps] = useState<Application[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [filterStatus, setFilterStatus] = useState<MainStatus | 'all'>('all')
  const [showRejected, setShowRejected] = useState(false)
  const [showGhostingOnly, setShowGhostingOnly] = useState(false)
  const [viewMode, setViewMode] = useState<ViewMode>('kanban')
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [mainView, setMainView] = useState<MainView>('applications')
  const [loading, setLoading] = useState(false)
  const [showAiSettings, setShowAiSettings] = useState(false)
  const [showReview, setShowReview] = useState(false)
  const [showCleanup, setShowCleanup] = useState(false)
  const [showChangelog, setShowChangelog] = useState(false)
  const [reviewCount, setReviewCount] = useState(0)

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300)
    return () => clearTimeout(t)
  }, [search])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [appsData, statsData] = await Promise.all([
        api.applications.list({
          main_status: filterStatus === 'all' ? undefined : filterStatus,
          search: debouncedSearch || undefined,
          show_rejected: showRejected,
        }),
        api.applications.stats(),
      ])
      setApps(appsData)
      setStats(statsData)
    } finally {
      setLoading(false)
    }
  }, [filterStatus, debouncedSearch, showRejected])

  useEffect(() => { load() }, [load])

  const loadReviewCount = useCallback(async () => {
    try {
      const { count } = await api.review.count()
      setReviewCount(count)
    } catch { /* ignore */ }
  }, [])

  useEffect(() => { loadReviewCount() }, [loadReviewCount])

  const visibleApps = showGhostingOnly ? apps.filter(a => a.ghosting) : apps
  const kanbanColumns: MainStatus[] = showRejected ? [...MAIN_PIPELINE, 'rejected'] : MAIN_PIPELINE
  const kanbanByStatus = kanbanColumns.map(s => ({
    status: s,
    items: visibleApps
      .filter(a => a.main_status === s)
      .sort((a, b) => {
        const da = a.letztes_update ?? a.datum_bewerbung ?? ''
        const db2 = b.letztes_update ?? b.datum_bewerbung ?? ''
        return db2.localeCompare(da)
      }),
  })).filter(col => col.items.length > 0 || filterStatus === col.status)

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="border-b border-gray-200 bg-white shadow-sm sticky top-0 z-30">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex h-14 items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2.5">
                <Briefcase className="h-5 w-5 text-indigo-600" />
                <div className="flex flex-col leading-tight">
                  <span className="font-semibold text-gray-900 leading-none">JobTracker</span>
                  <button
                    onClick={() => setShowChangelog(true)}
                    className="text-[10px] text-indigo-400 hover:text-indigo-600 font-mono leading-none mt-0.5 text-left transition-colors"
                  >
                    v{CURRENT_VERSION} · {BUILD_NUMBER}
                  </button>
                </div>
              </div>
              <div className="flex rounded-lg border border-gray-200 overflow-hidden bg-white">
                <button
                  onClick={() => setMainView('applications')}
                  className={clsx('flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors', mainView === 'applications' ? 'bg-indigo-600 text-white' : 'text-gray-600 hover:bg-gray-50')}
                >
                  <Briefcase className="h-3.5 w-3.5" /> Bewerbungen
                </button>
                <button
                  onClick={() => setMainView('contacts')}
                  className={clsx('flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors', mainView === 'contacts' ? 'bg-indigo-600 text-white' : 'text-gray-600 hover:bg-gray-50')}
                >
                  <Users className="h-3.5 w-3.5" /> Kontakte
                </button>
                <button
                  onClick={() => setMainView('calendar')}
                  className={clsx('flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors', mainView === 'calendar' ? 'bg-indigo-600 text-white' : 'text-gray-600 hover:bg-gray-50')}
                >
                  <Calendar className="h-3.5 w-3.5" /> Kalender
                </button>
              </div>
            </div>

            <div className="flex items-center gap-2">
<LinkedInSyncButton onSynced={load} />
<SyncButton onSynced={() => { load(); loadReviewCount() }} onReviewOpen={() => setShowReview(true)} />
              <ExportButton />
              <PdfExportButton />
              <ImportButton onImported={load} />
              <button
                onClick={() => setShowCleanup(true)}
                title="Duplikate in Bewerbungen, Kontakten und Timeline bereinigen"
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-600 border border-gray-200 rounded-lg bg-white hover:bg-gray-50 transition-colors"
              >
                <Sparkles className="h-3.5 w-3.5 text-indigo-400" />
                Bereinigen
              </button>
              <button
                onClick={() => setSelectedId(-1)}
                className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 transition-colors"
              >
                <Plus className="h-4 w-4" />
                Neu
              </button>
              <button
                onClick={() => setShowReview(true)}
                className="relative p-1.5 rounded-lg hover:bg-gray-100 text-amber-500"
                title="Manuelle Überprüfung"
              >
                <RefreshCw className="h-4 w-4" />
                {reviewCount > 0 && (
                  <span className="absolute -top-1 -right-1 min-w-[16px] h-4 flex items-center justify-center rounded-full bg-amber-500 text-white text-[10px] font-bold px-0.5">
                    {reviewCount}
                  </span>
                )}
              </button>
              <button
                onClick={() => setShowAiSettings(true)}
                className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400"
                title="KI-Einstellungen"
              >
                <Settings className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-6 space-y-5">
        {mainView === 'contacts' && (
          <ContactsView onOpenApplication={id => { setMainView('applications'); setSelectedId(id) }} />
        )}
        {mainView === 'calendar' && (
          <CalendarView onOpenApplication={id => { setMainView('applications'); setSelectedId(id) }} />
        )}
        {mainView === 'applications' && (<>
        {/* Stats */}
        {stats && <StatsBar stats={stats} />}

        {/* Search bar */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Firma oder Rolle suchen…"
            className="w-full rounded-lg border border-gray-200 pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
          />
        </div>

        {/* Controls row */}
        <div className="flex items-center justify-between gap-4 flex-wrap">
          {/* Status filter tabs */}
          <div className="flex items-center gap-1.5 flex-wrap">
            <button
              onClick={() => setFilterStatus('all')}
              className={clsx(
                'rounded-full px-3 py-1 text-xs font-medium transition-colors',
                filterStatus === 'all' ? 'bg-indigo-600 text-white' : 'bg-white border border-gray-200 text-gray-600 hover:bg-gray-50'
              )}
            >
              Alle
            </button>
            {MAIN_PIPELINE.map(s => (
              <button
                key={s}
                onClick={() => setFilterStatus(s)}
                className={clsx(
                  'rounded-full px-3 py-1 text-xs font-medium transition-colors',
                  filterStatus === s ? 'bg-indigo-600 text-white' : 'bg-white border border-gray-200 text-gray-600 hover:bg-gray-50'
                )}
              >
                {MAIN_STATUS_LABELS[s]}
                {stats?.by_status[s] ? <span className="ml-1 opacity-70">({stats.by_status[s]})</span> : null}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 text-xs text-gray-600 cursor-pointer">
              <input
                type="checkbox"
                checked={showGhostingOnly}
                onChange={e => setShowGhostingOnly(e.target.checked)}
                className="rounded border-gray-300 text-orange-500"
              />
              👻 Nur Ghosting
            </label>
            <label className="flex items-center gap-2 text-xs text-gray-600 cursor-pointer">
              <input
                type="checkbox"
                checked={showRejected}
                onChange={e => setShowRejected(e.target.checked)}
                className="rounded border-gray-300 text-indigo-600"
              />
              Abgesagte anzeigen
            </label>

            {/* View toggle */}
            <div className="flex rounded-lg border border-gray-200 overflow-hidden bg-white">
              {(['table', 'kanban'] as ViewMode[]).map(mode => (
                <button
                  key={mode}
                  onClick={() => setViewMode(mode)}
                  className={clsx(
                    'px-3 py-1.5 text-xs font-medium transition-colors',
                    viewMode === mode ? 'bg-indigo-600 text-white' : 'text-gray-600 hover:bg-gray-50'
                  )}
                >
                  {mode === 'table' ? '☰ Tabelle' : '▦ Kanban'}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Main content */}
        {viewMode === 'table' ? (
          <ApplicationTable applications={visibleApps} onSelect={setSelectedId} onStatusChanged={load} />
        ) : (
          <KanbanBoard columns={kanbanByStatus} onSelect={setSelectedId} onChanged={load} />
        )}
        </>)}
      </main>

      {/* Modal */}
      {selectedId !== null && selectedId > 0 && (
        <ApplicationModal
          appId={selectedId}
          onClose={() => setSelectedId(null)}
          onSaved={load}
        />
      )}

      {showAiSettings && <SettingsModal onClose={() => setShowAiSettings(false)} />}
      {showCleanup && (
        <CleanupModal
          onClose={() => setShowCleanup(false)}
          onDone={() => { load(); setShowCleanup(false) }}
        />
      )}
      {showReview && (
        <ReviewModal
          onClose={() => { setShowReview(false); loadReviewCount() }}
          onApproved={() => { load(); loadReviewCount() }}
        />
      )}

      <ChangelogModal open={showChangelog} onClose={() => setShowChangelog(false)} />

      {/* New application modal */}
      {selectedId === -1 && (
        <NewApplicationModal
          onClose={() => setSelectedId(null)}
          onSaved={() => { setSelectedId(null); load() }}
        />
      )}
    </div>
  )
}


function NewApplicationModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState<{
    firma: string; rolle: string; quelle: string; is_headhunter: boolean
    main_status: MainStatus; datum_bewerbung: string
  }>({ firma: '', rolle: '', quelle: '', is_headhunter: false, main_status: 'applied', datum_bewerbung: '' })
  const [saving, setSaving] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!form.firma || !form.rolle) return
    setSaving(true)
    try {
      await api.applications.create({
        ...form,
        datum_bewerbung: form.datum_bewerbung || undefined,
      })
      onSaved()
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={e => e.target === e.currentTarget && onClose()}>
      <form onSubmit={submit} className="w-full max-w-md rounded-2xl bg-white shadow-2xl p-6 space-y-4">
        <h2 className="text-lg font-semibold text-gray-900">Neue Bewerbung</h2>
        <input
          required
          className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          placeholder="Firma *"
          value={form.firma}
          onChange={e => setForm(f => ({ ...f, firma: e.target.value }))}
        />
        <input
          required
          className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          placeholder="Rolle *"
          value={form.rolle}
          onChange={e => setForm(f => ({ ...f, rolle: e.target.value }))}
        />
        <div className="grid grid-cols-2 gap-3">
          <input
            className="rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="Quelle (LinkedIn, XING, …)"
            value={form.quelle}
            onChange={e => setForm(f => ({ ...f, quelle: e.target.value }))}
          />
          <input
            type="date"
            className="rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            value={form.datum_bewerbung}
            onChange={e => setForm(f => ({ ...f, datum_bewerbung: e.target.value }))}
          />
        </div>
        <div>
          <p className="text-xs font-medium text-gray-500 mb-2">Status</p>
          <div className="flex gap-2 flex-wrap">
            {(['prospecting', 'applied'] as MainStatus[]).map(s => (
              <button
                key={s}
                type="button"
                onClick={() => setForm(f => ({ ...f, main_status: s }))}
                className={`text-xs px-3 py-1.5 rounded-full border transition-all ${form.main_status === s ? 'bg-indigo-600 text-white border-indigo-600' : 'border-gray-200 text-gray-600 hover:border-gray-300'}`}
              >
                {MAIN_STATUS_LABELS[s]}
              </button>
            ))}
          </div>
        </div>
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input
            type="checkbox"
            checked={form.is_headhunter}
            onChange={e => setForm(f => ({ ...f, is_headhunter: e.target.checked }))}
            className="rounded border-gray-300 text-indigo-600"
          />
          Über Headhunter
        </label>
        <div className="flex justify-end gap-3 pt-2">
          <button type="button" onClick={onClose} className="rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50">
            Abbrechen
          </button>
          <button type="submit" disabled={saving} className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60">
            {saving ? 'Speichern…' : 'Anlegen'}
          </button>
        </div>
      </form>
    </div>
  )
}
