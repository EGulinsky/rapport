import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { Search, ArrowUpDown, Clock, CheckCircle, XCircle, RefreshCw } from 'lucide-react'
import { api } from '../api/client'
import type { CompanyProfile, CompanySyncStatus } from '../types'
import clsx from 'clsx'

type SortKey = 'name' | 'industry' | 'apps' | 'sync_status'

interface Props {
  onOpenApplication: (id: number) => void
  onOpenCompany: (id: number) => void
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

export function CompaniesView({ onOpenApplication: _onOpenApplication, onOpenCompany }: Props) {
  const [companies, setCompanies] = useState<CompanyProfile[]>([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(false)
  const [sortKey, setSortKey] = useState<SortKey>('name')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')

  const [syncing, setSyncing] = useState(false)
  const [syncMsg, setSyncMsg] = useState<string | null>(null)
  const [syncLive, setSyncLive] = useState<CompanySyncStatus | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

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
    const t = setTimeout(load, 300)
    return () => clearTimeout(t)
  }, [load])

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
          if (s.pending > 0) {
            await api.companySync.run()
          } else {
            stopPolling()
            setSyncing(false)
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

  async function startSync() {
    setSyncing(true)
    setSyncMsg(null)
    setSyncLive(null)
    try {
      await api.companySync.resetLock()
      const r = await api.companySync.run()
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
    return [...companies].sort((a, b) => {
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
  }, [companies, sortKey, sortDir])

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
        <button
          onClick={startSync}
          disabled={syncing}
          className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shrink-0"
        >
          {syncing
            ? <span className="animate-spin inline-block h-3.5 w-3.5 border-b-2 border-white rounded-full" />
            : <RefreshCw className="h-3.5 w-3.5" />}
          Firmendaten aktualisieren
        </button>
        {failed > 0 && (
          <button
            onClick={resetFailed}
            className="rounded-lg bg-red-50 border border-red-200 px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-100 transition-colors"
          >
            {failed} fehlgeschlagen — zurücksetzen
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
              <Th k="name" label="Name" />
              <Th k="industry" label="Branche" />
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Typ</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Größe</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Standort</th>
              <Th k="sync_status" label="Status" />
              <Th k="apps" label="Bewerbungen" className="text-right" />
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
              return (
                <tr
                  key={company.id}
                  onClick={() => onOpenCompany(company.id)}
                  className="hover:bg-gray-50 cursor-pointer transition-colors"
                >
                  <td className="px-4 py-3">
                    <p className="font-medium text-gray-900 truncate max-w-[200px]">
                      {company.name_display || company.name_norm}
                    </p>
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
                  <td className="px-4 py-3 text-right text-gray-700 font-medium tabular-nums">
                    {company.app_count ?? 0}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-gray-400">{sorted.length} {sorted.length === 1 ? 'Firma' : 'Firmen'}</p>
    </div>
  )
}
