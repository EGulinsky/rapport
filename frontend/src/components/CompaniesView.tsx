import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { Search, ArrowUpDown, Clock, CheckCircle, XCircle, RefreshCw, GitMerge, Briefcase, Users, ChevronsUp, Network, ChevronDown, Trash2 } from 'lucide-react'
import { api } from '../api/client'
import type { CompanyProfile, CompanySyncStatus } from '../types'
import clsx from 'clsx'
import { CompanyLogo } from './CompanyLogo'
import type { CompanyFilter } from './CompanyFilterPicker'

type SortKey = 'name' | 'industry' | 'apps' | 'sync_status'

interface Props {
  onOpenApplication: (id: number) => void
  onOpenCompany: (id: number) => void
  onMergeRequest?: (ids: number[]) => void
  onNavigateToApps?: (filter: CompanyFilter) => void
  onNavigateToContacts?: (filter: CompanyFilter) => void
  reloadKey?: number
}

const COMPANY_TYPE_COLORS: Record<string, string> = {
  startup:     'bg-blue-100 text-blue-700',
  konzern:     'bg-indigo-100 text-indigo-700',
  kmu:         'bg-teal-100 text-teal-700',
  beratung:    'bg-purple-100 text-purple-700',
  headhunter:  'bg-orange-100 text-orange-700',
  nonprofit:   'bg-green-100 text-green-700',
  public:      'bg-gray-100 text-gray-700',
  other:       'bg-gray-100 text-gray-600',
}

const COMPANY_TYPE_LABELS: Record<string, string> = {
  startup:     'Startup',
  konzern:     'Konzern',
  kmu:         'KMU',
  beratung:    'Beratung',
  headhunter:  'Headhunter',
  nonprofit:   'Non-Profit',
  public:      'Öffentlich',
  other:       'Sonstiges',
}

