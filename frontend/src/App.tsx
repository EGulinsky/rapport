import { useState, useEffect, useCallback, useRef } from 'react'
import { Plus, RefreshCw, Briefcase, Users, Settings, Sparkles, GitMerge, ClipboardList, BarChart2, Building2, ChevronDown, Linkedin, Cloud } from 'lucide-react'
import { CompanySearchInput } from './components/CompanySearchInput'
import { api } from './api/client'
import { ApplicationTable } from './components/ApplicationTable'
import { KanbanBoard } from './components/KanbanBoard'
import { ApplicationModal } from './components/ApplicationModal'
import { StatsBar } from './components/StatsBar'
import { SyncButton } from './components/SyncButton'
import { ImportExportMenu } from './components/ImportExportMenu'
import { ContactsView } from './components/ContactsView'
import { NewContactModal } from './components/NewContactModal'
import { ContactImportModal } from './components/ContactImportModal'
import { CompaniesView } from './components/CompaniesView'
import { CompanyModal } from './components/CompanyModal'
import { CalendarView } from './components/CalendarView'
import { AnalyticsView } from './components/AnalyticsView'
import { SettingsModal } from './components/SettingsModal'
import { ReviewModal } from './components/ReviewModal'
import { CleanupModal } from './components/CleanupModal'
import { ChangelogModal, CURRENT_VERSION } from './components/ChangelogModal'
import { AppMergeDialog, CompanyMergeDialog } from './components/MergeDialog'
import AuditLogModal from './components/AuditLogModal'
import { StartupWarningBanner } from './components/StartupWarningBanner'
import { EnvironmentBanner } from './components/EnvironmentBanner'
import { BUILD_NUMBER } from './version'
import {
  MAIN_PIPELINE, MAIN_STATUS_LABELS,
  type Application, type Stats, type MainStatus, type CompanyProfile, type CleanupScope,
} from './types'
import { Calendar } from 'lucide-react'
import clsx from 'clsx'
import { LogoProvider } from './context/LogoContext'

type ViewMode = 'table' | 'kanban'
type MainView = 'applications' | 'contacts' | 'companies' | 'calendar' | 'analytics'

const CLEANUP_SCOPE_BY_VIEW: Partial<Record<MainView, { scope: CleanupScope; label: string }>> = {
  applications: { scope: 'applications', label: 'Bewerbungen' },
  contacts:     { scope: 'contacts',     label: 'Kontakte' },
  companies:    { scope: 'companies',    label: 'Firmen' },
  calendar:     { scope: 'events',       label: 'Kalender' },
}

