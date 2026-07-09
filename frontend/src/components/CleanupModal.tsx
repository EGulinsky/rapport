import { useState, useEffect, useRef, useCallback } from 'react'
import { X, Trash2, CheckCircle, AlertCircle, ChevronDown, ChevronRight, Loader2, Sparkles } from 'lucide-react'
import { api } from '../api/client'
import type { CleanupPreview, CleanupResult, CleanupScope, AppGroup, ContactGroup, CompanyGroup, EventGroup } from '../types'
import clsx from 'clsx'

interface Props {
  onClose: () => void
  onDone: () => void
  scope?: CleanupScope
  scopeLabel?: string
}

type Phase = 'loading' | 'preview' | 'running' | 'done' | 'error'

interface ProgressEntry {
  label: string
  step: string
  current: number
  total: number
  percent: number
  done: boolean
}

export function CleanupModal({ onClose, onDone, scope, scopeLabel }: Props) {
  const [phase, setPhase] = useState<Phase>('loading')
  const [preview, setPreview] = useState<CleanupPreview | null>(null)
  const [result, setResult] = useState<CleanupResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [progress, setProgress] = useState<ProgressEntry | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopPolling = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
  }, [])

  const loadPreview = useCallback(() => {
    return api.cleanup.preview(scope)
      .then(p => { setPreview(p); setPhase('preview') })
      .catch(e => { setError(String(e)); setPhase('error') })
  }, [scope])

  useEffect(() => { loadPreview() }, [loadPreview])

  useEffect(() => () => stopPolling(), [stopPolling])

  async function runCleanup() {
    setPhase('running')
    setProgress(null)

    pollRef.current = setInterval(async () => {
      try {
        const data = await api.cleanup.progress()
        const entry = data['cleanup']
        if (entry) setProgress(entry)
      } catch { /* ignore */ }
    }, 600)

    try {
      const res = await api.cleanup.run(scope)
      stopPolling()
      setResult(res)
      setPhase('done')
      // Defer so React renders the done/error phase before unmounting
      setTimeout(() => onDone(), 200)
    } catch (e) {
      stopPolling()
      setError(String(e))
      setPhase('error')
    }
  }

  const totalIssues = preview
    ? preview.applications.length + preview.contacts.length + preview.companies.length + preview.events.length + preview.cross_app_events.length
    : 0

  const totalRemove = preview
    ? preview.applications.reduce((s, g) => s + g.remove.length, 0)
      + preview.contacts.reduce((s, g) => s + g.remove.length, 0)
      + preview.companies.reduce((s, g) => s + g.remove.length, 0)
      + preview.events.reduce((s, g) => s + g.remove.length, 0)
      + preview.cross_app_events.reduce((s, g) => s + g.remove.length, 0)
    : 0

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={e => e.target === e.currentTarget && phase !== 'running' && onClose()}
    >
      <div className="w-full max-w-2xl rounded-2xl bg-white shadow-2xl flex flex-col max-h-[90vh]">

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100 shrink-0">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-indigo-500" />
            <h2 className="text-sm font-semibold text-gray-900">Duplikate bereinigen{scopeLabel ? ` — ${scopeLabel}` : ''}</h2>
          </div>
          {phase !== 'running' && (
            <button onClick={onClose} className="p-1 rounded-lg hover:bg-gray-100 text-gray-400">
              <X className="h-4 w-4" />
            </button>
          )}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">

          {/* Loading */}
          {phase === 'loading' && (
            <div className="flex flex-col items-center justify-center py-16 gap-3 text-gray-400">
              <Loader2 className="h-8 w-8 animate-spin text-indigo-400" />
              <span className="text-sm">Analyse läuft…</span>
            </div>
          )}

          {/* Error */}
          {phase === 'error' && (
            <div className="flex items-start gap-3 p-4 bg-red-50 rounded-xl text-sm text-red-700">
              <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Running */}
          {phase === 'running' && (
            <div className="flex flex-col items-center justify-center py-12 gap-6">
              <Loader2 className="h-8 w-8 animate-spin text-indigo-500" />
              {progress ? (
                <div className="w-full max-w-sm space-y-2">
                  <div className="flex justify-between text-xs text-gray-600">
                    <span className="font-medium">{progress.label}</span>
                    <span className="tabular-nums">{progress.done ? '✓' : `${progress.percent}%`}</span>
                  </div>
                  <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
                    <div
                      className={clsx('h-full rounded-full transition-all duration-300',
                        progress.done ? 'bg-green-400' : 'bg-indigo-500')}
                      style={{ width: `${progress.done ? 100 : progress.percent}%` }}
                    />
                  </div>
                  <p className="text-[11px] text-gray-400 text-center">{progress.step}</p>
                </div>
              ) : (
                <p className="text-sm text-gray-400">Bereinigung läuft…</p>
              )}
            </div>
          )}

          {/* Preview */}
          {phase === 'preview' && preview && (
            <>
              {totalIssues === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 gap-3 text-gray-400">
                  <CheckCircle className="h-10 w-10 text-green-400" />
                  <p className="text-sm font-medium text-gray-600">Keine Duplikate gefunden</p>
                  <p className="text-xs">{scopeLabel ? `${scopeLabel} ist sauber.` : 'Bewerbungen, Kontakte, Firmen und Timeline sind sauber.'}</p>
                </div>
              ) : (
                <>
                  <SummaryChips
                    apps={preview.applications.length}
                    contacts={preview.contacts.length}
                    companies={preview.companies.length}
                    events={preview.events.length + preview.cross_app_events.length}
                    totalRemove={totalRemove}
                  />
                  {preview.applications.length > 0 && (
                    <Section title="Bewerbungen" count={preview.applications.length} color="blue">
                      {preview.applications.map((g, i) => <AppGroupRow key={i} group={g} />)}
                    </Section>
                  )}
                  {preview.contacts.length > 0 && (
                    <Section title="Kontakte" count={preview.contacts.length} color="purple">
                      {preview.contacts.map((g, i) => <ContactGroupRow key={i} group={g} />)}
                    </Section>
                  )}
                  {preview.companies.length > 0 && (
                    <Section title="Firmen" count={preview.companies.length} color="green">
                      {preview.companies.map((g, i) => <CompanyGroupRow key={i} group={g} onAssigned={loadPreview} />)}
                    </Section>
                  )}
                  {preview.events.length > 0 && (
                    <Section title="Timeline-Einträge" count={preview.events.length} color="amber">
                      {preview.events.map((g, i) => <EventGroupRow key={i} group={g} />)}
                    </Section>
                  )}
                  {preview.cross_app_events.length > 0 && (
                    <Section title="Bewerbungsübergreifende Einträge" count={preview.cross_app_events.length} color="amber">
                      {preview.cross_app_events.map((g, i) => <EventGroupRow key={i} group={g} />)}
                    </Section>
                  )}
                </>
              )}
            </>
          )}

          {/* Done */}
          {phase === 'done' && result && (
            <div className="space-y-4">
              <div className="flex items-center gap-2 text-green-700">
                <CheckCircle className="h-5 w-5" />
                <span className="font-semibold text-sm">Bereinigung abgeschlossen</span>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <ResultChip label="Bewerbungen zusammengeführt" value={result.deleted_applications} />
                <ResultChip label="Kontakte zur Prüfung vorgemerkt" value={result.queued_contacts} />
                <ResultChip label="Firmen zusammengeführt" value={result.deleted_companies} />
                <ResultChip label="Einträge gelöscht" value={result.deleted_events} />
              </div>
              {result.deleted_applications === 0 && result.queued_contacts === 0 && result.deleted_companies === 0 && result.deleted_events === 0 && result.queued_cross_app_events === 0 && (
                <p className="text-xs text-gray-400 text-center">Nichts zu bereinigen gewesen.</p>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 px-5 py-3 border-t border-gray-100 shrink-0">
          {phase === 'preview' && totalIssues === 0 && (
            <button onClick={onClose} className="text-xs font-medium px-4 py-2 rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50">
              Schließen
            </button>
          )}
          {phase === 'preview' && totalIssues > 0 && (
            <>
              <button onClick={onClose} className="text-xs font-medium px-4 py-2 rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50">
                Abbrechen
              </button>
              <button
                onClick={runCleanup}
                className="flex items-center gap-1.5 text-xs font-medium px-4 py-2 rounded-lg bg-red-500 text-white hover:bg-red-600"
              >
                <Trash2 className="h-3.5 w-3.5" />
                {totalRemove} Duplikat{totalRemove !== 1 ? 'e' : ''} löschen
              </button>
            </>
          )}
          {(phase === 'done' || phase === 'error') && (
            <button onClick={onClose} className="text-xs font-medium px-4 py-2 rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50">
              Schließen
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────────

function SummaryChips({ apps, contacts, companies, events, totalRemove }: {
  apps: number; contacts: number; companies: number; events: number; totalRemove: number
}) {
  return (
    <div className="flex flex-wrap gap-2 p-3 bg-gray-50 rounded-xl text-xs">
      <span className="text-gray-500">Gefunden:</span>
      {apps > 0 && <span className="px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 font-medium">{apps} Bewerbungsgruppe{apps !== 1 ? 'n' : ''}</span>}
      {contacts > 0 && <span className="px-2 py-0.5 rounded-full bg-purple-100 text-purple-700 font-medium">{contacts} Kontaktgruppe{contacts !== 1 ? 'n' : ''}</span>}
      {companies > 0 && <span className="px-2 py-0.5 rounded-full bg-green-100 text-green-700 font-medium">{companies} Firmengruppe{companies !== 1 ? 'n' : ''}</span>}
      {events > 0 && <span className="px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 font-medium">{events} Eintragsgruppe{events !== 1 ? 'n' : ''}</span>}
      <span className="ml-auto text-gray-400">{totalRemove} Zeilen werden gelöscht, Daten zusammengeführt</span>
    </div>
  )
}

function Section({ title, count, color, children }: {
  title: string; count: number; color: 'blue' | 'purple' | 'green' | 'amber'; children: React.ReactNode
}) {
  const [open, setOpen] = useState(true)
  const colors = {
    blue:   'text-blue-700 bg-blue-50',
    purple: 'text-purple-700 bg-purple-50',
    green:  'text-green-700 bg-green-50',
    amber:  'text-amber-700 bg-amber-50',
  }
  return (
    <div className="rounded-xl border border-gray-100 overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-2.5 bg-gray-50 hover:bg-gray-100 transition-colors"
      >
        <div className="flex items-center gap-2">
          {open ? <ChevronDown className="h-3.5 w-3.5 text-gray-400" /> : <ChevronRight className="h-3.5 w-3.5 text-gray-400" />}
          <span className="text-xs font-semibold text-gray-700">{title}</span>
          <span className={clsx('text-[10px] font-bold px-1.5 py-0.5 rounded-full', colors[color])}>{count}</span>
        </div>
      </button>
      {open && (
        <div className="divide-y divide-gray-50">{children}</div>
      )}
    </div>
  )
}

function AppGroupRow({ group }: { group: AppGroup }) {
  return (
    <div className="px-4 py-3 text-xs space-y-1.5">
      <div className="flex items-center gap-2">
        <span className="text-[10px] font-semibold text-green-600 uppercase tracking-wide">Behalten</span>
        <span className="font-medium text-gray-800">{group.keep.firma}</span>
        {group.keep.rolle && <span className="text-gray-500">· {group.keep.rolle}</span>}
        <span className="ml-auto text-gray-400">{group.keep.events} Events · {group.keep.contacts} Kontakte</span>
      </div>
      {group.remove.map(r => (
        <div key={r.id} className="flex items-center gap-2 text-gray-400 ml-4">
          <Trash2 className="h-3 w-3 text-red-400 shrink-0" />
          <span className={clsx(r.abgesagt && 'line-through')}>{r.firma}</span>
          {r.rolle && <span>· {r.rolle}</span>}
          <span className="ml-auto">{r.events_count} Events</span>
        </div>
      ))}
      {(group.events_merged > 0 || group.contacts_merged > 0) && (
        <p className="text-[10px] text-gray-400 ml-4">
          → {group.events_merged > 0 && `${group.events_merged} Events`}
          {group.events_merged > 0 && group.contacts_merged > 0 && ' + '}
          {group.contacts_merged > 0 && `${group.contacts_merged} Kontakte`} werden übertragen
        </p>
      )}
    </div>
  )
}

function ContactGroupRow({ group }: { group: ContactGroup }) {
  return (
    <div className="px-4 py-3 text-xs space-y-1.5">
      <div className="flex items-center gap-2">
        <span className="text-[10px] font-semibold text-green-600 uppercase tracking-wide">Behalten</span>
        <span className="font-medium text-gray-800">{group.keep.name}</span>
        {group.keep.email && <span className="text-gray-400">{group.keep.email}</span>}
        {group.keep.firma && <span className="text-gray-500">· {group.keep.firma}</span>}
        <span className="ml-auto text-gray-400">{group.keep.apps} Bewerbungen</span>
      </div>
      {group.remove.map(r => (
        <div key={r.id} className="flex items-center gap-2 text-gray-400 ml-4">
          <Trash2 className="h-3 w-3 text-red-400 shrink-0" />
          <span>{r.name}</span>
          {r.email && <span className="text-gray-300">{r.email}</span>}
          <span className="ml-auto">{r.apps_count} Verknüpfungen</span>
        </div>
      ))}
      {group.apps_merged > 0 && (
        <p className="text-[10px] text-gray-400 ml-4">→ {group.apps_merged} Bewerbungsverknüpfung{group.apps_merged !== 1 ? 'en' : ''} werden übertragen</p>
      )}
    </div>
  )
}

function CompanyGroupRow({ group, onAssigned }: { group: CompanyGroup; onAssigned: () => void }) {
  const [assigningId, setAssigningId] = useState<number | null>(null)
  const [assignedIds, setAssignedIds] = useState<Set<number>>(new Set())

  async function assignAsSubsidiary(childId: number) {
    setAssigningId(childId)
    try {
      await api.companies.update(childId, { parent_company_id: group.keep.id })
      setAssignedIds(prev => new Set(prev).add(childId))
      onAssigned()
    } finally {
      setAssigningId(null)
    }
  }

  return (
    <div className="px-4 py-3 text-xs space-y-1.5">
      <div className="flex items-center gap-2">
        <span className="text-[10px] font-semibold text-green-600 uppercase tracking-wide">Behalten</span>
        <span className="font-medium text-gray-800">{group.keep.name}</span>
        {group.keep.website && <span className="text-gray-400 truncate">{group.keep.website}</span>}
        <span className="ml-auto text-gray-400">{group.keep.apps} Bewerbungen · {group.keep.contacts} Kontakte</span>
      </div>
      {group.remove.map(r => {
        const isAssigned = assignedIds.has(r.id)
        return (
          <div key={r.id} className={clsx('flex items-center gap-2 ml-4', isAssigned ? 'text-emerald-500' : 'text-gray-400')}>
            {isAssigned ? <CheckCircle className="h-3 w-3 shrink-0" /> : <Trash2 className="h-3 w-3 text-red-400 shrink-0" />}
            <span>{r.name}</span>
            <span className="text-gray-300">{r.apps_count} Bewerbungen · {r.contacts_count} Kontakte</span>
            {isAssigned ? (
              <span className="ml-auto text-[10px]">Als Tochterfirma zugeordnet</span>
            ) : (
              <button
                type="button"
                disabled={assigningId === r.id}
                onClick={() => assignAsSubsidiary(r.id)}
                className="ml-auto text-[10px] font-medium text-indigo-600 hover:text-indigo-800 hover:underline disabled:opacity-50"
                title={`${r.name} als Tochterfirma von ${group.keep.name} eintragen, statt zusammenzuführen`}
              >
                {assigningId === r.id ? 'Ordne zu…' : 'Als Tochterfirma zuordnen'}
              </button>
            )}
          </div>
        )
      })}
      {(group.apps_merged > 0 || group.contacts_merged > 0) && (
        <p className="text-[10px] text-gray-400 ml-4">
          → {group.apps_merged > 0 && `${group.apps_merged} Bewerbungen`}
          {group.apps_merged > 0 && group.contacts_merged > 0 && ' + '}
          {group.contacts_merged > 0 && `${group.contacts_merged} Kontakte`} werden übertragen, falls stattdessen zusammengeführt
        </p>
      )}
    </div>
  )
}

function EventGroupRow({ group }: { group: EventGroup }) {
  return (
    <div className="px-4 py-3 text-xs space-y-1.5">
      <div className="flex items-center gap-2">
        <span className="text-[10px] font-semibold text-green-600 uppercase tracking-wide">Behalten</span>
        <span className="font-medium text-gray-800">{group.keep.titel || '(kein Titel)'}</span>
        {group.keep.typ && <span className="text-gray-400">· {group.keep.typ}</span>}
        {group.keep.datum && <span className="text-gray-400">{group.keep.datum}</span>}
        {group.keep.has_notiz && <span className="text-indigo-400 text-[10px]">Notiz</span>}
      </div>
      {group.remove.map(r => (
        <div key={r.id} className="flex items-center gap-2 text-gray-400 ml-4">
          <Trash2 className="h-3 w-3 text-red-400 shrink-0" />
          <span>{r.titel || '(kein Titel)'}</span>
          {r.datum && <span>{r.datum}</span>}
        </div>
      ))}
    </div>
  )
}

function ResultChip({ label, value }: { label: string; value: number }) {
  return (
    <div className={clsx(
      'flex flex-col items-center p-3 rounded-xl',
      value > 0 ? 'bg-red-50' : 'bg-gray-50'
    )}>
      <span className={clsx('text-2xl font-bold', value > 0 ? 'text-red-600' : 'text-gray-400')}>{value}</span>
      <span className="text-[10px] text-gray-500 text-center leading-tight mt-0.5">{label}</span>
    </div>
  )
}
