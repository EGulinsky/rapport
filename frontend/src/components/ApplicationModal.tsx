import { useState, useEffect, useRef, useCallback } from 'react'
import { X, Plus, Trash2, Pencil, Check, Clock, Mail, Calendar, FileText, Phone, PenLine, Crosshair, ChevronDown, RefreshCw, Send, TrendingUp, MessageCircle, ExternalLink, Search, Paperclip, Download } from 'lucide-react'
import { api } from '../api/client'
import { StatusBadge } from './StatusBadge'
import {
  MAIN_PIPELINE, MAIN_STATUS_LABELS, MAIN_STATUS_COLORS,
  SUB_STATUS_LABELS, SUB_STATUS_SEQUENCE,
  type Application, type MainStatus, type Contact, type Event, type ManualCandidate,
} from '../types'

interface Props {
  appId: number | null
  onClose: () => void
  onSaved: () => void
}

const CONTACT_TYPES = ['HR', 'Headhunter', 'FB', 'CEO', 'Netzwerk']
const EMPTY_CONTACT = { name: '', email: '', telefon: '', typ: '', rolle: '' }

export function ApplicationModal({ appId, onClose, onSaved }: Props) {
  const [app, setApp] = useState<Application | null>(null)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<Partial<Application>>({})
  const [saving, setSaving] = useState(false)
  const [addingContact, setAddingContact] = useState(false)
  const [contactDraft, setContactDraft] = useState<Partial<Contact>>(EMPTY_CONTACT)
  const [savingContact, setSavingContact] = useState(false)
  const [editingContactId, setEditingContactId] = useState<number | null>(null)
  const [editContactDraft, setEditContactDraft] = useState<Partial<Contact>>({})
  const [addingNote, setAddingNote] = useState(false)
  const [noteDraft, setNoteDraft] = useState({ notiz: '', datum: '' })
  const [savingNote, setSavingNote] = useState(false)
  const [addingBewerbung, setAddingBewerbung] = useState(false)
  const [bewerbungDraft, setBewerbungDraft] = useState({ datum: '', titel: 'Bewerbung eingereicht' })
  const [savingBewerbung, setSavingBewerbung] = useState(false)
  const [manualOpen, setManualOpen] = useState(false)
  const [manualQuery, setManualQuery] = useState('')
  const [manualCandidates, setManualCandidates] = useState<ManualCandidate[]>([])
  const [manualLoading, setManualLoading] = useState(false)
  const [manualConflict, setManualConflict] = useState<{ candidate: ManualCandidate; conflict_app_firma: string } | null>(null)
  const [syncing, setSyncing] = useState(false)
  const [syncMenuOpen, setSyncMenuOpen] = useState(false)
  const [syncProgress, setSyncProgress] = useState<Record<string, { label: string; step: string; current: number; total: number; percent: number; done: boolean }>>({})
  const [syncResult, setSyncResult] = useState<{ created: number; errors: string[] } | null>(null)
  const syncMenuRef = useRef<HTMLDivElement>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopPolling = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
  }, [])

  const startPolling = useCallback(() => {
    stopPolling()
    pollRef.current = setInterval(async () => {
      try {
        const data = await api.sync.progress()
        // Only show: the main key for this app (targeted_{appId}) and generic sub-task keys.
        // Exclude targeted_{otherId} keys from previous/other app syncs.
        const isSubTask = (k: string) => k.startsWith('targeted_') && !/^targeted_\d+$/.test(k)
        const targeted = Object.fromEntries(
          Object.entries(data).filter(([k]) => k === `targeted_${appId}` || isSubTask(k))
        )
        setSyncProgress(targeted)
      } catch { /* ignore */ }
    }, 1000)
  }, [stopPolling])

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (syncMenuRef.current && !syncMenuRef.current.contains(e.target as Node)) setSyncMenuOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  async function runSync(reset: boolean) {
    if (!appId) return
    setSyncing(true)
    setSyncMenuOpen(false)
    setSyncResult(null)
    setSyncProgress({})
    startPolling()
    try {
      if (reset) await api.targeted.resetForApp(appId)
      await api.targeted.syncForApp(appId)  // returns immediately — sync runs in background

      // Poll for result
      for (let i = 0; i < 600; i++) {   // max 10 min
        await new Promise(r => setTimeout(r, 2000))
        const result = await api.targeted.getResult(appId)
        if (result.done) {
          setSyncResult({ created: result.created ?? 0, errors: result.errors ?? [] })
          await refreshContacts()
          onSaved()
          break
        }
      }
    } catch (e: unknown) {
      setSyncResult({ created: 0, errors: [e instanceof Error ? e.message : String(e)] })
    } finally {
      stopPolling()
      setSyncing(false)
      setSyncProgress({})
    }
  }

  useEffect(() => {
    if (!appId) return
    api.applications.get(appId).then(data => {
      setApp(data)
      setDraft(data)
    })
  }, [appId])

  if (!appId) return null

  async function save() {
    if (!appId) return
    setSaving(true)
    try {
      const updated = await api.applications.update(appId, draft)
      setApp(updated)
      setEditing(false)
      onSaved()
    } finally {
      setSaving(false)
    }
  }

  async function deleteApp() {
    if (!appId || !confirm(`Bewerbung bei "${app?.firma}" wirklich löschen?`)) return
    await api.applications.delete(appId)
    onClose()
    onSaved()
  }

  async function refreshContacts() {
    if (!appId) return
    const updated = await api.applications.get(appId)
    setApp(updated)
    setDraft(updated)
  }

  async function saveNote() {
    if (!appId || !noteDraft.notiz.trim()) return
    setSavingNote(true)
    try {
      await api.applications.addEvent(appId, {
        typ: 'notiz',
        datum: noteDraft.datum || new Date().toISOString().slice(0, 10),
        notiz: noteDraft.notiz.trim(),
      })
      await refreshContacts()
      setNoteDraft({ notiz: '', datum: '' })
      setAddingNote(false)
    } finally {
      setSavingNote(false)
    }
  }

  async function openManual() {
    if (!appId) return
    setManualOpen(true)
    setSyncMenuOpen(false)
    setManualLoading(true)
    try {
      const results = await api.targeted.candidates(appId, '')
      setManualCandidates(results)
    } finally {
      setManualLoading(false)
    }
  }

  async function searchManual() {
    if (!appId) return
    setManualLoading(true)
    try {
      const results = await api.targeted.candidates(appId, manualQuery)
      setManualCandidates(results)
    } finally {
      setManualLoading(false)
    }
  }

  async function assignCandidate(candidate: ManualCandidate, removeFromOther = false) {
    if (!appId) return
    const res = await api.targeted.assign(appId, {
      match_id: candidate.id,
      external_id: candidate.external_id,
      source: candidate.source,
      datum: candidate.datum ?? undefined,
      titel: candidate.titel ?? undefined,
      remove_from_other: removeFromOther,
    })
    if (res.conflict && !removeFromOther) {
      setManualConflict({ candidate, conflict_app_firma: res.conflict_app_firma ?? 'andere Bewerbung' })
      return
    }
    setManualConflict(null)
    setManualOpen(false)
    await refreshContacts()
  }

  async function saveBewerbung() {
    if (!appId || !bewerbungDraft.datum) return
    setSavingBewerbung(true)
    try {
      await api.applications.addEvent(appId, {
        typ: 'bewerbung',
        datum: bewerbungDraft.datum,
        titel: bewerbungDraft.titel.trim() || 'Bewerbung eingereicht',
      })
      await refreshContacts()
      setBewerbungDraft({ datum: '', titel: 'Bewerbung eingereicht' })
      setAddingBewerbung(false)
    } finally {
      setSavingBewerbung(false)
    }
  }

  async function saveContact() {
    if (!appId || !contactDraft.name) return
    setSavingContact(true)
    try {
      await api.contacts.add(appId, contactDraft)
      await refreshContacts()
      setContactDraft(EMPTY_CONTACT)
      setAddingContact(false)
    } finally {
      setSavingContact(false)
    }
  }

  async function updateContact(contactId: number) {
    if (!appId) return
    setSavingContact(true)
    try {
      await api.contacts.update(appId, contactId, editContactDraft)
      await refreshContacts()
      setEditingContactId(null)
    } finally {
      setSavingContact(false)
    }
  }

  async function deleteContact(contactId: number, name: string) {
    if (!appId || !confirm(`Kontakt "${name}" löschen?`)) return
    await api.contacts.delete(appId, contactId)
    await refreshContacts()
  }

  const field = (label: string, value?: string | null) =>
    value ? (
      <div>
        <dt className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</dt>
        <dd className="mt-0.5 text-sm text-gray-900">{value}</dd>
      </div>
    ) : null

  const STEP_LABELS: Record<string, string> = {
    prospecting: 'Anbahnung',
    applied:     'Beworben',
    hr:          'HR / HH',
    fb:          'Fachbereich',
    waiting:     'Entscheidung',
    negotiating: 'Angebot',
    signed:      'Zusage',
  }

  const reachedIdx = (() => {
    if (!app) return -1
    const idx = MAIN_PIPELINE.indexOf(app.main_status)
    if (idx >= 0) return idx
    // Rejected: infer last reached stage from timeline events
    if (!app.abgesagt || !app.events?.length) return -1
    const events = app.events
    const text = (e: { titel?: string; notiz?: string }) =>
      `${e.titel ?? ''} ${e.notiz ?? ''}`.toLowerCase()
    const gesprächCount = events.filter(e => e.typ === 'gespräch').length
    const hasBewerbung  = events.some(e => e.typ === 'bewerbung')
    const hasAngebot    = events.some(e =>
      /(angebot|salary|gehalts|verhandlung|offer letter)/i.test(text(e)))
    const hasFB         = events.some(e =>
      /(fachbereich|fach.?interview|technical|panel|2\. gespr|zweites gespr|3\. gespr)/i.test(text(e)))
    const hasWaiting    = events.some(e =>
      /(finale entscheidung|waiting|final decision|warten)/i.test(text(e)))
    let best = hasBewerbung ? MAIN_PIPELINE.indexOf('applied') : 0
    if (gesprächCount >= 1) best = Math.max(best, MAIN_PIPELINE.indexOf('hr'))
    if (gesprächCount >= 2 || hasFB) best = Math.max(best, MAIN_PIPELINE.indexOf('fb'))
    if (hasWaiting) best = Math.max(best, MAIN_PIPELINE.indexOf('waiting'))
    if (hasAngebot) best = Math.max(best, MAIN_PIPELINE.indexOf('negotiating'))
    return best
  })()

  return (
    <>
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="w-full max-w-2xl rounded-2xl bg-white shadow-2xl flex flex-col max-h-[90vh]">

        {/* Header */}
        <div className="flex items-start justify-between p-6 border-b border-gray-100">
          <div className="flex-1 min-w-0">
            {editing ? (
              <div className="space-y-2">
                <input
                  className="w-full text-lg font-semibold rounded-lg border border-gray-200 px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  value={draft.firma ?? ''}
                  onChange={e => setDraft(d => ({ ...d, firma: e.target.value }))}
                  placeholder="Firma"
                />
                <input
                  className="w-full text-sm rounded-lg border border-gray-200 px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  value={draft.rolle ?? ''}
                  onChange={e => setDraft(d => ({ ...d, rolle: e.target.value }))}
                  placeholder="Rolle"
                />
              </div>
            ) : (
              <>
                <div className="flex items-baseline gap-2">
                  <h2 className="text-lg font-semibold text-gray-900 truncate">{app?.firma}</h2>
                  <span className="text-xs text-gray-300 shrink-0 select-all">#{app?.id}</span>
                </div>
                <p className="text-sm text-gray-500 truncate">{app?.rolle}</p>
              </>
            )}
          </div>
          <div className="ml-4 flex items-center gap-1.5">
            {/* Split sync button */}
            <div className="relative flex rounded-lg border border-indigo-200" ref={syncMenuRef}>
              <button
                onClick={() => runSync(false)}
                disabled={syncing}
                title="Gezielter Sync für diese Bewerbung (KI)"
                className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-indigo-600 bg-indigo-50 hover:bg-indigo-100 disabled:opacity-50 transition-colors rounded-l-lg"
              >
                <Crosshair className={`h-3.5 w-3.5 ${syncing ? 'animate-spin' : ''}`} />
                {syncing ? 'Sync…' : 'Sync'}
              </button>
              <button
                onClick={() => setSyncMenuOpen(o => !o)}
                disabled={syncing}
                className="px-1.5 border-l border-indigo-200 text-indigo-400 bg-indigo-50 hover:bg-indigo-100 disabled:opacity-50 transition-colors rounded-r-lg"
              >
                <ChevronDown className={`h-3 w-3 transition-transform ${syncMenuOpen ? 'rotate-180' : ''}`} />
              </button>
              {syncMenuOpen && (
                <div className="absolute right-0 top-full mt-1 z-50 w-44 rounded-lg border border-gray-200 bg-white shadow-lg py-1">
                  <button
                    onClick={() => runSync(false)}
                    className="w-full text-left px-3 py-2 text-xs text-gray-700 hover:bg-gray-50 flex items-center gap-2"
                  >
                    <Crosshair className="h-3.5 w-3.5 text-indigo-400" />
                    Sync
                  </button>
                  <button
                    onClick={() => runSync(true)}
                    className="w-full text-left px-3 py-2 text-xs text-gray-700 hover:bg-gray-50 flex items-center gap-2"
                  >
                    <RefreshCw className="h-3.5 w-3.5 text-amber-400" />
                    <span>
                      Re-sync
                      <span className="block text-[10px] text-gray-400">Reset + neu einlesen</span>
                    </span>
                  </button>
                  <hr className="my-1 border-gray-100" />
                  <button
                    onClick={openManual}
                    className="w-full text-left px-3 py-2 text-xs text-gray-700 hover:bg-gray-50 flex items-center gap-2"
                  >
                    <Search className="h-3.5 w-3.5 text-green-500" />
                    <span>
                      Manuell zuordnen
                      <span className="block text-[10px] text-gray-400">Direkt aus Sync-Quellen</span>
                    </span>
                  </button>
                </div>
              )}
            </div>
            <button onClick={onClose} className="p-1 rounded-lg hover:bg-gray-100 text-gray-400">
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        {/* Lifecycle bar */}
        {app && (
          <div className="px-6 py-3 border-b border-gray-100 bg-gray-50/60">
            <div className="flex items-start">
              {MAIN_PIPELINE.map((step, idx) => {
                const isPast    = idx < reachedIdx
                const isCurrent = idx === reachedIdx && !app.abgesagt
                // Short sub-status hint for hr/fb when that step is current
                const subHint = isCurrent && app.sub_status ? (() => {
                  const m = app.sub_status!.match(/^(\d+)_(scheduled|done)$/)
                  if (!m) return null
                  const n = m[1]; const kind = m[2]
                  return n === '1'
                    ? (kind === 'scheduled' ? 'terminiert' : 'geführt')
                    : `${n}. ${kind === 'scheduled' ? 'terminiert' : 'geführt'}`
                })() : null
                return (
                  <div key={step} className="flex items-start flex-1 min-w-0">
                    {/* node */}
                    <div className="flex flex-col items-center w-full min-w-0">
                      {isCurrent ? (
                        // Active step: prominent ring + filled center
                        <div className="w-5 h-5 rounded-full shrink-0 border-2 border-indigo-600 bg-indigo-600 ring-2 ring-indigo-200 ring-offset-1 flex items-center justify-center">
                          <span className="w-1.5 h-1.5 rounded-full bg-white block" />
                        </div>
                      ) : isPast ? (
                        // Completed: muted filled with checkmark
                        <div className="w-4 h-4 rounded-full shrink-0 bg-indigo-300 flex items-center justify-center mt-0.5">
                          <span className="text-[7px] font-bold text-white leading-none">✓</span>
                        </div>
                      ) : (
                        // Future: empty
                        <div className="w-4 h-4 rounded-full shrink-0 border-2 border-gray-200 bg-white mt-0.5" />
                      )}
                      <span className={`mt-1 text-center text-[9px] leading-tight w-full px-0.5 ${
                        isCurrent ? 'text-indigo-700 font-semibold'
                        : isPast  ? 'text-indigo-300'
                        : 'text-gray-300'
                      }`}>
                        {STEP_LABELS[step]}
                      </span>
                      {subHint && (
                        <span className="text-[8px] text-indigo-400 text-center leading-tight mt-0.5 w-full px-0.5">
                          {subHint}
                        </span>
                      )}
                    </div>
                    {/* connector to next */}
                    {idx < MAIN_PIPELINE.length - 1 && (
                      <div className={`h-px shrink-0 mt-[9px] w-3 ${
                        idx < reachedIdx ? 'bg-indigo-200' : 'bg-gray-200'
                      }`} />
                    )}
                  </div>
                )
              })}
              {/* Connector to rejection node */}
              <div className={`h-px shrink-0 mt-[9px] w-3 ${
                app.abgesagt ? 'bg-red-200' : 'bg-gray-200'
              }`} />
              {/* Absage node */}
              <div className="flex flex-col items-center shrink-0">
                {app.abgesagt ? (
                  <div className="w-5 h-5 rounded-full border-2 border-red-400 bg-red-400 ring-2 ring-red-100 ring-offset-1 flex items-center justify-center">
                    <span className="text-[8px] font-bold text-white leading-none">✕</span>
                  </div>
                ) : (
                  <div className="w-4 h-4 rounded-full border-2 border-gray-200 bg-white mt-0.5" />
                )}
                <span className={`mt-1 text-center text-[9px] leading-tight ${
                  app.abgesagt ? 'text-red-500 font-semibold' : 'text-gray-300'
                }`}>Absage</span>
              </div>
            </div>
          </div>
        )}

        {/* Progress panel */}
        {syncing && Object.keys(syncProgress).length > 0 && (
          <div className="border-b border-indigo-100 bg-indigo-50 px-5 py-3 space-y-2">
            <p className="text-[10px] font-semibold text-indigo-500 uppercase tracking-wide flex items-center gap-1.5">
              <Crosshair className="h-3 w-3 animate-spin" /> Sync läuft…
            </p>
            {Object.values(syncProgress).map(p => (
              <div key={p.label} className="space-y-0.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-gray-700">{p.label}</span>
                  <span className="text-[10px] text-gray-400 tabular-nums">
                    {p.done ? '✓' : p.total > 0 ? `${p.current}/${p.total}` : '…'}
                  </span>
                </div>
                <div className="h-1 rounded-full bg-indigo-100 overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-300 ${p.done ? 'bg-green-400' : 'bg-indigo-500'}`}
                    style={{ width: `${p.done ? 100 : p.total > 0 ? Math.round(p.current / p.total * 100) : 10}%` }}
                  />
                </div>
                <p className="text-[10px] text-gray-400 truncate">{p.step}</p>
              </div>
            ))}
          </div>
        )}

        {/* Sync result banner */}
        {syncResult && (
          <div className={`px-5 py-2 text-xs flex items-center justify-between border-b ${syncResult.errors.length > 0 ? 'bg-red-50 border-red-100 text-red-700' : 'bg-green-50 border-green-100 text-green-700'}`}>
            <span>
              {syncResult.errors.length > 0
                ? `Sync: ${syncResult.errors[0]}`
                : `Sync abgeschlossen — ${syncResult.created} neue Einträge`}
            </span>
            <button onClick={() => setSyncResult(null)} className="ml-2 opacity-60 hover:opacity-100">✕</button>
          </div>
        )}

        {/* Body */}
        <div className="overflow-y-auto flex-1 p-6 space-y-6">

          {/* Status selector */}
          <div>
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Status</p>
            {editing ? (
              <div className="space-y-2">
                <div className="flex flex-wrap gap-1.5">
                  {([...MAIN_PIPELINE, 'rejected'] as MainStatus[]).map(s => (
                    <button
                      key={s}
                      type="button"
                      onClick={() => setDraft(d => ({
                        ...d,
                        main_status: s,
                        sub_status: (s === 'hr' || s === 'fb') ? (d.sub_status ?? '1_scheduled') : undefined,
                      }))}
                      className={`text-xs px-2.5 py-1 rounded-full border transition-all ${
                        draft.main_status === s
                          ? `${MAIN_STATUS_COLORS[s]} border-transparent ring-2 ring-offset-1 ring-indigo-400`
                          : 'border-gray-200 text-gray-600 hover:border-gray-300'
                      }`}
                    >
                      {MAIN_STATUS_LABELS[s]}
                    </button>
                  ))}
                </div>
                {(draft.main_status === 'hr' || draft.main_status === 'fb') && (
                  <div className="flex flex-wrap gap-1.5 pl-1 border-l-2 border-indigo-200">
                    {SUB_STATUS_SEQUENCE.map(sub => (
                      <button
                        key={sub}
                        type="button"
                        onClick={() => setDraft(d => ({ ...d, sub_status: sub }))}
                        className={`text-xs px-2.5 py-1 rounded-full border transition-all ${
                          draft.sub_status === sub
                            ? 'bg-indigo-100 text-indigo-800 border-indigo-300 font-medium'
                            : 'border-gray-200 text-gray-500 hover:border-gray-300'
                        }`}
                      >
                        {SUB_STATUS_LABELS[sub]}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <StatusBadge status={app?.main_status ?? 'applied'} subStatus={app?.sub_status} />
            )}
          </div>

          {/* Flags */}
          {editing && (
            <div className="flex gap-4">
              {([['is_headhunter', 'Headhunter']] as const).map(([key, label]) => (
                <label key={key} className="flex items-center gap-2 text-sm cursor-pointer">
                  <input
                    type="checkbox"
                    checked={!!(draft as Record<string, unknown>)[key]}
                    onChange={e => setDraft(d => ({ ...d, [key]: e.target.checked }))}
                    className="rounded border-gray-300 text-indigo-600"
                  />
                  {label}
                </label>
              ))}
            </div>
          )}

          {/* Meta fields */}
          {editing ? (
            <div className="grid grid-cols-2 gap-3">
              {[
                ['quelle', 'Quelle (LinkedIn, XING, …)'],
                ['zielfirma_bei_hh', 'Zielfirma (bei HH)'],
                ['wurde_besetzt_von', 'Besetzt von'],
              ].map(([key, placeholder]) => (
                <input
                  key={key}
                  className="rounded-lg border border-gray-200 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder={placeholder}
                  value={(draft as Record<string, string>)[key] ?? ''}
                  onChange={e => setDraft(d => ({ ...d, [key]: e.target.value }))}
                />
              ))}
              <div className="col-span-2 rounded-lg border border-gray-100 bg-gray-50 px-3 py-1.5 text-sm text-gray-500">
                <span className="text-xs text-gray-400 mr-1">Bewerbungsdatum:</span>
                {app?.datum_bewerbung
                  ? new Date(app.datum_bewerbung).toLocaleDateString('de-DE')
                  : <span className="italic">über Timeline-Ereignis "Bewerbung" setzen</span>}
              </div>
            </div>
          ) : (
            <dl className="grid grid-cols-2 gap-3">
              {field('Quelle', app?.quelle)}
              {field('Datum Bewerbung', app?.datum_bewerbung)}
              {field('Letztes Update', app?.letztes_update)}
              {field('Zielfirma (HH)', app?.zielfirma_bei_hh)}
              {field('Besetzt von', app?.wurde_besetzt_von)}
              {app?.is_headhunter && (
                <div>
                  <dt className="text-xs font-medium text-gray-500 uppercase tracking-wide">Headhunter</dt>
                  <dd className="mt-0.5 text-sm text-indigo-700 font-medium">Ja</dd>
                </div>
              )}
              {app?.ghosting && (
                <div>
                  <dt className="text-xs font-medium text-gray-500 uppercase tracking-wide">Ghosting</dt>
                  <dd className="mt-0.5 text-sm text-red-600 font-medium">Ja</dd>
                </div>
              )}
            </dl>
          )}

          {/* Stellenanzeige */}
          <div>
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">Stellenanzeige</p>
            {editing ? (
              <input
                type="url"
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                value={draft.stellenanzeige_url ?? ''}
                onChange={e => setDraft(d => ({ ...d, stellenanzeige_url: e.target.value || undefined }))}
                placeholder="https://…"
              />
            ) : app?.stellenanzeige_url ? (
              <a
                href={app.stellenanzeige_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-sm text-indigo-600 hover:text-indigo-800 hover:underline break-all"
              >
                <ExternalLink className="h-3.5 w-3.5 shrink-0" />
                {app.stellenanzeige_url}
              </a>
            ) : (
              <span className="text-gray-400 italic text-sm">Kein Link</span>
            )}
          </div>

          {/* Kommentar */}
          <div>
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">Kommentar</p>
            {editing ? (
              <textarea
                rows={3}
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                value={draft.kommentar ?? ''}
                onChange={e => setDraft(d => ({ ...d, kommentar: e.target.value }))}
                placeholder="Notizen zur Bewerbung…"
              />
            ) : (
              <p className="text-sm text-gray-700 whitespace-pre-wrap">{app?.kommentar || <span className="text-gray-400 italic">Kein Kommentar</span>}</p>
            )}
          </div>

          {/* Timeline */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide flex items-center gap-1.5">
                <Clock className="h-3.5 w-3.5" /> Verlauf
              </p>
              {!addingNote && (
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setAddingNote(true)}
                    className="flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-700"
                  >
                    <Plus className="h-3 w-3" /> Notiz
                  </button>
                  <button
                    onClick={() => setAddingBewerbung(true)}
                    className="flex items-center gap-1 text-xs text-green-600 hover:text-green-700"
                    title="Bewerbungsdatum als neues Timeline-Ereignis setzen"
                  >
                    <Plus className="h-3 w-3" /> Bewerbung
                  </button>
                </div>
              )}
            </div>

            {addingNote && (
              <div className="mb-3 rounded-lg border border-indigo-200 bg-indigo-50 p-3 space-y-2">
                <textarea
                  autoFocus
                  rows={2}
                  className="w-full rounded-md border border-gray-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder="Notiz…"
                  value={noteDraft.notiz}
                  onChange={e => setNoteDraft(d => ({ ...d, notiz: e.target.value }))}
                />
                <div className="flex items-center justify-between">
                  <input
                    type="date"
                    className="rounded-md border border-gray-200 px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    value={noteDraft.datum}
                    onChange={e => setNoteDraft(d => ({ ...d, datum: e.target.value }))}
                  />
                  <div className="flex gap-2">
                    <button type="button" onClick={() => { setAddingNote(false); setNoteDraft({ notiz: '', datum: '' }) }} className="text-xs text-gray-500 hover:text-gray-700 px-2 py-1">Abbrechen</button>
                    <button type="button" disabled={!noteDraft.notiz.trim() || savingNote} onClick={saveNote} className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50">
                      {savingNote ? 'Speichern…' : 'Speichern'}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {addingBewerbung && (
              <div className="mb-3 rounded-lg border border-green-200 bg-green-50 p-3 space-y-2">
                <p className="text-xs text-green-700 font-medium">Bewerbungsdatum setzen</p>
                <input
                  autoFocus
                  className="w-full rounded-md border border-gray-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
                  placeholder="Titel (z.B. Bewerbung eingereicht)"
                  value={bewerbungDraft.titel}
                  onChange={e => setBewerbungDraft(d => ({ ...d, titel: e.target.value }))}
                />
                <div className="flex items-center justify-between">
                  <input
                    type="date"
                    className="rounded-md border border-gray-200 px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-green-500"
                    value={bewerbungDraft.datum}
                    onChange={e => setBewerbungDraft(d => ({ ...d, datum: e.target.value }))}
                  />
                  <div className="flex gap-2">
                    <button type="button" onClick={() => { setAddingBewerbung(false); setBewerbungDraft({ datum: '', titel: 'Bewerbung eingereicht' }) }} className="text-xs text-gray-500 hover:text-gray-700 px-2 py-1">Abbrechen</button>
                    <button type="button" disabled={!bewerbungDraft.datum || savingBewerbung} onClick={saveBewerbung} className="rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700 disabled:opacity-50">
                      {savingBewerbung ? 'Speichern…' : 'Speichern'}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {(app?.events ?? []).length === 0 && !addingNote ? (
              <p className="text-sm text-gray-400 italic">Noch keine Einträge</p>
            ) : (
              <div className="relative">
                <div className="absolute left-2 top-0 bottom-0 w-px bg-gray-200" />
                <div className="space-y-3 pl-7">
                  {[...(app?.events ?? [])].sort((a, b) => (a.datum ?? '').localeCompare(b.datum ?? '')).map(ev => (
                    <TimelineEvent key={ev.id} event={ev} appId={appId!} onUpdated={refreshContacts} />
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Kontakte */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Kontakte</p>
              {!addingContact && (
                <button
                  onClick={() => setAddingContact(true)}
                  className="flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-700"
                >
                  <Plus className="h-3 w-3" /> Hinzufügen
                </button>
              )}
            </div>

            {(app?.contacts ?? []).length > 0 && (
              <div className="space-y-2 mb-3">
                {app!.contacts!.map(c => (
                  <div key={c.id} className="rounded-lg border border-gray-100 bg-gray-50 px-3 py-2 text-sm">
                    {editingContactId === c.id ? (
                      <div className="space-y-2">
                        <input
                          autoFocus
                          className="w-full rounded-md border border-gray-200 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                          value={editContactDraft.name ?? ''}
                          onChange={e => setEditContactDraft(d => ({ ...d, name: e.target.value }))}
                          placeholder="Name *"
                        />
                        <div className="grid grid-cols-2 gap-2">
                          <input className="rounded-md border border-gray-200 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" placeholder="E-Mail" value={editContactDraft.email ?? ''} onChange={e => setEditContactDraft(d => ({ ...d, email: e.target.value }))} />
                          <input className="rounded-md border border-gray-200 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" placeholder="Telefon" value={editContactDraft.telefon ?? ''} onChange={e => setEditContactDraft(d => ({ ...d, telefon: e.target.value }))} />
                          <input className="rounded-md border border-gray-200 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" placeholder="Rolle" value={editContactDraft.rolle ?? ''} onChange={e => setEditContactDraft(d => ({ ...d, rolle: e.target.value }))} />
                          <input className="rounded-md border border-gray-200 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" placeholder="Firma" value={editContactDraft.firma ?? ''} onChange={e => setEditContactDraft(d => ({ ...d, firma: e.target.value }))} />
                          <select className="col-span-2 rounded-md border border-gray-200 px-2 py-1 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500" value={editContactDraft.typ ?? ''} onChange={e => setEditContactDraft(d => ({ ...d, typ: e.target.value }))}>
                            <option value="">Typ wählen…</option>
                            {CONTACT_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                          </select>
                        </div>
                        <input className="w-full rounded-md border border-gray-200 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" placeholder="LinkedIn URL" value={editContactDraft.linkedin_url ?? ''} onChange={e => setEditContactDraft(d => ({ ...d, linkedin_url: e.target.value }))} />
                        <div className="flex justify-end gap-2 pt-1">
                          <button type="button" onClick={() => setEditingContactId(null)} className="text-xs text-gray-500 hover:text-gray-700 px-2 py-1">Abbrechen</button>
                          <button type="button" disabled={!editContactDraft.name || savingContact} onClick={() => updateContact(c.id)} className="flex items-center gap-1 rounded-md bg-indigo-600 px-2 py-1 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50">
                            <Check className="h-3 w-3" /> Speichern
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-start gap-2">
                        <div className="flex-1 min-w-0">
                          <p className="font-medium text-gray-900 truncate">{c.name}</p>
                          <p className="text-xs text-gray-500 truncate">{[c.typ, c.rolle].filter(Boolean).join(' · ')}</p>
                          {c.firma && <p className="text-xs text-gray-400 truncate">{c.firma}</p>}
                          {c.email && <p className="text-xs text-gray-400 truncate">{c.email}</p>}
                          {c.telefon && <p className="text-xs text-gray-400">{c.telefon}</p>}
                          {c.linkedin_url && <a href={c.linkedin_url} target="_blank" rel="noreferrer" className="text-xs text-indigo-500 hover:underline truncate block">LinkedIn</a>}
                        </div>
                        <div className="flex gap-1 shrink-0">
                          <button
                            onClick={() => { setEditingContactId(c.id); setEditContactDraft({ name: c.name, email: c.email, telefon: c.telefon, rolle: c.rolle, firma: c.firma, typ: c.typ, linkedin_url: c.linkedin_url }) }}
                            className="p-1 rounded hover:bg-gray-200 text-gray-400 hover:text-gray-600"
                            title="Bearbeiten"
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </button>
                          <button
                            onClick={() => deleteContact(c.id, c.name)}
                            className="p-1 rounded hover:bg-red-50 text-gray-400 hover:text-red-500"
                            title="Löschen"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {(app?.contacts ?? []).length === 0 && !addingContact && (
              <p className="text-sm text-gray-400 italic">Keine Kontakte hinterlegt</p>
            )}

            {addingContact && (
              <div className="rounded-lg border border-indigo-200 bg-indigo-50 p-3 space-y-2">
                <input
                  autoFocus
                  className="w-full rounded-md border border-gray-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder="Name *"
                  value={contactDraft.name ?? ''}
                  onChange={e => setContactDraft(d => ({ ...d, name: e.target.value }))}
                />
                <div className="grid grid-cols-2 gap-2">
                  <input
                    className="rounded-md border border-gray-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    placeholder="E-Mail"
                    value={contactDraft.email ?? ''}
                    onChange={e => setContactDraft(d => ({ ...d, email: e.target.value }))}
                  />
                  <input
                    className="rounded-md border border-gray-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    placeholder="Telefon"
                    value={contactDraft.telefon ?? ''}
                    onChange={e => setContactDraft(d => ({ ...d, telefon: e.target.value }))}
                  />
                  <input
                    className="rounded-md border border-gray-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    placeholder="Rolle"
                    value={contactDraft.rolle ?? ''}
                    onChange={e => setContactDraft(d => ({ ...d, rolle: e.target.value }))}
                  />
                  <input
                    className="rounded-md border border-gray-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    placeholder="Firma"
                    value={contactDraft.firma ?? ''}
                    onChange={e => setContactDraft(d => ({ ...d, firma: e.target.value }))}
                  />
                  <select
                    className="col-span-2 rounded-md border border-gray-200 px-2 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    value={contactDraft.typ ?? ''}
                    onChange={e => setContactDraft(d => ({ ...d, typ: e.target.value }))}
                  >
                    <option value="">Typ wählen…</option>
                    {CONTACT_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>
                <div className="flex justify-end gap-2 pt-1">
                  <button
                    type="button"
                    onClick={() => { setAddingContact(false); setContactDraft(EMPTY_CONTACT) }}
                    className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700"
                  >
                    <Trash2 className="h-3 w-3" /> Abbrechen
                  </button>
                  <button
                    type="button"
                    disabled={!contactDraft.name || savingContact}
                    onClick={saveContact}
                    className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                  >
                    {savingContact ? 'Speichern…' : 'Speichern'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-6 border-t border-gray-100 bg-gray-50 rounded-b-2xl">
          <button
            onClick={deleteApp}
            className="text-sm text-red-600 hover:text-red-700 hover:underline"
          >
            Löschen
          </button>
          <div className="flex gap-3">
            {editing ? (
              <>
                <button onClick={() => { setEditing(false); setDraft(app ?? {}) }} className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100">
                  Abbrechen
                </button>
                <button onClick={save} disabled={saving} className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60">
                  {saving ? 'Speichern…' : 'Speichern'}
                </button>
              </>
            ) : (
              <button onClick={() => setEditing(true)} className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700">
                Bearbeiten
              </button>
            )}
          </div>
        </div>
      </div>
    </div>

    {/* Manual assign dialog */}
    {manualOpen && (
      <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4" onClick={e => { if (e.target === e.currentTarget) { setManualOpen(false); setManualConflict(null) } }}>
        <div className="w-full max-w-lg rounded-2xl bg-white shadow-2xl flex flex-col max-h-[80vh]">
          <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
            <h3 className="font-semibold text-gray-900 text-sm">Manuell zuordnen</h3>
            <button onClick={() => { setManualOpen(false); setManualConflict(null) }} className="p-1 rounded hover:bg-gray-100 text-gray-400">
              <X className="h-4 w-4" />
            </button>
          </div>
          {manualConflict ? (
            <div className="p-5 space-y-4">
              <p className="text-sm text-gray-700">
                Dieser Eintrag ist bereits mit <strong>{manualConflict.conflict_app_firma}</strong> verknüpft.
                Was soll passieren?
              </p>
              <div className="flex gap-2 justify-end">
                <button onClick={() => setManualConflict(null)} className="text-xs text-gray-500 hover:text-gray-700 px-3 py-2">Abbrechen</button>
                <button onClick={() => assignCandidate(manualConflict.candidate, false)} className="rounded-md border border-gray-200 px-3 py-2 text-xs hover:bg-gray-50">Beide verknüpfen</button>
                <button onClick={() => assignCandidate(manualConflict.candidate, true)} className="rounded-md bg-indigo-600 px-3 py-2 text-xs text-white hover:bg-indigo-700">Aus anderer Bewerbung entfernen</button>
              </div>
            </div>
          ) : (
            <>
              <div className="px-5 py-3 border-b border-gray-100 flex gap-2">
                <input
                  className="flex-1 rounded-lg border border-gray-200 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder="Suchen…"
                  value={manualQuery}
                  onChange={e => setManualQuery(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && searchManual()}
                />
                <button onClick={searchManual} disabled={manualLoading} className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm text-white hover:bg-indigo-700 disabled:opacity-50">
                  <Search className="h-4 w-4" />
                </button>
              </div>
              <div className="overflow-y-auto flex-1 p-3 space-y-3">
                {manualLoading && <p className="text-sm text-gray-400 text-center py-4">Lädt…</p>}
                {!manualLoading && manualCandidates.length === 0 && (
                  <p className="text-sm text-gray-400 italic text-center py-4">Keine Treffer</p>
                )}
                {!manualLoading && (() => {
                  const SOURCE_ORDER = ['gmail','gcal','icloud_mail','icloud_cal','icloud_notes','pending','event']
                  const grouped: Record<string, typeof manualCandidates> = {}
                  manualCandidates.forEach(c => {
                    const key = c.source || 'event'
                    ;(grouped[key] ??= []).push(c)
                  })
                  const keys = [
                    ...SOURCE_ORDER.filter(k => grouped[k]),
                    ...Object.keys(grouped).filter(k => !SOURCE_ORDER.includes(k)),
                  ]
                  return keys.map(src => {
                    const items = grouped[src]
                    const meta = SOURCE_META[src]
                    const label = meta?.label ?? src
                    const cls   = meta?.cls   ?? 'bg-gray-50 text-gray-600 border-gray-200'
                    return (
                      <details key={src} open className="text-xs">
                        <summary className="flex items-center gap-1.5 cursor-pointer select-none list-none mb-1.5">
                          <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium ${cls}`}>
                            {meta?.icon}{label}
                          </span>
                          <span className="text-gray-400">({items.length})</span>
                        </summary>
                        <div className="space-y-1.5 pl-1">
                          {items.map(c => (
                            <button
                              key={c.id}
                              onClick={() => assignCandidate(c)}
                              className="w-full text-left rounded-lg border border-gray-200 hover:border-indigo-300 hover:bg-indigo-50 p-3 transition-colors"
                            >
                              <div className="min-w-0">
                                <p className="text-sm font-medium text-gray-800 truncate">{c.titel || c.event_type || c.source}</p>
                                {c.datum && <p className="text-xs text-gray-500">{new Date(c.datum).toLocaleDateString('de-DE')}</p>}
                                {c.extract && <p className="text-xs text-gray-400 truncate mt-0.5">{c.extract}</p>}
                                {c.suggested_app_firma && <p className="text-xs text-amber-600 mt-0.5">Vorschlag: {c.suggested_app_firma}</p>}
                              </div>
                            </button>
                          ))}
                        </div>
                      </details>
                    )
                  })
                })()}
              </div>
            </>
          )}
        </div>
      </div>
    )}
    </>
  )
}

const EVENT_STYLES: Record<string, { dot: string; label: string }> = {
  bewerbung: { dot: 'bg-green-500',  label: 'Bewerbung' },
  status:    { dot: 'bg-indigo-500', label: 'Status' },
  notiz:     { dot: 'bg-gray-400',   label: 'Notiz' },
  gespräch:  { dot: 'bg-purple-500', label: 'Gespräch' },
}

function getEventIcon(event: Event): { icon: React.ReactNode; bg: string; fg: string } {
  const sz = 'h-[9px] w-[9px]'
  const src = event.source
  if (src === 'icloud_calls' || src === 'call') return { icon: <Phone className={sz} />, bg: 'bg-green-100', fg: 'text-green-700' }
  if (src === 'gmail') return { icon: <Mail className={sz} />, bg: 'bg-red-100', fg: 'text-red-600' }
  if (src === 'icloud_mail') return { icon: <Mail className={sz} />, bg: 'bg-sky-100', fg: 'text-sky-600' }
  if (src === 'gcal') return { icon: <Calendar className={sz} />, bg: 'bg-blue-100', fg: 'text-blue-600' }
  if (src === 'icloud_cal') return { icon: <Calendar className={sz} />, bg: 'bg-sky-100', fg: 'text-sky-700' }
  if (src === 'icloud_notes' || src === 'notes') return { icon: <FileText className={sz} />, bg: 'bg-amber-100', fg: 'text-amber-700' }
  if (src === 'icloud_todo') return { icon: <FileText className={sz} />, bg: 'bg-orange-100', fg: 'text-orange-700' }
  const typ = event.typ
  if (typ === 'bewerbung') return { icon: <Send className={sz} />, bg: 'bg-green-100', fg: 'text-green-700' }
  if (typ === 'status') return { icon: <TrendingUp className={sz} />, bg: 'bg-indigo-100', fg: 'text-indigo-600' }
  if (typ === 'gespräch') return { icon: <MessageCircle className={sz} />, bg: 'bg-purple-100', fg: 'text-purple-600' }
  return { icon: <PenLine className={sz} />, bg: 'bg-gray-100', fg: 'text-gray-500' }
}

const SOURCE_META: Record<string, { icon: React.ReactNode; label: string; cls: string }> = {
  gmail:        { icon: <Mail className="h-3 w-3" />,     label: 'Gmail',          cls: 'bg-red-50 text-red-600 border-red-100' },
  gcal:         { icon: <Calendar className="h-3 w-3" />, label: 'Google Kalender',cls: 'bg-blue-50 text-blue-600 border-blue-100' },
  icloud_mail:  { icon: <Mail className="h-3 w-3" />,     label: 'iCloud Mail',    cls: 'bg-sky-50 text-sky-600 border-sky-100' },
  icloud_cal:   { icon: <Calendar className="h-3 w-3" />, label: 'iCloud Kalender',cls: 'bg-sky-50 text-sky-700 border-sky-100' },
  icloud_notes: { icon: <FileText className="h-3 w-3" />, label: 'iCloud Notizen', cls: 'bg-yellow-50 text-yellow-700 border-yellow-100' },
  icloud_todo:  { icon: <FileText className="h-3 w-3" />, label: 'Erinnerungen',   cls: 'bg-orange-50 text-orange-700 border-orange-100' },
  notes:        { icon: <FileText className="h-3 w-3" />, label: 'Notizen',        cls: 'bg-yellow-50 text-yellow-700 border-yellow-100' },
  call:         { icon: <Phone className="h-3 w-3" />,    label: 'Anruf',          cls: 'bg-green-50 text-green-700 border-green-100' },
}

function buildDeepLink(source: string | undefined, external_id: string | undefined): string | null {
  if (!source || !external_id) return null
  // Strip status-suffix used for PendingMatch keys (e.g. "abc__status")
  const rawId = external_id.replace(/__status$/, '')
  switch (source) {
    case 'gmail':
      return `https://mail.google.com/mail/u/0/#all/${rawId}`
    case 'gcal':
      return `https://calendar.google.com/calendar/r/eventedit/${btoa(rawId)}`
    case 'icloud_mail':
      return `message://${rawId}`
    case 'icloud_cal':
      return `x-apple-calevent:///${rawId}`
    case 'icloud_notes':
      return `applenotes://${rawId}`
    default:
      return null
  }
}

function SourceBadge({ source, external_id }: { source?: string; external_id?: string }) {
  if (!source) return null
  const meta = SOURCE_META[source]
  const deepLink = buildDeepLink(source, external_id)
  const cls = meta
    ? `inline-flex items-center gap-0.5 rounded-full border px-1.5 py-0.5 text-[10px] font-medium ${meta.cls}`
    : 'inline-flex items-center rounded-full border px-1.5 py-0.5 text-[10px] font-medium bg-gray-50 text-gray-500 border-gray-200'
  const label = meta ? meta.label : source
  if (deepLink) {
    return (
      <a href={deepLink} target="_blank" rel="noreferrer" className={`${cls} hover:opacity-80 cursor-pointer`} title="In App öffnen">
        {label} <ExternalLink className="h-2.5 w-2.5 opacity-60" />
      </a>
    )
  }
  return <span className={cls}>{label}</span>
}

const EVENT_TYPES = ['bewerbung', 'status', 'notiz', 'gespräch'] as const

function TimelineEvent({ event, appId, onUpdated }: { event: Event; appId: number; onUpdated: () => void }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState({ typ: event.typ, datum: event.datum ?? '', titel: event.titel ?? '', notiz: event.notiz ?? '' })
  const [saving, setSaving] = useState(false)

  const style = EVENT_STYLES[event.typ] ?? { dot: 'bg-gray-300', label: event.typ }
  const dateStr = event.datum
    ? new Date(event.datum).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })
    : null
  // Extract leading time from notiz, e.g. "10:30–10:50 Uhr (20min)" or "10:31 Uhr"
  const timeStr = (() => {
    const m = (event.notiz ?? '').match(/^(\d{1,2}:\d{2}(?:–\d{1,2}:\d{2})?\s*Uhr)/)
    return m ? m[1] : null
  })()

  async function save() {
    setSaving(true)
    try {
      await api.applications.updateEvent(appId, event.id, {
        typ: draft.typ,
        datum: draft.datum || undefined,
        titel: draft.titel || undefined,
        notiz: draft.notiz || undefined,
      })
      onUpdated()
      setEditing(false)
    } finally {
      setSaving(false)
    }
  }

  async function deleteEvent() {
    if (!confirm('Eintrag löschen?')) return
    await api.applications.deleteEvent(appId, event.id)
    onUpdated()
  }

  if (editing) {
    const { icon: editIcon, bg: editBg, fg: editFg } = getEventIcon(event)
    return (
      <div className="relative">
        <div className={`absolute -left-5 top-1.5 h-[18px] w-[18px] rounded-full border-2 border-white flex items-center justify-center ${editBg}`}>
          <span className={editFg}>{editIcon}</span>
        </div>
        <div className="rounded-lg border border-indigo-200 bg-indigo-50 p-3 space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <select
              className="rounded-md border border-gray-200 px-2 py-1.5 text-xs bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
              value={draft.typ}
              onChange={e => setDraft(d => ({ ...d, typ: e.target.value }))}
            >
              {EVENT_TYPES.map(t => (
                <option key={t} value={t}>{EVENT_STYLES[t]?.label ?? t}</option>
              ))}
            </select>
            <input
              type="date"
              className="rounded-md border border-gray-200 px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
              value={draft.datum}
              onChange={e => setDraft(d => ({ ...d, datum: e.target.value }))}
            />
          </div>
          <input
            className="w-full rounded-md border border-gray-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="Titel"
            value={draft.titel}
            onChange={e => setDraft(d => ({ ...d, titel: e.target.value }))}
          />
          <textarea
            rows={2}
            className="w-full rounded-md border border-gray-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="Notiz"
            value={draft.notiz}
            onChange={e => setDraft(d => ({ ...d, notiz: e.target.value }))}
          />
          <div className="flex justify-end gap-2 pt-1">
            <button type="button" onClick={() => setEditing(false)} className="text-xs text-gray-500 hover:text-gray-700 px-2 py-1">Abbrechen</button>
            <button type="button" disabled={saving} onClick={save} className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50">
              {saving ? 'Speichern…' : 'Speichern'}
            </button>
          </div>
        </div>
      </div>
    )
  }

  const { icon: evIcon, bg: evBg, fg: evFg } = getEventIcon(event)
  return (
    <div className="relative group">
      <div className={`absolute -left-5 top-1 h-[18px] w-[18px] rounded-full border-2 border-white flex items-center justify-center ${evBg}`}>
        <span className={evFg}>{evIcon}</span>
      </div>
      <div className="text-xs text-gray-400 mb-0.5 flex items-center gap-2 flex-wrap">
        <span>{dateStr ?? <span className="italic">kein Datum</span>}{timeStr && <span className="text-gray-400">, {timeStr}</span>}</span>
        <span className="uppercase tracking-wide font-medium text-gray-400">{style.label}</span>
        <SourceBadge source={event.source} external_id={event.external_id} />
        <span className="ml-auto hidden group-hover:flex items-center gap-1">
          <button
            onClick={() => { setDraft({ typ: event.typ, datum: event.datum ?? '', titel: event.titel ?? '', notiz: event.notiz ?? '' }); setEditing(true) }}
            className="p-0.5 rounded hover:bg-gray-200 text-gray-400 hover:text-gray-600"
            title="Bearbeiten"
          >
            <Pencil className="h-3 w-3" />
          </button>
          <button
            onClick={deleteEvent}
            className="p-0.5 rounded hover:bg-red-50 text-gray-400 hover:text-red-500"
            title="Löschen"
          >
            <Trash2 className="h-3 w-3" />
          </button>
        </span>
      </div>
      {event.titel && <p className="text-sm font-medium text-gray-800">{event.titel}</p>}
      {event.autor && <p className="text-xs text-gray-500 italic">{event.autor}</p>}
      {event.notiz && <p className="text-sm text-gray-600 whitespace-pre-wrap">{event.notiz}</p>}
      {(event.attachments ?? []).length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {event.attachments!.map(att => (
            <a
              key={att.id}
              href={api.attachments.download(att.id)}
              download={att.filename}
              className="inline-flex items-center gap-1 rounded border border-gray-200 bg-gray-50 px-2 py-0.5 text-xs text-gray-600 hover:bg-gray-100"
            >
              <Paperclip className="h-3 w-3 text-gray-400" />
              <span className="truncate max-w-[160px]">{att.filename}</span>
              {att.size_bytes && (
                <span className="text-gray-400">({(att.size_bytes / 1024).toFixed(0)} KB)</span>
              )}
              <Download className="h-2.5 w-2.5 text-gray-400" />
            </a>
          ))}
        </div>
      )}
    </div>
  )
}