function BackendGate({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false)

  useEffect(() => {
    let cancelled = false
    async function poll() {
      while (!cancelled) {
        try {
          const res = await fetch('/api/applications/stats')
          if (res.ok) { setReady(true); return }
        } catch { /* still starting */ }
        await new Promise(r => setTimeout(r, 1500))
      }
    }
    poll()
    return () => { cancelled = true }
  }, [])

  if (!ready) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-4 bg-gray-50 text-gray-500">
        <div className="h-8 w-8 rounded-full border-2 border-indigo-400 border-t-transparent animate-spin" />
        <p className="text-sm font-medium">Backend startet…</p>
      </div>
    )
  }
  return <>{children}</>
}

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
  const [selectedAppIds, setSelectedAppIds] = useState<Set<number>>(new Set())
  const [showMerge, setShowMerge] = useState(false)
  const [mainView, setMainView] = useState<MainView>('applications')
  const [loading, setLoading] = useState(false)
  const [showAiSettings, setShowAiSettings] = useState(false)
  const [showAuditLog, setShowAuditLog] = useState(false)
  const [showReview, setShowReview] = useState(false)
  const [showCleanup, setShowCleanup] = useState(false)
  const [aiAssessingAll, setAiAssessingAll] = useState(false)
  const [aiAssessProgress, setAiAssessProgress] = useState<{ done: number; total: number } | null>(null)
  const [showNewMenu, setShowNewMenu] = useState(false)
  const [showLinkedInImport, setShowLinkedInImport] = useState(false)
  const [newApplicationPrefill, setNewApplicationPrefill] = useState<NewApplicationPrefill | null>(null)
  const newMenuRef = useRef<HTMLDivElement>(null)
  const [showChangelog, setShowChangelog] = useState(false)
  const [reviewCount, setReviewCount] = useState(0)
  const [companyModalId, setCompanyModalId] = useState<number | null>(null)
  const [companyMergeIds, setCompanyMergeIds] = useState<number[] | null>(null)
  const [companyReloadKey, setCompanyReloadKey] = useState(0)
  const [contactsSearch, setContactsSearch] = useState('')
  const [showNewContact, setShowNewContact] = useState(false)
  const [contactImportSource, setContactImportSource] = useState<'icloud' | 'linkedin' | null>(null)
  const [contactsReloadKey, setContactsReloadKey] = useState(0)

  const prevAppsRef = useRef<Map<number, Application>>(new Map())
  const [updatedAppIds, setUpdatedAppIds] = useState<Set<number>>(new Set())
  const [changedFields, setChangedFields] = useState<Map<number, Set<string>>>(new Map())

  const SYNC_DIFFABLE_FIELDS: (keyof Application)[] = [
    'main_status', 'sub_status', 'naechster_schritt', 'kommentar', 'quelle',
    'wurde_besetzt_von', 'zielfirma_bei_hh', 'ghosting', 'abgesagt',
    'stellenanzeige_url', 'gespraech_1', 'gespraech_2', 'gespraech_3',
    'gespraech_4', 'gespraech_5', 'firma', 'rolle',
  ]

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300)
    return () => clearTimeout(t)
  }, [search])

  useEffect(() => {
    if (!showNewMenu) return
    function onDown(e: MouseEvent) {
      if (newMenuRef.current && !newMenuRef.current.contains(e.target as Node)) setShowNewMenu(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [showNewMenu])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [appsData, statsData] = await Promise.all([
        api.applications.list({
          main_status: filterStatus === 'all' ? undefined : filterStatus,
          search: debouncedSearch || undefined,
          show_rejected: showRejected || showGhostingOnly,
        }),
        api.applications.stats(),
      ])
      const prev = prevAppsRef.current
      if (prev.size > 0) {
        const changed = new Set<number>()
        const newFieldChanges = new Map<number, Set<string>>()
        for (const app of appsData) {
          const prevApp = prev.get(app.id)
          if (!prevApp) continue
          if (app.letztes_update && prevApp.letztes_update !== app.letztes_update) {
            changed.add(app.id)
            const fields = new Set<string>()
            for (const key of SYNC_DIFFABLE_FIELDS) {
              if (String(prevApp[key] ?? '') !== String(app[key] ?? '')) fields.add(key)
            }
            if (fields.size > 0) newFieldChanges.set(app.id, fields)
          }
        }
        if (changed.size > 0) setUpdatedAppIds(s => new Set([...s, ...changed]))
        if (newFieldChanges.size > 0) {
          setChangedFields(prev => {
            const next = new Map(prev)
            for (const [id, fields] of newFieldChanges) {
              const existing = next.get(id)
              if (existing) fields.forEach(f => existing.add(f))
              else next.set(id, new Set(fields))
            }
            return next
          })
        }
      }
      prevAppsRef.current = new Map(appsData.map(a => [a.id, a]))
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

  useEffect(() => {
    const id = setInterval(loadReviewCount, 30_000)
    return () => clearInterval(id)
  }, [loadReviewCount])

  useEffect(() => {
    if (selectedId && selectedId > 0) {
      setUpdatedAppIds(s => {
        if (!s.has(selectedId)) return s
        const next = new Set(s)
        next.delete(selectedId)
        return next
      })
      setChangedFields(prev => {
        if (!prev.has(selectedId)) return prev
        const next = new Map(prev)
        next.delete(selectedId)
        return next
      })
    }
  }, [selectedId])

  const visibleApps = showGhostingOnly ? apps.filter(a => a.ghosting) : apps

  // Rejected apps appear in their last-active column, not a separate "Abgesagt" column
  const kanbanColumns: MainStatus[] = MAIN_PIPELINE
  function kanbanColumnForApp(a: Application): MainStatus {
    if (a.abgesagt) {
      const pre = a.pre_rejection_status
      return (pre && MAIN_PIPELINE.includes(pre as MainStatus) ? pre : 'applied') as MainStatus
    }
    return a.main_status
  }
  const kanbanByStatus = kanbanColumns.map(s => ({
    status: s,
    items: visibleApps
      .filter(a => kanbanColumnForApp(a) === s)
      .sort((a, b) => {
        // Active apps first, then rejected
        if (a.abgesagt !== b.abgesagt) return a.abgesagt ? 1 : -1
        const da = a.letztes_update ?? a.datum_bewerbung ?? ''
        const db2 = b.letztes_update ?? b.datum_bewerbung ?? ''
        return db2.localeCompare(da)
      }),
  })).filter(col => col.items.length > 0 || filterStatus === col.status)

  return (
    <BackendGate>
    <LogoProvider>
    <div className="min-h-screen bg-gray-50">
      <EnvironmentBanner />
      <StartupWarningBanner />
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
                  onClick={() => setMainView('companies')}
                  className={clsx('flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors', mainView === 'companies' ? 'bg-indigo-600 text-white' : 'text-gray-600 hover:bg-gray-50')}
                >
                  <Building2 className="h-3.5 w-3.5" /> Firmen
                </button>
                <button
                  onClick={() => setMainView('calendar')}
                  className={clsx('flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors', mainView === 'calendar' ? 'bg-indigo-600 text-white' : 'text-gray-600 hover:bg-gray-50')}
                >
                  <Calendar className="h-3.5 w-3.5" /> Kalender
                </button>
                <button
                  onClick={() => setMainView('analytics')}
                  className={clsx('flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors', mainView === 'analytics' ? 'bg-indigo-600 text-white' : 'text-gray-600 hover:bg-gray-50')}
                >
                  <BarChart2 className="h-3.5 w-3.5" /> Auswertungen
                </button>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <SyncButton onSynced={() => { load(); loadReviewCount() }} onReviewOpen={() => setShowReview(true)} />
              <ImportExportMenu onImported={load} />
              <button
                onClick={async () => {
                  setAiAssessingAll(true)
                  setAiAssessProgress(null)
                  try {
                    const resp = await fetch(api.applications.aiAssessAllUrl())
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
                          if (d.status === 'start') setAiAssessProgress({ done: 0, total: d.total })
                          if (d.status === 'progress') {
                            setAiAssessProgress({ done: d.done, total: d.total })
                            load()
                          }
                        } catch { /* ignore parse errors */ }
                      }
                    }
                    load()
                  }
                  catch (e) { console.error('AI assess all failed', e) }
                  finally { setAiAssessingAll(false); setAiAssessProgress(null) }
                }}
                disabled={aiAssessingAll}
                title="KI-Einschätzung für alle aktiven Bewerbungen aktualisieren"
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-purple-600 border border-purple-200 rounded-lg bg-purple-50 hover:bg-purple-100 disabled:opacity-50 transition-colors"
              >
                <Sparkles className={`h-3.5 w-3.5 ${aiAssessingAll ? 'animate-pulse' : ''}`} />
                {aiAssessingAll
                  ? (aiAssessProgress ? `KI: ${aiAssessProgress.done}/${aiAssessProgress.total}` : 'KI läuft…')
                  : 'KI bewerten'}
              </button>
              <button
                onClick={() => setShowCleanup(true)}
                title={CLEANUP_SCOPE_BY_VIEW[mainView] ? `Duplikate in ${CLEANUP_SCOPE_BY_VIEW[mainView]!.label} bereinigen` : 'Duplikate bereinigen'}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-600 border border-gray-200 rounded-lg bg-white hover:bg-gray-50 transition-colors"
              >
                <Sparkles className="h-3.5 w-3.5 text-indigo-400" />
                Bereinigen{CLEANUP_SCOPE_BY_VIEW[mainView] ? ` (${CLEANUP_SCOPE_BY_VIEW[mainView]!.label})` : ''}
              </button>
              <div className="relative" ref={newMenuRef}>
                <button
                  onClick={() => setShowNewMenu(o => !o)}
                  className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 transition-colors"
                >
                  <Plus className="h-4 w-4" />
                  Neu
                  <ChevronDown className="h-3.5 w-3.5" />
                </button>
                {showNewMenu && (
                  <div className="absolute z-50 top-full right-0 mt-1 w-56 bg-white border border-gray-200 rounded-lg shadow-lg py-1">
                    {mainView === 'contacts' ? (
                      <>
                        <button
                          type="button"
                          onClick={() => { setShowNewMenu(false); setShowNewContact(true) }}
                          className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-indigo-50 hover:text-indigo-700 transition-colors flex items-center gap-2"
                        >
                          <Plus className="h-3.5 w-3.5 shrink-0" /> Manuell anlegen
                        </button>
                        <button
                          type="button"
                          onClick={() => { setShowNewMenu(false); setContactImportSource('icloud') }}
                          className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-indigo-50 hover:text-indigo-700 transition-colors flex items-center gap-2"
                        >
                          <Cloud className="h-3.5 w-3.5 shrink-0" /> Aus iCloud importieren
                        </button>
                        <button
                          type="button"
                          onClick={() => { setShowNewMenu(false); setContactImportSource('linkedin') }}
                          className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-indigo-50 hover:text-indigo-700 transition-colors flex items-center gap-2"
                        >
                          <Linkedin className="h-3.5 w-3.5 shrink-0" /> Aus LinkedIn importieren
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={() => { setShowNewMenu(false); setNewApplicationPrefill(null); setSelectedId(-1) }}
                          className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-indigo-50 hover:text-indigo-700 transition-colors flex items-center gap-2"
                        >
                          <Plus className="h-3.5 w-3.5 shrink-0" /> Manuell anlegen
                        </button>
                        <button
                          type="button"
                          onClick={() => { setShowNewMenu(false); setShowLinkedInImport(true) }}
                          className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-indigo-50 hover:text-indigo-700 transition-colors flex items-center gap-2"
                        >
                          <Linkedin className="h-3.5 w-3.5 shrink-0" /> Aus LinkedIn importieren
                        </button>
                      </>
                    )}
                  </div>
                )}
              </div>
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
                onClick={() => setShowAuditLog(true)}
                className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400"
                title="Audit-Log"
              >
                <ClipboardList className="h-4 w-4" />
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
          <ContactsView
            onOpenApplication={id => { setMainView('applications'); setSelectedId(id) }}
            onOpenCompany={id => setCompanyModalId(id)}
            search={contactsSearch}
            onSearchChange={setContactsSearch}
            reloadKey={contactsReloadKey}
          />
        )}
        {mainView === 'companies' && (
          <CompaniesView
            onOpenApplication={id => { setMainView('applications'); setSelectedId(id) }}
            onOpenCompany={id => setCompanyModalId(id)}
            onMergeRequest={ids => setCompanyMergeIds(ids)}
            onNavigateToApps={name => { setSearch(name); setMainView('applications') }}
            onNavigateToContacts={name => { setContactsSearch(name); setMainView('contacts') }}
            reloadKey={companyReloadKey}
          />
        )}
        {mainView === 'calendar' && (
          <CalendarView onOpenApplication={id => { setMainView('applications'); setSelectedId(id) }} />
        )}
        {mainView === 'analytics' && (
          <AnalyticsView />
        )}
        {mainView === 'applications' && (<>
        {/* Stats */}
        {stats && <StatsBar stats={stats} />}

        {/* Search bar (mit Firmen-Autocomplete) */}
        <CompanySearchInput value={search} onChange={setSearch} placeholder="Firma oder Rolle suchen…" />

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
            {selectedAppIds.size >= 2 && viewMode === 'table' && (
              <button
                onClick={() => setShowMerge(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-lg bg-violet-600 text-white hover:bg-violet-700 transition-colors"
              >
                <GitMerge className="h-3.5 w-3.5" />
                Mergen ({selectedAppIds.size})
              </button>
            )}
            {selectedAppIds.size > 0 && viewMode === 'table' && (
              <button
                onClick={() => setSelectedAppIds(new Set())}
                className="text-xs text-gray-400 hover:text-gray-600 transition-colors"
              >
                Auswahl aufheben
              </button>
            )}
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

        {/* Table (only in table mode — Kanban is rendered outside max-w-7xl below) */}
        {viewMode === 'table' && (
          <ApplicationTable
            applications={visibleApps}
            onSelect={setSelectedId}
            onStatusChanged={load}
            selectedIds={selectedAppIds}
            onToggleSelect={id => setSelectedAppIds(prev => {
              const next = new Set(prev)
              next.has(id) ? next.delete(id) : next.add(id)
              return next
            })}
            onOpenCompany={id => setCompanyModalId(id)}
            updatedIds={updatedAppIds}
          />
        )}
        </>)}
      </main>

      {/* Kanban: full viewport width, outside max-w-7xl */}
      {mainView === 'applications' && viewMode === 'kanban' && (
        <KanbanBoard columns={kanbanByStatus} onSelect={setSelectedId} onChanged={load} onOpenCompany={id => setCompanyModalId(id)} updatedIds={updatedAppIds} />
      )}

      {/* Modal */}
      {selectedId !== null && selectedId > 0 && (
        <ApplicationModal
          appId={selectedId}
          onClose={() => setSelectedId(null)}
          onSaved={() => { load(); loadReviewCount() }}
          onOpenCompany={id => setCompanyModalId(id)}
          updatedFields={changedFields.get(selectedId) ?? undefined}
        />
      )}

      {companyModalId !== null && (
        <CompanyModal
          id={companyModalId}
          onClose={() => setCompanyModalId(null)}
          onOpenApplication={id => { setCompanyModalId(null); setMainView('applications'); setSelectedId(id) }}
          onOpenContact={() => { setCompanyModalId(null); setMainView('contacts') }}
          onOpenCompany={id => setCompanyModalId(id)}
          onMergeRequest={ids => { setCompanyModalId(null); setCompanyMergeIds(ids) }}
          onSaved={() => { setCompanyReloadKey(k => k + 1); load() }}
        />
      )}

      {companyMergeIds && (
        <CompanyMergeDialog
          companyIds={companyMergeIds}
          onMerged={winnerId => { setCompanyMergeIds(null); setCompanyReloadKey(k => k + 1); setCompanyModalId(winnerId) }}
          onClose={() => setCompanyMergeIds(null)}
        />
      )}

      {showAiSettings && <SettingsModal onClose={() => setShowAiSettings(false)} />}
      {showAuditLog && <AuditLogModal onClose={() => setShowAuditLog(false)} />}
      {showCleanup && (
        <CleanupModal
          onClose={() => setShowCleanup(false)}
          onDone={() => { load(); setCompanyReloadKey(k => k + 1); setShowCleanup(false) }}
          scope={CLEANUP_SCOPE_BY_VIEW[mainView]?.scope}
          scopeLabel={CLEANUP_SCOPE_BY_VIEW[mainView]?.label}
        />
      )}
      {showReview && (
        <ReviewModal
          onClose={() => { setShowReview(false); loadReviewCount() }}
          onApproved={() => { load(); loadReviewCount() }}
        />
      )}

      <ChangelogModal open={showChangelog} onClose={() => setShowChangelog(false)} />

      {showMerge && selectedAppIds.size >= 2 && (
        <AppMergeDialog
          appIds={[...selectedAppIds]}
          onMerged={() => { setShowMerge(false); setSelectedAppIds(new Set()); load() }}
          onClose={() => setShowMerge(false)}
        />
      )}

      {/* New application modal */}
      {selectedId === -1 && (
        <NewApplicationModal
          initial={newApplicationPrefill}
          onClose={() => { setSelectedId(null); setNewApplicationPrefill(null) }}
          onSaved={() => { setSelectedId(null); setNewApplicationPrefill(null); load() }}
        />
      )}

      {/* LinkedIn import modal */}
      {showLinkedInImport && (
        <LinkedInImportModal
          onClose={() => setShowLinkedInImport(false)}
          onExtracted={prefill => { setShowLinkedInImport(false); setNewApplicationPrefill(prefill); setSelectedId(-1) }}
        />
      )}

      {showNewContact && (
        <NewContactModal
          onClose={() => setShowNewContact(false)}
          onCreated={() => setContactsReloadKey(k => k + 1)}
        />
      )}

      {contactImportSource && (
        <ContactImportModal
          source={contactImportSource}
          onClose={() => setContactImportSource(null)}
          onImported={() => setContactsReloadKey(k => k + 1)}
        />
      )}
    </div>
    </LogoProvider>
    </BackendGate>
  )
}