export function CompaniesView({ onOpenApplication: _onOpenApplication, onOpenCompany, onMergeRequest, onNavigateToApps, onNavigateToContacts, reloadKey }: Props) {
  const [companies, setCompanies] = useState<CompanyProfile[]>([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(false)
  const [sortKey, setSortKey] = useState<SortKey>('apps')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [appsFilter, setAppsFilter] = useState<'all' | 'yes' | 'no'>('all')
  const [contactsFilter, setContactsFilter] = useState<'all' | 'yes' | 'no'>('all')
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [deleting, setDeleting] = useState(false)

  function toggleSelect(id: number, e: React.MouseEvent) {
    e.stopPropagation()
    setSelectedIds(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const [linking, setLinking] = useState(false)
  const [linkMsg, setLinkMsg] = useState<string | null>(null)
  const [linkProgress, setLinkProgress] = useState<{linked: number; created: number; total: number} | null>(null)
  const linkPollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [parentPickerOpen, setParentPickerOpen] = useState(false)
  const [parentQuery, setParentQuery] = useState('')
  const [parentResults, setParentResults] = useState<CompanyProfile[]>([])
  const [assigningParent, setAssigningParent] = useState(false)
  const parentPickerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!parentPickerOpen) { setParentQuery(''); return }
    const t = setTimeout(async () => {
      setParentResults(await api.companies.list({ search: parentQuery || undefined }))
    }, 200)
    return () => clearTimeout(t)
  }, [parentQuery, parentPickerOpen])

  useEffect(() => {
    if (!parentPickerOpen) return
    const handler = (e: MouseEvent) => {
      if (parentPickerRef.current && !parentPickerRef.current.contains(e.target as Node))
        setParentPickerOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [parentPickerOpen])

  async function assignParent(parentId: number, parentName: string) {
    setAssigningParent(true)
    setParentPickerOpen(false)
    try {
      await Promise.all([...selectedIds].map(id =>
        api.companies.update(id, { parent_company_id: parentId })
      ))
      setSelectedIds(new Set())
      load()
    } finally {
      setAssigningParent(false)
    }
  }
  const [syncing, setSyncing] = useState(false)
  const [syncMsg, setSyncMsg] = useState<string | null>(null)
  const [syncLive, setSyncLive] = useState<CompanySyncStatus | null>(null)
  const [syncMenuOpen, setSyncMenuOpen] = useState(false)
  const syncMenuRef = useRef<HTMLDivElement>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const syncCancelledRef = useRef(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.companies.list({ search: search || undefined })
      setCompanies(data)
    } finally {
      setLoading(false)
    }
  }, [search])

  useEffect(() => {
    if (reloadKey) setSelectedIds(new Set())
    const t = setTimeout(load, 300)
    return () => clearTimeout(t)
  }, [load, reloadKey])

  const stopPolling = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
  }, [])

  const startPolling = useCallback(() => {
    stopPolling()
    pollRef.current = setInterval(async () => {
      try {
        const s = await api.companySync.status()
        setSyncLive(s)
        if (!s.running) {
          if (s.pending > 0 && !syncCancelledRef.current) {
            await api.companySync.run()
          } else {
            stopPolling()
            setSyncing(false)
            setSyncMsg(syncCancelledRef.current ? 'Abgebrochen.' : null)
            syncCancelledRef.current = false
            load()
          }
        }
      } catch {
        stopPolling()
        setSyncing(false)
      }
    }, 1500)
  }, [stopPolling, load])

  useEffect(() => () => stopPolling(), [stopPolling])
  useEffect(() => () => stopLinkPolling(), [])

  useEffect(() => {
    if (!syncMenuOpen) return
    const handler = (e: MouseEvent) => {
      if (syncMenuRef.current && !syncMenuRef.current.contains(e.target as Node)) setSyncMenuOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [syncMenuOpen])

  async function startSync(force = false) {
    setSyncMenuOpen(false)
    setSyncing(true)
    syncCancelledRef.current = false
    setSyncMsg(null)
    setSyncLive(null)
    try {
      await api.companySync.resetLock()
      const r = await api.companySync.run(force)
      if (r.started) {
        setSyncMsg(`${r.count} Firmenprofil(e) werden synchronisiert…`)
        startPolling()
      } else {
        setSyncMsg(r.message || 'Kein Sync nötig.')
        setSyncing(false)
      }
    } catch (e) {
      setSyncMsg(e instanceof Error ? e.message : 'Fehler')
      setSyncing(false)
    }
  }

  function stopLinkPolling() {
    if (linkPollRef.current) { clearInterval(linkPollRef.current); linkPollRef.current = null }
  }

  async function handleLinkContacts() {
    setLinking(true)
    setLinkMsg(null)
    setLinkProgress(null)
    try {
      const r = await api.companies.linkContacts()
      if (!r.started) {
        setLinkMsg(r.message || 'Bereits läuft')
        setLinking(false)
        return
      }
      stopLinkPolling()
      linkPollRef.current = setInterval(async () => {
        try {
          const s = await api.companies.linkContactsStatus()
          setLinkProgress({ linked: s.linked, created: s.created, total: s.total })
          if (!s.running) {
            stopLinkPolling()
            setLinking(false)
            setLinkProgress(null)
            if (s.cancelled) {
              setLinkMsg(`Abgebrochen — ${s.linked} verknüpft, ${s.created} neue Profile`)
            } else {
              setLinkMsg(`${s.linked} verknüpft, ${s.created} neue Profile`)
            }
            await load()
          }
        } catch {
          stopLinkPolling()
          setLinking(false)
        }
      }, 800)
    } catch (e) {
      setLinkMsg(e instanceof Error ? e.message : 'Fehler')
      setLinking(false)
    }
  }

  async function cancelLinkContacts() {
    await api.companies.linkContactsCancel()
  }

  async function cancelSync() {
    syncCancelledRef.current = true
    await api.companySync.cancel()
  }

  async function resetFailed() {
    try {
      await api.companySync.resetFailed()
      await load()
      setSyncMsg('Fehlgeschlagene Profile zurückgesetzt.')
    } catch {
      setSyncMsg('Fehler beim Zurücksetzen.')
    }
  }

  const pending = syncLive?.pending ?? companies.filter(c => c.sync_status === 'pending').length
  const done = syncLive?.done ?? companies.filter(c => c.sync_status === 'done').length
  const failed = syncLive?.failed ?? companies.filter(c => c.sync_status === 'failed').length
  const total = pending + done + failed

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('asc') }
  }

  const sorted = useMemo(() => {
    let list = companies
    if (appsFilter === 'yes') list = list.filter(c => (c.app_count ?? 0) > 0)
    if (appsFilter === 'no') list = list.filter(c => (c.app_count ?? 0) === 0)
    if (contactsFilter === 'yes') list = list.filter(c => (c.contact_count ?? 0) > 0)
    if (contactsFilter === 'no') list = list.filter(c => (c.contact_count ?? 0) === 0)
    return [...list].sort((a, b) => {
      let av: string | number
      let bv: string | number
      if (sortKey === 'apps') {
        av = a.app_count ?? 0
        bv = b.app_count ?? 0
      } else if (sortKey === 'industry') {
        av = (a.industry ?? '').toLowerCase()
        bv = (b.industry ?? '').toLowerCase()
      } else if (sortKey === 'sync_status') {
        av = a.sync_status
        bv = b.sync_status
      } else {
        av = (a.name_display || a.name_norm).toLowerCase()
        bv = (b.name_display || b.name_norm).toLowerCase()
      }
      if (av < bv) return sortDir === 'asc' ? -1 : 1
      if (av > bv) return sortDir === 'asc' ? 1 : -1
      return 0
    })
  }, [companies, sortKey, sortDir, appsFilter, contactsFilter])

  const allSelected = sorted.length > 0 && sorted.every(c => selectedIds.has(c.id))

  function toggleAll() {
    setSelectedIds(allSelected ? new Set() : new Set(sorted.map(c => c.id)))
  }

  async function deleteSelected() {
    if (selectedIds.size === 0) return
    if (!confirm(`${selectedIds.size} ${selectedIds.size === 1 ? 'Firma' : 'Firmen'} löschen?`)) return
    setDeleting(true)
    try {
      await api.companies.bulkDelete([...selectedIds])
      setSelectedIds(new Set())
      await load()
    } finally {
      setDeleting(false)
    }
  }

  const Th = ({ k, label, className }: { k: SortKey; label: string; className?: string }) => (
    <th
      className={clsx(
        'px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide cursor-pointer hover:text-gray-900 select-none',
        className,
      )}
      onClick={() => toggleSort(k)}
    >
      <span className="flex items-center gap-1">
        {label}
        <ArrowUpDown className={clsx('h-3 w-3 shrink-0', sortKey === k ? 'text-indigo-600' : 'text-gray-300')} />
      </span>
    </th>
  )

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Firma, Branche oder Ort…"
            className="w-full rounded-lg border border-gray-200 pl-9 pr-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        {loading && <span className="text-xs text-gray-400">Laden…</span>}
        <div className="flex items-center gap-1 shrink-0">
          <span className="text-xs text-gray-400">Bewerb.:</span>
          {(['all', 'yes', 'no'] as const).map(v => (
            <button key={v} onClick={() => setAppsFilter(v)}
              className={`px-2 py-1 rounded text-xs font-medium transition-colors ${appsFilter === v ? 'bg-indigo-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}>
              {v === 'all' ? 'Alle' : v === 'yes' ? 'Ja' : 'Nein'}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <span className="text-xs text-gray-400">Kontakte:</span>
          {(['all', 'yes', 'no'] as const).map(v => (
            <button key={v} onClick={() => setContactsFilter(v)}
              className={`px-2 py-1 rounded text-xs font-medium transition-colors ${contactsFilter === v ? 'bg-indigo-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}>
              {v === 'all' ? 'Alle' : v === 'yes' ? 'Ja' : 'Nein'}
            </button>
          ))}
        </div>
        {/* Sync dropdown */}
        <div className="relative shrink-0 flex items-center gap-1" ref={syncMenuRef}>
          <button
            onClick={() => !syncing && setSyncMenuOpen(o => !o)}
            disabled={syncing}
            className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {syncing
              ? <span className="animate-spin inline-block h-3.5 w-3.5 border-b-2 border-white rounded-full" />
              : <RefreshCw className="h-3.5 w-3.5" />}
            Sync
            {!syncing && <ChevronDown className="h-3.5 w-3.5 opacity-70" />}
          </button>
          {syncing && (
            <button
              onClick={cancelSync}
              className="rounded-lg border border-gray-300 px-2 py-1.5 text-xs text-gray-600 hover:bg-red-50 hover:border-red-300 hover:text-red-600 transition-colors"
              title="Sync abbrechen"
            >
              Abbrechen
            </button>
          )}
          {syncMenuOpen && (
            <div className="absolute z-50 top-full left-0 mt-1 w-56 bg-white border border-gray-200 rounded-lg shadow-lg py-1">
              <button
                onClick={() => startSync(false)}
                className="w-full text-left px-3 py-2 text-sm hover:bg-indigo-50 hover:text-indigo-700 transition-colors"
              >
                <div className="font-medium">Sync</div>
                <div className="text-xs text-gray-400">Ausstehende + leere Felder</div>
              </button>
              <button
                onClick={() => startSync(true)}
                className="w-full text-left px-3 py-2 text-sm hover:bg-indigo-50 hover:text-indigo-700 transition-colors"
              >
                <div className="font-medium">Re-Sync</div>
                <div className="text-xs text-gray-400">Alle Firmen neu synchronisieren</div>
              </button>
              {failed > 0 && (
                <>
                  <div className="border-t border-gray-100 my-1" />
                  <button
                    onClick={() => { setSyncMenuOpen(false); resetFailed() }}
                    className="w-full text-left px-3 py-2 text-sm text-red-600 hover:bg-red-50 transition-colors"
                  >
                    <div className="font-medium">{failed} fehlgeschlagen zurücksetzen</div>
                    <div className="text-xs text-red-400">Status auf ausstehend zurücksetzen</div>
                  </button>
                </>
              )}
            </div>
          )}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={handleLinkContacts}
            disabled={linking}
            className="flex items-center gap-1.5 rounded-lg bg-violet-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-violet-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {linking && <span className="animate-spin inline-block h-3.5 w-3.5 border-b-2 border-white rounded-full" />}
            {linking
              ? linkProgress
                ? `${linkProgress.linked + linkProgress.created}/${linkProgress.total}`
                : 'Verknüpfe…'
              : 'Kontakte verknüpfen'}
          </button>
          {linking && (
            <button
              onClick={cancelLinkContacts}
              className="rounded-lg border border-gray-300 px-2 py-1.5 text-xs text-gray-600 hover:bg-red-50 hover:border-red-300 hover:text-red-600 transition-colors"
              title="Verknüpfung abbrechen"
            >
              Abbrechen
            </button>
          )}
        </div>
        {linkMsg && <span className="text-xs text-violet-600">{linkMsg}</span>}
        {selectedIds.size >= 1 && (
          <div className="relative" ref={parentPickerRef}>
            <button
              onClick={() => setParentPickerOpen(o => !o)}
              disabled={assigningParent}
              className="flex items-center gap-1.5 rounded-lg bg-indigo-50 border border-indigo-200 px-3 py-1.5 text-sm font-medium text-indigo-700 hover:bg-indigo-100 disabled:opacity-50 transition-colors shrink-0"
            >
              <Network className="h-3.5 w-3.5" />
              {assigningParent ? 'Wird zugeordnet…' : `${selectedIds.size} → Muttergesellschaft`}
            </button>
            {parentPickerOpen && (
              <div className="absolute z-50 top-full right-0 mt-1 w-72 bg-white border border-gray-200 rounded-lg shadow-lg">
                <div className="p-2 border-b border-gray-100">
                  <input
                    autoFocus
                    value={parentQuery}
                    onChange={e => setParentQuery(e.target.value)}
                    placeholder="Muttergesellschaft suchen…"
                    className="w-full rounded border border-gray-200 px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                </div>
                <div className="max-h-56 overflow-y-auto py-1">
                  {parentResults.length === 0 && <p className="text-xs text-gray-400 px-3 py-2 italic">Keine Treffer</p>}
                  {parentResults
                    .filter(c => !selectedIds.has(c.id))
                    .slice(0, 15)
                    .map(c => (
                      <button
                        key={c.id}
                        onClick={() => assignParent(c.id, c.name_display ?? c.name_norm)}
                        className="w-full text-left px-3 py-1.5 text-xs hover:bg-indigo-50 hover:text-indigo-700 transition-colors"
                      >
                        <span className="font-medium">{c.name_display ?? c.name_norm}</span>
                        {c.parent_name && <span className="ml-1 text-gray-400">↑ {c.parent_name}</span>}
                      </button>
                    ))}
                </div>
              </div>
            )}
          </div>
        )}
        {selectedIds.size >= 2 && onMergeRequest && (
          <button
            onClick={() => onMergeRequest([...selectedIds])}
            className="flex items-center gap-1.5 rounded-lg bg-violet-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-violet-700 transition-colors shrink-0"
          >
            <GitMerge className="h-3.5 w-3.5" />
            {selectedIds.size} zusammenführen
          </button>
        )}
        {selectedIds.size > 0 && (
          <button
            onClick={deleteSelected}
            disabled={deleting}
            className="flex items-center gap-1.5 rounded-lg bg-red-50 border border-red-200 px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-100 disabled:opacity-50 transition-colors shrink-0"
          >
            <Trash2 className="h-3.5 w-3.5" />
            {deleting ? 'Löschen…' : `${selectedIds.size} löschen`}
          </button>
        )}
      </div>

      {/* Sync status bar */}
      {(syncing || total > 0) && (
        <div className="bg-white rounded-xl border border-gray-100 p-4 space-y-2">
          <div className="flex items-center justify-between text-xs text-gray-500">
            <span>
              {done} synchronisiert · {pending} ausstehend · {failed} fehlgeschlagen
            </span>
            {syncing && syncLive?.current_company && (
              <span className="flex items-center gap-1.5 text-indigo-500 truncate max-w-xs">
                <span className="animate-spin inline-block h-3 w-3 border-b-2 border-indigo-400 rounded-full shrink-0" />
                {syncLive.current_company}
              </span>
            )}
          </div>
          {total > 0 && (
            <div className="h-1.5 rounded-full bg-gray-100 overflow-hidden">
              <div
                className="h-full bg-emerald-500 rounded-full transition-all duration-500"
                style={{ width: `${total > 0 ? (done / total) * 100 : 0}%` }}
              />
            </div>
          )}
          {syncMsg && <p className="text-xs text-indigo-600">{syncMsg}</p>}
        </div>
      )}


      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="w-8 px-3 py-3">
                <input
                  type="checkbox"
                  checked={allSelected}
                  ref={el => { if (el) el.indeterminate = selectedIds.size > 0 && !allSelected }}
                  onChange={toggleAll}
                  className="rounded border-gray-300 text-violet-600 cursor-pointer"
                />
              </th>
              <Th k="name" label="Name" />
              <Th k="industry" label="Branche" />
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Typ</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Größe</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Standort</th>
              <Th k="sync_status" label="Status" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {sorted.length === 0 && !loading && (
              <tr>
                <td colSpan={7} className="px-4 py-12 text-center text-sm text-gray-400">
                  Keine Firmen gefunden
                </td>
              </tr>
            )}
            {sorted.map(company => {
              const location = [company.hq_city, company.hq_country].filter(Boolean).join(', ')
              const selected = selectedIds.has(company.id)
              return (
                <tr
                  key={company.id}
                  onClick={() => onOpenCompany(company.id)}
                  className={clsx('cursor-pointer transition-colors', selected ? 'bg-violet-50' : 'hover:bg-gray-50')}
                >
                  <td className="px-3" onClick={e => toggleSelect(company.id, e)}>
                    <input
                      type="checkbox"
                      checked={selected}
                      onChange={() => {}}
                      className="rounded border-gray-300 text-violet-600 cursor-pointer"
                    />
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2.5">
                      <CompanyLogo name={company.name_display || company.name_norm} website={company.website} logoData={company.logo_data} />
                      <div className="min-w-0">
                        <p className="font-medium text-gray-900 truncate max-w-[180px]">
                          {company.name_display || company.name_norm}
                        </p>
                        {company.parent_name && (
                          <p className="flex items-center gap-0.5 text-[10px] text-gray-400 truncate max-w-[180px] mt-0">
                            <ChevronsUp className="h-2.5 w-2.5 shrink-0" />
                            {company.parent_name}
                          </p>
                        )}
                        <div className="flex items-center gap-1.5 mt-0.5">
                          {(company.app_count ?? 0) > 0 && (
                            <button
                              onClick={e => { e.stopPropagation(); onNavigateToApps?.({ id: company.id, name: company.name_display ?? company.name_norm, subsidiaryIds: companies.filter(c => c.parent_company_id === company.id).map(c => c.id) }) }}
                              className="inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium bg-blue-50 text-blue-600 hover:bg-blue-100 transition-colors"
                            >
                              <Briefcase className="h-2.5 w-2.5" />
                              {company.app_count}
                            </button>
                          )}
                          {(company.contact_count ?? 0) > 0 && (
                            <button
                              onClick={e => { e.stopPropagation(); onNavigateToContacts?.({ id: company.id, name: company.name_display ?? company.name_norm, subsidiaryIds: companies.filter(c => c.parent_company_id === company.id).map(c => c.id) }) }}
                              className="inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium bg-violet-50 text-violet-600 hover:bg-violet-100 transition-colors"
                            >
                              <Users className="h-2.5 w-2.5" />
                              {company.contact_count}
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-gray-500 truncate max-w-[160px]">
                    {company.industry || '—'}
                  </td>
                  <td className="px-4 py-3">
                    {company.company_type ? (
                      <span className={clsx(
                        'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
                        COMPANY_TYPE_COLORS[company.company_type] ?? 'bg-gray-100 text-gray-600'
                      )}>
                        {COMPANY_TYPE_LABELS[company.company_type] ?? company.company_type}
                      </span>
                    ) : <span className="text-gray-400">—</span>}
                  </td>
                  <td className="px-4 py-3 text-gray-500 text-xs whitespace-nowrap">
                    {company.employee_range || '—'}
                  </td>
                  <td className="px-4 py-3 text-gray-500 text-xs whitespace-nowrap">
                    {location || '—'}
                  </td>
                  <td className="px-4 py-3">
                    {company.sync_status === 'pending' && (
                      <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium bg-yellow-100 text-yellow-700">
                        <Clock className="h-3 w-3" /> Ausstehend
                      </span>
                    )}
                    {company.sync_status === 'done' && (
                      <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium bg-green-100 text-green-700">
                        <CheckCircle className="h-3 w-3" /> Sync
                      </span>
                    )}
                    {company.sync_status === 'failed' && (
                      <span
                        className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium bg-red-100 text-red-700"
                        title={company.sync_error ?? undefined}
                      >
                        <XCircle className="h-3 w-3" /> Fehler
                      </span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-xs text-gray-400">
        <span>
          {sorted.length} {sorted.length === 1 ? 'Firma' : 'Firmen'}
          {sorted.length !== companies.length && <span className="ml-1 text-gray-300">von {companies.length}</span>}
        </span>
        {selectedIds.size > 0 && (
          <span className="text-violet-600 font-medium">{selectedIds.size} ausgewählt</span>
        )}
      </div>
    </div>
  )
}
