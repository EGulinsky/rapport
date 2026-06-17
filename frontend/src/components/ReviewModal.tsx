import { useState, useEffect } from 'react'
import { api } from '../api/client'
import type { PendingMatch, Application } from '../types'
import { MAIN_STATUS_LABELS, MAIN_STATUS_COLORS, SUB_STATUS_LABELS } from '../types'
import { Check, X, ChevronDown, Mail, Calendar, FileText, ArrowRight, Linkedin } from 'lucide-react'
import clsx from 'clsx'

const SOURCE_LABEL: Record<string, string> = {
  gmail: 'Gmail',
  gcal: 'Google Calendar',
  icloud_cal: 'iCloud Kalender',
  icloud_notes: 'iCloud Notizen',
  icloud_mail: 'iCloud Mail',
  linkedin: 'LinkedIn',
}
const EVENT_TYPE_OPTIONS = ['bewerbung', 'status', 'gespräch', 'notiz', 'angebot', 'absage']

interface Props {
  onClose: () => void
  onApproved: () => void
}

export function ReviewModal({ onClose, onApproved }: Props) {
  const [items, setItems] = useState<PendingMatch[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState<number | null>(null)
  const [batchBusy, setBatchBusy] = useState(false)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [overrides, setOverrides] = useState<Record<number, { app_id?: number; event_type?: string; datum?: string; titel?: string }>>({})
  const [allApps, setAllApps] = useState<Application[]>([])
  const [appSearch, setAppSearch] = useState<Record<number, string>>({})

  async function load() {
    setLoading(true)
    try {
      const [itemsData, appsData] = await Promise.all([
        api.review.list(),
        api.applications.list({ show_rejected: true }),
      ])
      setItems(itemsData)
      setAllApps(appsData)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  function getOverride(id: number) {
    return overrides[id] ?? {}
  }
  function setOverride(id: number, patch: Partial<typeof overrides[number]>) {
    setOverrides(o => ({ ...o, [id]: { ...o[id], ...patch } }))
  }

  function filteredApps(itemId: number) {
    const q = (appSearch[itemId] ?? '').toLowerCase()
    if (!q) return allApps.slice(0, 20)
    return allApps.filter(a =>
      a.firma.toLowerCase().includes(q) || (a.rolle ?? '').toLowerCase().includes(q)
    ).slice(0, 20)
  }

  function toggleSelect(id: number) {
    setSelected(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
  }
  function toggleAll() {
    if (selected.size === items.length) {
      setSelected(new Set())
    } else {
      setSelected(new Set(items.map(i => i.id)))
    }
  }

  async function approve(item: PendingMatch) {
    const ov = getOverride(item.id)
    const app_id = ov.app_id ?? item.suggested_app_id
    if (!app_id) return
    setSaving(item.id)
    try {
      await api.review.approve(item.id, {
        application_id: app_id,
        event_type: ov.event_type ?? item.event_type ?? undefined,
        datum: ov.datum ?? item.datum ?? undefined,
        titel: ov.titel ?? item.titel ?? undefined,
      })
      setItems(prev => prev.filter(i => i.id !== item.id))
      setSelected(s => { const n = new Set(s); n.delete(item.id); return n })
      onApproved()
    } catch (e) {
      alert(String(e))
    } finally {
      setSaving(null)
    }
  }

  async function reject(item: PendingMatch) {
    setSaving(item.id)
    try {
      await api.review.reject(item.id)
      setItems(prev => prev.filter(i => i.id !== item.id))
      setSelected(s => { const n = new Set(s); n.delete(item.id); return n })
      onApproved()
    } finally {
      setSaving(null)
    }
  }

  async function batchApprove() {
    const targets = items.filter(i => selected.has(i.id) && (getOverride(i.id).app_id ?? i.suggested_app_id))
    if (!targets.length) return
    setBatchBusy(true)
    try {
      await Promise.allSettled(targets.map(item => {
        const ov = getOverride(item.id)
        const app_id = ov.app_id ?? item.suggested_app_id!
        return api.review.approve(item.id, {
          application_id: app_id,
          event_type: ov.event_type ?? item.event_type ?? undefined,
          datum: ov.datum ?? item.datum ?? undefined,
          titel: ov.titel ?? item.titel ?? undefined,
        })
      }))
      const doneIds = new Set(targets.map(i => i.id))
      setItems(prev => prev.filter(i => !doneIds.has(i.id)))
      setSelected(s => { const n = new Set(s); doneIds.forEach(id => n.delete(id)); return n })
      onApproved()
    } finally {
      setBatchBusy(false)
    }
  }

  async function batchReject() {
    const targets = items.filter(i => selected.has(i.id))
    if (!targets.length) return
    setBatchBusy(true)
    try {
      await Promise.allSettled(targets.map(item => api.review.reject(item.id)))
      const doneIds = new Set(targets.map(i => i.id))
      setItems(prev => prev.filter(i => !doneIds.has(i.id)))
      setSelected(new Set())
      onApproved()
    } finally {
      setBatchBusy(false)
    }
  }

  const confidenceColor = (c: number) => {
    if (c >= 50) return 'text-yellow-600 bg-yellow-50'
    return 'text-red-600 bg-red-50'
  }

  function resolvedAppId(item: PendingMatch) {
    return getOverride(item.id).app_id ?? item.suggested_app_id
  }
  function resolvedAppLabel(item: PendingMatch) {
    const id = resolvedAppId(item)
    if (!id) return null
    const a = allApps.find(x => x.id === id)
    if (a) return `${a.firma} — ${a.rolle}`
    if (getOverride(item.id).app_id == null) {
      // fall back to the suggested names from the API
      if (item.suggested_app_firma) return `${item.suggested_app_firma} — ${item.suggested_app_rolle}`
    }
    return null
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <div className="w-full max-w-3xl rounded-2xl bg-white shadow-2xl flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 gap-3 flex-wrap">
          <div className="flex items-center gap-3">
            {!loading && items.length > 0 && (
              <input
                type="checkbox"
                className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                checked={selected.size === items.length}
                ref={el => { if (el) el.indeterminate = selected.size > 0 && selected.size < items.length }}
                onChange={toggleAll}
                title="Alle auswählen"
              />
            )}
            <div>
              <h2 className="text-base font-semibold text-gray-900">Manuelle Überprüfung</h2>
              <p className="text-xs text-gray-500 mt-0.5">
                {selected.size > 0 ? `${selected.size} ausgewählt` : `KI-Treffer mit <60% Konfidenz`}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {selected.size > 0 && (
              <>
                <button
                  onClick={batchApprove}
                  disabled={batchBusy}
                  className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-green-600 text-white hover:bg-green-700 disabled:opacity-50"
                >
                  <Check className="h-3.5 w-3.5" />
                  {selected.size} annehmen
                </button>
                <button
                  onClick={batchReject}
                  disabled={batchBusy}
                  className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50 disabled:opacity-50"
                >
                  <X className="h-3.5 w-3.5" />
                  {selected.size} ablehnen
                </button>
              </>
            )}
            <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400">
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="overflow-y-auto flex-1 px-6 py-4 space-y-4">
          {loading && (
            <p className="text-sm text-gray-400 text-center py-8">Lade…</p>
          )}
          {!loading && items.length === 0 && (
            <div className="text-center py-12 text-gray-400">
              <Check className="h-8 w-8 mx-auto mb-2 text-green-400" />
              <p className="text-sm">Keine offenen Einträge</p>
            </div>
          )}
          {items.map(item => {
            const ov = getOverride(item.id)
            const busy = saving === item.id
            const appId = resolvedAppId(item)
            const canApprove = !!appId
            const appLabel = resolvedAppLabel(item)
            const noSuggestion = !item.suggested_app_id
            const isStatusOnly = !!item.status_only

            return (
              <div key={item.id} className={clsx(
                "rounded-xl border p-4 space-y-3",
                isStatusOnly ? "border-violet-200 bg-violet-50/30" : "border-gray-200",
                selected.has(item.id) && "ring-2 ring-indigo-300"
              )}>
                {/* Top row */}
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-2 flex-wrap">
                    <input
                      type="checkbox"
                      className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500 mt-0.5 shrink-0"
                      checked={selected.has(item.id)}
                      onChange={() => toggleSelect(item.id)}
                    />
                    <span className="text-xs font-medium bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
                      {SOURCE_LABEL[item.source] ?? item.source}
                    </span>
                    {isStatusOnly ? (
                      <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-violet-100 text-violet-700">
                        Status-Vorschlag
                      </span>
                    ) : (
                      <span className={clsx('text-xs font-semibold px-2 py-0.5 rounded-full', confidenceColor(item.confidence))}>
                        {item.confidence}% Konfidenz
                      </span>
                    )}
                    {item.datum && (
                      <span className="text-xs text-gray-500">{item.datum}</span>
                    )}
                  </div>
                  <div className="flex gap-1.5 shrink-0">
                    <button
                      onClick={() => approve(item)}
                      disabled={busy || !canApprove}
                      className="flex items-center gap-1 text-xs font-medium px-2.5 py-1.5 rounded-lg bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <Check className="h-3.5 w-3.5" />
                      Annehmen
                    </button>
                    <button
                      onClick={() => reject(item)}
                      disabled={busy}
                      className="flex items-center gap-1 text-xs font-medium px-2.5 py-1.5 rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50 disabled:opacity-50"
                    >
                      <X className="h-3.5 w-3.5" />
                      Ablehnen
                    </button>
                  </div>
                </div>

                {/* Status change proposal */}
                {isStatusOnly && item.suggested_main_status && (
                  <div className="rounded-lg border border-violet-200 bg-violet-50 p-3">
                    <p className="text-xs font-medium text-violet-700 mb-2">
                      {item.source === 'linkedin' ? 'LinkedIn meldet Status-Änderung:' : 'KI schlägt Status-Änderung vor:'}
                    </p>
                    <div className="flex items-center gap-2">
                      <span className={clsx('text-xs font-medium px-2 py-0.5 rounded-full', item.current_main_status ? MAIN_STATUS_COLORS[item.current_main_status as keyof typeof MAIN_STATUS_COLORS] ?? 'bg-gray-100 text-gray-600' : 'bg-gray-100 text-gray-600')}>
                        {item.current_main_status ? MAIN_STATUS_LABELS[item.current_main_status as keyof typeof MAIN_STATUS_LABELS] ?? item.current_main_status : '—'}
                      </span>
                      <ArrowRight className="h-3.5 w-3.5 text-violet-400 shrink-0" />
                      <span className={clsx('text-xs font-medium px-2 py-0.5 rounded-full', MAIN_STATUS_COLORS[item.suggested_main_status as keyof typeof MAIN_STATUS_COLORS] ?? 'bg-gray-100 text-gray-600')}>
                        {MAIN_STATUS_LABELS[item.suggested_main_status as keyof typeof MAIN_STATUS_LABELS] ?? item.suggested_main_status}
                        {item.suggested_sub_status && ` – ${SUB_STATUS_LABELS[item.suggested_sub_status] ?? item.suggested_sub_status}`}
                      </span>
                    </div>
                    <p className="text-xs text-violet-600 mt-2">
                      {appLabel && <span className="font-medium">{appLabel}</span>}
                    </p>
                  </div>
                )}

                {/* Suggested / selected app (non-status-only items) */}
                {!isStatusOnly && noSuggestion && (
                  <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 space-y-2">
                    <p className="text-xs font-medium text-amber-700">Keine Stelle erkannt — bitte manuell zuordnen:</p>
                    <AppPicker
                      itemId={item.id}
                      selectedId={ov.app_id}
                      allApps={allApps}
                      apps={filteredApps(item.id)}
                      onSearch={q => setAppSearch(s => ({ ...s, [item.id]: q }))}
                      onSelect={id => setOverride(item.id, { app_id: id })}
                    />
                  </div>
                )}
                {!isStatusOnly && !noSuggestion && (
                  <div className="text-sm">
                    <span className="text-gray-500 text-xs">Zugeordnete Stelle: </span>
                    <span className="font-medium text-gray-800">{appLabel}</span>
                  </div>
                )}

                {/* Content preview (not for status-only) */}
                {!isStatusOnly && <ContentPreview item={item} />}

                {/* Editable fields (not for status-only) */}
                {!isStatusOnly && (
                  <details className="group">
                    <summary className="flex items-center gap-1 text-xs text-gray-400 cursor-pointer select-none hover:text-gray-600 list-none">
                      <ChevronDown className="h-3.5 w-3.5 transition-transform group-open:rotate-180" />
                      Felder bearbeiten
                    </summary>
                    <div className="mt-2 grid grid-cols-2 gap-2">
                      {!noSuggestion && (
                        <div className="col-span-2">
                          <label className="text-xs text-gray-500 mb-1 block">Stelle ändern</label>
                          <AppPicker
                            itemId={item.id}
                            selectedId={ov.app_id ?? item.suggested_app_id ?? undefined}
                            allApps={allApps}
                            apps={filteredApps(item.id)}
                            onSearch={q => setAppSearch(s => ({ ...s, [item.id]: q }))}
                            onSelect={id => setOverride(item.id, { app_id: id })}
                          />
                        </div>
                      )}
                      <div className="col-span-2">
                        <label className="text-xs text-gray-500 mb-1 block">Titel</label>
                        <input
                          className="w-full rounded-lg border border-gray-200 px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                          value={ov.titel ?? item.titel ?? ''}
                          onChange={e => setOverride(item.id, { titel: e.target.value })}
                        />
                      </div>
                      <div>
                        <label className="text-xs text-gray-500 mb-1 block">Datum</label>
                        <input
                          type="date"
                          className="w-full rounded-lg border border-gray-200 px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                          value={ov.datum ?? item.datum ?? ''}
                          onChange={e => setOverride(item.id, { datum: e.target.value })}
                        />
                      </div>
                      <div>
                        <label className="text-xs text-gray-500 mb-1 block">Typ</label>
                        <select
                          className="w-full rounded-lg border border-gray-200 px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
                          value={ov.event_type ?? item.event_type ?? ''}
                          onChange={e => setOverride(item.id, { event_type: e.target.value })}
                        >
                          <option value="">— auswählen —</option>
                          {EVENT_TYPE_OPTIONS.map(t => (
                            <option key={t} value={t}>{t}</option>
                          ))}
                        </select>
                      </div>
                    </div>
                  </details>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

// ── Content preview ──────────────────────────────────────────────────────────

function parseRaw(raw: string): { key: string; value: string }[] {
  const lines = raw.split('\n')
  const fields: { key: string; value: string }[] = []
  let currentKey = ''
  let currentLines: string[] = []

  for (const line of lines) {
    const m = line.match(/^([A-Za-zÄÖÜäöüß ]+):\s*(.*)$/)
    if (m && m[1].length <= 20) {
      if (currentKey) fields.push({ key: currentKey, value: currentLines.join('\n').trim() })
      currentKey = m[1].trim()
      currentLines = m[2] ? [m[2]] : []
    } else {
      currentLines.push(line)
    }
  }
  if (currentKey) fields.push({ key: currentKey, value: currentLines.join('\n').trim() })
  return fields.filter(f => f.value)
}

const SOURCE_ICON: Record<string, React.ReactNode> = {
  gmail: <Mail className="h-3.5 w-3.5" />,
  gcal: <Calendar className="h-3.5 w-3.5" />,
  icloud_cal: <Calendar className="h-3.5 w-3.5" />,
  icloud_notes: <FileText className="h-3.5 w-3.5" />,
  icloud_mail: <Mail className="h-3.5 w-3.5" />,
  linkedin: <Linkedin className="h-3.5 w-3.5" />,
}

function ContentPreview({ item }: { item: PendingMatch }) {
  const [expanded, setExpanded] = useState(false)
  const raw = item.raw_content
  const isEmail = item.source === 'gmail' || item.source === 'icloud_mail'
  const isNote = item.source === 'icloud_notes'

  if (!raw && !item.extract) return null

  if (!raw) {
    // Legacy: only extract available
    return (
      <div className="text-xs text-gray-600 bg-gray-50 rounded-lg p-3 leading-relaxed whitespace-pre-wrap">
        {item.extract}
      </div>
    )
  }

  const fields = parseRaw(raw)

  if (isEmail) {
    const from = fields.find(f => f.key === 'Von')?.value ?? ''
    const subject = fields.find(f => f.key === 'Betreff')?.value ?? item.titel ?? ''
    const bodyField = fields.find(f => f.key === 'Inhalt' || !['Von','Betreff','An','Datum','CC'].includes(f.key))
    const body = bodyField?.value ?? raw.split('\n\n').slice(1).join('\n\n').trim()
    const preview = body.slice(0, 300)
    const hasMore = body.length > 300

    return (
      <div className="rounded-lg border border-gray-200 overflow-hidden text-xs">
        <div className="bg-gray-50 px-3 py-2 border-b border-gray-200 flex items-center gap-2">
          <span className="text-gray-400">{SOURCE_ICON[item.source]}</span>
          <div className="min-w-0">
            {subject && <p className="font-medium text-gray-800 truncate">{subject}</p>}
            {from && <p className="text-gray-500 truncate">{from}</p>}
          </div>
        </div>
        <div className="px-3 py-2.5 text-gray-700 leading-relaxed">
          <p className="whitespace-pre-wrap">{expanded ? body : preview}</p>
          {hasMore && (
            <button
              onClick={() => setExpanded(e => !e)}
              className="mt-1.5 text-indigo-500 hover:text-indigo-700 font-medium"
            >
              {expanded ? 'Weniger anzeigen ▲' : `… ${body.length - 300} weitere Zeichen ▼`}
            </button>
          )}
        </div>
      </div>
    )
  }

  if (isNote) {
    const title = fields.find(f => f.key === 'Titel')?.value ?? item.titel ?? ''
    const body = raw.split('\n\n').slice(1).join('\n\n').trim() || fields.filter(f => f.key !== 'Titel').map(f => f.value).join('\n')
    const preview = body.slice(0, 400)
    const hasMore = body.length > 400

    return (
      <div className="rounded-lg border border-gray-200 overflow-hidden text-xs">
        <div className="bg-amber-50 px-3 py-2 border-b border-amber-100 flex items-center gap-2">
          <span className="text-amber-400"><FileText className="h-3.5 w-3.5" /></span>
          <p className="font-medium text-gray-800 truncate">{title}</p>
        </div>
        {body && (
          <div className="px-3 py-2.5 text-gray-700 leading-relaxed">
            <p className="whitespace-pre-wrap">{expanded ? body : preview}</p>
            {hasMore && (
              <button
                onClick={() => setExpanded(e => !e)}
                className="mt-1.5 text-indigo-500 hover:text-indigo-700 font-medium"
              >
                {expanded ? 'Weniger anzeigen ▲' : `… ${body.length - 400} weitere Zeichen ▼`}
              </button>
            )}
          </div>
        )}
      </div>
    )
  }

  // Calendar / generic: show fields as key-value table
  return (
    <div className="rounded-lg border border-gray-200 overflow-hidden text-xs">
      <div className="bg-blue-50 px-3 py-2 border-b border-blue-100 flex items-center gap-2">
        <span className="text-blue-400"><Calendar className="h-3.5 w-3.5" /></span>
        <p className="font-medium text-gray-800">{item.titel}</p>
      </div>
      <dl className="divide-y divide-gray-100">
        {fields.map(f => (
          <div key={f.key} className="flex gap-3 px-3 py-1.5">
            <dt className="text-gray-400 w-20 shrink-0">{f.key}</dt>
            <dd className="text-gray-700 whitespace-pre-wrap">{f.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

interface AppPickerProps {
  itemId: number
  selectedId?: number
  allApps: Application[]
  apps: Application[]
  onSearch: (q: string) => void  // called to filter the apps list in the parent
  onSelect: (id: number) => void
}

function AppPicker({ selectedId, allApps, apps, onSearch, onSelect }: AppPickerProps) {
  const [open, setOpen] = useState(false)
  const [inputValue, setInputValue] = useState('')
  // Always resolve the selected app from the full list so it's found even after filtering
  const selectedApp = allApps.find(a => a.id === selectedId)

  function handleFocus() {
    setInputValue('')
    onSearch('')
    setOpen(true)
  }

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    setInputValue(e.target.value)
    onSearch(e.target.value)
    setOpen(true)
  }

  function handleBlur() {
    // Restore display name on blur; onMouseDown on items uses preventDefault so blur fires after selection
    setInputValue('')
    setTimeout(() => setOpen(false), 100)
  }

  function handleSelect(a: Application) {
    onSelect(a.id)
    setInputValue('')
    onSearch('')
    setOpen(false)
  }

  const displayValue = open ? inputValue : (selectedApp ? `${selectedApp.firma} — ${selectedApp.rolle}` : '')

  return (
    <div className="relative">
      <input
        className="w-full rounded-lg border border-gray-200 px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        placeholder="Stelle suchen…"
        value={displayValue}
        onFocus={handleFocus}
        onChange={handleChange}
        onBlur={handleBlur}
      />
      {open && apps.length > 0 && (
        <ul className="absolute z-20 w-full mt-1 max-h-48 overflow-y-auto rounded-lg border border-gray-200 bg-white shadow-lg text-sm">
          {apps.map(a => (
            <li
              key={a.id}
              onMouseDown={e => { e.preventDefault(); handleSelect(a) }}
              className={clsx(
                'px-3 py-2 cursor-pointer hover:bg-indigo-50',
                a.id === selectedId && 'bg-indigo-50 font-medium'
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <span className="font-medium text-gray-800">{a.firma}</span>
                  {a.rolle && <span className="text-gray-400 ml-1 text-xs">— {a.rolle}</span>}
                </div>
                <span className={clsx('shrink-0 text-[10px] font-medium px-1.5 py-0.5 rounded-full', MAIN_STATUS_COLORS[a.main_status])}>
                  {MAIN_STATUS_LABELS[a.main_status]}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