interface NewApplicationPrefill {
  firma: string
  rolle: string
  quelle: string
  is_headhunter: boolean
  zielfirma_bei_hh: string | null
  kommentar: string | null
  stellenanzeige_url?: string
  company_profile_id?: number | null
}

function LinkedInImportModal({ onClose, onExtracted }: { onClose: () => void; onExtracted: (prefill: NewApplicationPrefill) => void }) {
  const [url, setUrl] = useState('')
  const [extracting, setExtracting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function extract() {
    if (!url.trim()) return
    setExtracting(true)
    setError(null)
    try {
      const result = await api.applications.extractFromLinkedInUrl(url.trim())
      onExtracted(result)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      setError(
        msg.includes('429') || msg.toLowerCase().includes('rate')
          ? 'Rate-Limit erreicht — bitte 30–60 Sekunden warten und nochmal versuchen.'
          : msg.toLowerCase().includes('linkedin nicht konfiguriert')
            ? 'LinkedIn ist nicht verbunden — bitte zuerst in den Einstellungen unter "LinkedIn" anmelden.'
            : msg.includes('400')
              ? 'Stellenanzeige konnte nicht geladen werden — bitte Link prüfen oder Felder manuell ausfüllen.'
              : 'Import fehlgeschlagen.'
      )
    } finally {
      setExtracting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="w-full max-w-lg rounded-2xl bg-white shadow-2xl p-6 space-y-4">
        <div className="flex items-center gap-2">
          <Linkedin className="h-5 w-5 text-[#0A66C2]" />
          <h2 className="text-lg font-semibold text-gray-900">Aus LinkedIn importieren</h2>
        </div>
        <p className="text-sm text-gray-500">
          Link zur LinkedIn-Stellenanzeige einfügen. Die Seite wird automatisch geladen und Firma, Rolle und weitere Felder per KI ausgefüllt.
        </p>
        <input
          autoFocus
          type="url"
          className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          placeholder="https://www.linkedin.com/jobs/view/…"
          value={url}
          onChange={e => setUrl(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !extracting && url.trim()) extract() }}
        />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex justify-end gap-3 pt-2">
          <button type="button" onClick={onClose} className="rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50">
            Abbrechen
          </button>
          <button
            type="button"
            disabled={extracting || !url.trim()}
            onClick={extract}
            className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            <Sparkles className={`h-3.5 w-3.5 ${extracting ? 'animate-pulse' : ''}`} />
            {extracting ? 'Lade & extrahiere…' : 'Importieren'}
          </button>
        </div>
      </div>
    </div>
  )
}


function NewApplicationModal({ initial, onClose, onSaved }: { initial?: NewApplicationPrefill | null; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState<{
    firma: string; company_profile_id: number | null; rolle: string; quelle: string; is_headhunter: boolean
    main_status: MainStatus; datum_bewerbung: string; zielfirma_bei_hh: string; kommentar: string; stellenanzeige_url: string
  }>({
    firma: initial?.firma ?? '',
    company_profile_id: initial?.company_profile_id ?? null,
    rolle: initial?.rolle ?? '',
    quelle: initial?.quelle ?? '',
    is_headhunter: initial?.is_headhunter ?? false,
    main_status: 'applied',
    datum_bewerbung: '',
    zielfirma_bei_hh: initial?.zielfirma_bei_hh ?? '',
    kommentar: initial?.kommentar ?? '',
    stellenanzeige_url: initial?.stellenanzeige_url ?? '',
  })
  const [saving, setSaving] = useState(false)
  const [firmaPicker, setFirmaPicker] = useState(false)
  const [firmaQuery, setFirmaQuery] = useState('')
  const [firmaResults, setFirmaResults] = useState<CompanyProfile[]>([])
  const [firmaLoading, setFirmaLoading] = useState(false)
  const [firmaCreating, setFirmaCreating] = useState(false)
  const firmaPickerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!firmaPicker) { setFirmaQuery(''); setFirmaResults([]); return }
    let active = true
    setFirmaLoading(true)
    api.companies.list({ search: firmaQuery || undefined }).then(r => { if (active) setFirmaResults(r) }).finally(() => { if (active) setFirmaLoading(false) })
    return () => { active = false }
  }, [firmaQuery, firmaPicker])

  useEffect(() => {
    if (!firmaPicker) return
    function onDown(e: MouseEvent) {
      if (firmaPickerRef.current && !firmaPickerRef.current.contains(e.target as Node)) setFirmaPicker(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [firmaPicker])

  async function pickCompany(c: CompanyProfile) {
    setForm(f => ({ ...f, firma: c.name_display ?? c.name_norm, company_profile_id: c.id }))
    setFirmaPicker(false)
  }

  async function createAndPickCompany(name: string) {
    setFirmaCreating(true)
    try {
      const c = await api.companies.create(name)
      setForm(f => ({ ...f, firma: c.name_display ?? c.name_norm, company_profile_id: c.id }))
      setFirmaPicker(false)
    } finally {
      setFirmaCreating(false)
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!form.firma || !form.rolle) return
    setSaving(true)
    try {
      await api.applications.create({
        firma: form.firma,
        company_profile_id: form.company_profile_id ?? undefined,
        rolle: form.rolle,
        quelle: form.quelle,
        is_headhunter: form.is_headhunter,
        main_status: form.main_status,
        datum_bewerbung: form.datum_bewerbung || undefined,
        zielfirma_bei_hh: form.zielfirma_bei_hh || undefined,
        kommentar: form.kommentar || undefined,
        stellenanzeige_url: form.stellenanzeige_url || undefined,
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
        <div className="relative" ref={firmaPickerRef}>
          <div
            className={`w-full flex items-center justify-between rounded-lg border px-3 py-2 text-sm cursor-pointer ${form.firma ? 'border-gray-200 text-gray-900' : 'border-gray-200 text-gray-400'} hover:border-indigo-300`}
            onClick={() => setFirmaPicker(o => !o)}
          >
            <span className="truncate">{form.firma || 'Firma wählen… *'}</span>
            <Building2 className="h-4 w-4 text-gray-400 shrink-0 ml-2" />
          </div>
          {firmaPicker && (
            <div className="absolute z-50 top-full left-0 mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg">
              <div className="p-2 border-b border-gray-100">
                <input
                  autoFocus
                  value={firmaQuery}
                  onChange={e => setFirmaQuery(e.target.value)}
                  placeholder="Firma suchen…"
                  className="w-full rounded border border-gray-200 px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
              <div className="max-h-52 overflow-y-auto py-1">
                {firmaLoading && <p className="text-xs text-gray-400 px-3 py-2">Suche…</p>}
                {!firmaLoading && firmaResults.length === 0 && !firmaQuery && (
                  <p className="text-xs text-gray-400 px-3 py-2 italic">Suchbegriff eingeben…</p>
                )}
                {firmaResults.slice(0, 12).map(c => (
                  <button key={c.id} type="button" onClick={() => pickCompany(c)}
                    className="w-full text-left px-3 py-1.5 text-sm hover:bg-indigo-50 hover:text-indigo-700 transition-colors">
                    {c.name_display ?? c.name_norm}
                  </button>
                ))}
                {firmaQuery.trim() && (
                  <button type="button" disabled={firmaCreating} onClick={() => createAndPickCompany(firmaQuery.trim())}
                    className="w-full text-left px-3 py-1.5 text-sm text-indigo-600 hover:bg-indigo-50 transition-colors flex items-center gap-2 border-t border-gray-100 mt-1">
                    <Plus className="h-3.5 w-3.5 shrink-0" />
                    {firmaCreating ? 'Anlegen…' : `"${firmaQuery.trim()}" neu anlegen`}
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
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
        {form.is_headhunter && (
          <input
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="Zielfirma (für wen wird besetzt)"
            value={form.zielfirma_bei_hh}
            onChange={e => setForm(f => ({ ...f, zielfirma_bei_hh: e.target.value }))}
          />
        )}
        <textarea
          rows={2}
          className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          placeholder="Kommentar (optional)"
          value={form.kommentar}
          onChange={e => setForm(f => ({ ...f, kommentar: e.target.value }))}
        />
        <div className="flex justify-end gap-3 pt-2">
          <button type="button" onClick={onClose} className="rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50">
            Abbrechen
          </button>
          <button type="submit" disabled={saving || !form.firma || !form.rolle} className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60">
            {saving ? 'Speichern…' : 'Anlegen'}
          </button>
        </div>
      </form>
    </div>
  )
}
