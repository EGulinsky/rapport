import { useState, useEffect, useCallback } from 'react'
import { X, RefreshCw, Trash2, ChevronLeft, ChevronRight } from 'lucide-react'
import { api } from '../api/client'
import type { AuditEntry } from '../types'
import clsx from 'clsx'

interface Props {
  onClose: () => void
  initialAppId?: number
}

const ACTION_LABELS: Record<string, string> = {
  create: 'Erstellt',
  update: 'Geändert',
  delete: 'Gelöscht',
  status_change: 'Status',
  merge: 'Zusammengeführt',
  import: 'Importiert',
}

const ACTION_COLORS: Record<string, string> = {
  create: 'bg-green-100 text-green-700',
  update: 'bg-blue-100 text-blue-700',
  delete: 'bg-red-100 text-red-700',
  status_change: 'bg-orange-100 text-orange-700',
  merge: 'bg-purple-100 text-purple-700',
  import: 'bg-gray-100 text-gray-600',
}

const SOURCE_LABELS: Record<string, string> = {
  user: 'Manuell',
  gmail: 'Gmail',
  icloud_mail: 'iCloud Mail',
  linkedin: 'LinkedIn',
  import: 'Excel-Import',
  merge: 'Merge',
  gcal: 'Google Kalender',
  icloud_cal: 'iCloud Kalender',
  system: 'Automatisch',
}

const PAGE_SIZE = 50

export default function AuditLogModal({ onClose, initialAppId }: Props) {
  const [entries, setEntries] = useState<AuditEntry[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(0)
  const [filterApp, setFilterApp] = useState<string>(initialAppId ? String(initialAppId) : '')
  const [clearing, setClearing] = useState(false)

  const load = useCallback(async (pg = page, appFilter = filterApp) => {
    setLoading(true)
    try {
      const appId = appFilter ? parseInt(appFilter) : undefined
      const res = await api.audit.list({
        app_id: isNaN(appId!) ? undefined : appId,
        limit: PAGE_SIZE,
        offset: pg * PAGE_SIZE,
      })
      setEntries(res.items)
      setTotal(res.total)
    } finally {
      setLoading(false)
    }
  }, [page, filterApp])

  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  function changePage(delta: number) {
    const next = page + delta
    setPage(next)
    load(next, filterApp)
  }

  function applyFilter() {
    setPage(0)
    load(0, filterApp)
  }

  async function clearLog() {
    if (!confirm('Audit-Log vollständig löschen?')) return
    setClearing(true)
    try {
      await api.audit.clear()
      setEntries([])
      setTotal(0)
    } finally {
      setClearing(false)
    }
  }

  function formatTs(ts: string) {
    const d = new Date(ts)
    return d.toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
  }

  const totalPages = Math.ceil(total / PAGE_SIZE)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-5xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200">
          <h2 className="text-base font-semibold text-gray-800">Audit-Log</h2>
          <div className="flex items-center gap-2">
            <button onClick={() => load(page, filterApp)} className="p-1.5 text-gray-400 hover:text-gray-600 rounded">
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            </button>
            <button onClick={clearLog} disabled={clearing} className="p-1.5 text-gray-400 hover:text-red-500 rounded">
              <Trash2 size={14} />
            </button>
            <button onClick={onClose} className="p-1.5 text-gray-400 hover:text-gray-600 rounded">
              <X size={16} />
            </button>
          </div>
        </div>

        {/* Filter bar */}
        <div className="flex items-center gap-3 px-5 py-2 border-b border-gray-100 bg-gray-50">
          <label className="text-xs text-gray-500 shrink-0">App-ID:</label>
          <input
            type="number"
            value={filterApp}
            onChange={e => setFilterApp(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && applyFilter()}
            placeholder="alle"
            className="w-24 text-xs border border-gray-200 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-blue-400"
          />
          <button onClick={applyFilter} className="text-xs px-2 py-1 bg-blue-600 text-white rounded hover:bg-blue-700">
            Filtern
          </button>
          <span className="ml-auto text-xs text-gray-400">{total} Einträge</span>
        </div>

        {/* Table */}
        <div className="overflow-auto flex-1">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-3 py-2 font-medium text-gray-500 w-32">Zeitpunkt</th>
                <th className="text-left px-3 py-2 font-medium text-gray-500 w-24">Aktion</th>
                <th className="text-left px-3 py-2 font-medium text-gray-500">Bewerbung</th>
                <th className="text-left px-3 py-2 font-medium text-gray-500 w-20">Quelle</th>
                <th className="text-left px-3 py-2 font-medium text-gray-500">Änderung</th>
                <th className="text-left px-3 py-2 font-medium text-gray-500 w-36">Grund</th>
              </tr>
            </thead>
            <tbody>
              {entries.length === 0 && !loading && (
                <tr><td colSpan={6} className="px-3 py-8 text-center text-gray-400">Keine Einträge</td></tr>
              )}
              {entries.map(e => (
                <tr key={e.id} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="px-3 py-2 text-gray-500 font-mono whitespace-nowrap">{formatTs(e.timestamp)}</td>
                  <td className="px-3 py-2">
                    <span className={clsx('inline-block px-1.5 py-0.5 rounded text-[10px] font-medium', ACTION_COLORS[e.action] ?? 'bg-gray-100 text-gray-600')}>
                      {ACTION_LABELS[e.action] ?? e.action}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-gray-700 max-w-[200px]">
                    {e.app_firma && (
                      <span className="truncate block">
                        <span className="font-medium">{e.app_firma}</span>
                        {e.app_rolle && <span className="text-gray-400"> – {e.app_rolle}</span>}
                      </span>
                    )}
                    {e.app_id && <span className="text-gray-300">#{e.app_id}</span>}
                  </td>
                  <td className="px-3 py-2 text-gray-500">{SOURCE_LABELS[e.source] ?? e.source}</td>
                  <td className="px-3 py-2 text-gray-600 max-w-[240px]">
                    {e.field && <span className="font-mono text-gray-400 mr-1">{e.field}:</span>}
                    {e.old_value && (
                      <span className="text-red-500 line-through mr-1">{e.old_value}</span>
                    )}
                    {e.new_value && (
                      <span className="text-green-600">{e.new_value}</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-gray-400 italic">{e.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-3 px-5 py-2 border-t border-gray-100 text-xs text-gray-500">
            <button onClick={() => changePage(-1)} disabled={page === 0} className="p-1 disabled:opacity-30 hover:text-gray-700">
              <ChevronLeft size={14} />
            </button>
            <span>Seite {page + 1} / {totalPages}</span>
            <button onClick={() => changePage(1)} disabled={page >= totalPages - 1} className="p-1 disabled:opacity-30 hover:text-gray-700">
              <ChevronRight size={14} />
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
