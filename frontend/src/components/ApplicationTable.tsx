import { useState, useMemo } from 'react'
import { ArrowUpDown, ExternalLink } from 'lucide-react'
import { StatusBadge } from './StatusBadge'
import { StatusPopover } from './StatusPopover'
import { MAIN_PIPELINE, MAIN_STATUS_LABELS, SUB_STATUS_LABELS, SUB_STATUS_SEQUENCE } from '../types'
import type { Application, MainStatus } from '../types'

const SUB_ORDER = Object.fromEntries(SUB_STATUS_SEQUENCE.map((s, i) => [s, i]))
import { api } from '../api/client'
import clsx from 'clsx'

interface Props {
  applications: Application[]
  onSelect: (id: number) => void
  onStatusChanged: () => void
  selectedIds?: Set<number>
  onToggleSelect?: (id: number) => void
}

type SortKey = 'firma' | 'datum_bewerbung' | 'letztes_update' | 'main_status'

export function ApplicationTable({ applications, onSelect, onStatusChanged, selectedIds, onToggleSelect }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>('datum_bewerbung')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [popoverId, setPopoverId] = useState<number | null>(null)

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('asc') }
  }

  async function handleStatusSelect(appId: number, main: MainStatus, sub?: string) {
    await api.applications.update(appId, { main_status: main, sub_status: sub ?? undefined })
    onStatusChanged()
  }

  const sorted = useMemo(() => {
    return [...applications].sort((a, b) => {
      let av: string | number
      let bv: string | number
      if (sortKey === 'main_status') {
        const mainA = MAIN_PIPELINE.indexOf(a.main_status)
        const mainB = MAIN_PIPELINE.indexOf(b.main_status)
        const ma = mainA === -1 ? 99 : mainA
        const mb = mainB === -1 ? 99 : mainB
        if (ma !== mb) return sortDir === 'asc' ? ma - mb : mb - ma
        // secondary: sub_status order within same main
        const sa = a.sub_status ? (SUB_ORDER[a.sub_status] ?? 99) : -1
        const sb = b.sub_status ? (SUB_ORDER[b.sub_status] ?? 99) : -1
        return sa - sb
      } else {
        av = a[sortKey] ?? ''
        bv = b[sortKey] ?? ''
      }
      const cmp = typeof av === 'number' && typeof bv === 'number'
        ? av - bv
        : String(av).localeCompare(String(bv), 'de')
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [applications, sortKey, sortDir])

  const Th = ({ k, label }: { k: SortKey; label: string }) => (
    <th
      className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide cursor-pointer hover:text-gray-900 select-none"
      onClick={() => toggleSort(k)}
    >
      <span className="flex items-center gap-1">
        {label}
        <ArrowUpDown className={clsx('h-3 w-3', sortKey === k ? 'text-indigo-600' : 'text-gray-300')} />
      </span>
    </th>
  )

  if (applications.length === 0) {
    return (
      <div className="py-16 text-center text-gray-400 text-sm">
        Keine Bewerbungen gefunden
      </div>
    )
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
      <table className="w-full text-sm">
        <thead className="border-b border-gray-100 bg-gray-50">
          <tr>
            {onToggleSelect && (
              <th className="pl-4 pr-2 py-3 w-8">
                <input
                  type="checkbox"
                  checked={selectedIds ? applications.length > 0 && selectedIds.size === applications.length : false}
                  ref={el => {
                    if (el) el.indeterminate = !!(selectedIds && selectedIds.size > 0 && selectedIds.size < applications.length)
                  }}
                  onChange={() => {
                    if (!selectedIds || !onToggleSelect) return
                    const allSelected = selectedIds.size === applications.length
                    applications.forEach(a => {
                      if (allSelected ? selectedIds.has(a.id) : !selectedIds.has(a.id)) onToggleSelect(a.id)
                    })
                  }}
                  className="rounded border-gray-300 text-indigo-600 cursor-pointer"
                />
              </th>
            )}
            <th className="px-3 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide w-10">#</th>
            <Th k="firma" label="Firma / Rolle" />
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Quelle</th>
            <Th k="main_status" label="Status" />
            <Th k="datum_bewerbung" label="Beworben" />
            <Th k="letztes_update" label="Update" />
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Nächster Schritt</th>
            <th className="px-4 py-3" />
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {sorted.map((app, idx) => {
            const prev = sorted[idx - 1]
            const groupBreak = sortKey === 'main_status' && (
              !prev ||
              prev.main_status !== app.main_status ||
              (prev.sub_status ?? null) !== (app.sub_status ?? null)
            )
            const groupLabel = groupBreak
              ? (app.sub_status
                  ? `${MAIN_STATUS_LABELS[app.main_status]} · ${SUB_STATUS_LABELS[app.sub_status] ?? app.sub_status}`
                  : MAIN_STATUS_LABELS[app.main_status])
              : null
            return (
              <>
                {groupLabel && (
                  <tr key={`grp-${app.main_status}-${app.sub_status ?? 'none'}`} className="bg-gray-50/80">
                    <td colSpan={onToggleSelect ? 9 : 8} className="px-4 py-1.5 text-[11px] font-semibold text-gray-400 uppercase tracking-wide">
                      {groupLabel}
                    </td>
                  </tr>
                )}
                <tr
                  key={app.id}
                  onClick={() => onSelect(app.id)}
              className={clsx(
                'cursor-pointer transition-colors',
                app.abgesagt
                  ? 'bg-rose-50/40 opacity-65 hover:bg-rose-50/60'
                  : 'hover:bg-indigo-50/40',
                selectedIds?.has(app.id) && 'bg-indigo-50/60'
              )}
            >
              {onToggleSelect && (
                <td className="pl-4 pr-2 py-3 w-8" onClick={e => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    checked={selectedIds?.has(app.id) ?? false}
                    onChange={() => onToggleSelect(app.id)}
                    className="rounded border-gray-300 text-indigo-600 cursor-pointer"
                  />
                </td>
              )}
              <td className="px-3 py-3 text-xs text-gray-400 font-mono whitespace-nowrap select-all align-top">{app.id}</td>
              <td className="px-4 py-3">
                <div>
                  {app.is_headhunter ? (
                    <>
                      <div className="flex items-center gap-1.5 leading-tight">
                        <span className="inline-flex items-center rounded px-1 py-0.5 text-[10px] font-semibold bg-indigo-100 text-indigo-700 shrink-0">HH</span>
                        <span className="text-xs text-indigo-700 font-medium truncate">{app.firma}</span>
                      </div>
                      {app.zielfirma_bei_hh ? (
                        <p className="font-medium text-gray-900 leading-tight mt-0.5">→ {app.zielfirma_bei_hh}</p>
                      ) : (
                        <p className="text-xs text-gray-400 italic leading-tight mt-0.5">Zielfirma unbekannt</p>
                      )}
                    </>
                  ) : (
                    <p className={clsx('font-medium leading-tight', app.abgesagt ? 'text-gray-500 line-through decoration-red-300' : 'text-gray-900')}>{app.firma}</p>
                  )}
                  <p className="text-xs text-gray-500 leading-tight mt-0.5">{app.rolle}</p>
                </div>
              </td>
              <td className="px-4 py-3 text-xs text-gray-500">{app.quelle || '—'}</td>
              <td className="px-4 py-3">
                <div className="relative inline-block">
                  <button
                    type="button"
                    onClick={e => { e.stopPropagation(); setPopoverId(popoverId === app.id ? null : app.id) }}
                    className="rounded focus:outline-none focus:ring-2 focus:ring-indigo-400"
                    title="Status ändern"
                  >
                    <StatusBadge status={app.main_status} subStatus={app.sub_status} size="sm" />
                  </button>
                  {popoverId === app.id && (
                    <StatusPopover
                      currentMain={app.main_status}
                      currentSub={app.sub_status}
                      onSelect={(main, sub) => {
                        handleStatusSelect(app.id, main, sub)
                        setPopoverId(null)
                      }}
                      onClose={() => setPopoverId(null)}
                    />
                  )}
                </div>
                {app.ghosting && <span className="ml-1 text-xs text-orange-500">👻</span>}
              </td>
              <td className="px-4 py-3 text-xs text-gray-500 whitespace-nowrap">
                {app.datum_bewerbung ? new Date(app.datum_bewerbung).toLocaleDateString('de-DE') : '—'}
              </td>
              <td className="px-4 py-3 text-xs text-gray-500 whitespace-nowrap">
                {app.letztes_update ? new Date(app.letztes_update).toLocaleDateString('de-DE') : '—'}
              </td>
              <td className="px-4 py-3 text-xs max-w-[220px]">
                {app.naechster_schritt ? (
                  <span className={clsx(
                    'inline-block rounded px-1.5 py-0.5 text-[11px] font-medium leading-tight',
                    app.naechster_schritt.startsWith('Gespräch') ? 'bg-indigo-50 text-indigo-700' :
                    app.naechster_schritt.startsWith('Kein Feedback') || app.naechster_schritt.startsWith('Keine Reaktion') ? 'bg-orange-50 text-orange-700' :
                    app.naechster_schritt.startsWith('Evtl.') || app.naechster_schritt.startsWith('Feedback aus') ? 'bg-yellow-50 text-yellow-700' :
                    'bg-gray-50 text-gray-600'
                  )}>
                    {app.naechster_schritt}
                  </span>
                ) : '—'}
              </td>
              <td className="px-4 py-3 text-right">
                <ExternalLink className="h-3.5 w-3.5 text-gray-300 group-hover:text-indigo-400" />
              </td>
            </tr>
              </>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
