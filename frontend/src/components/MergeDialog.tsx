import { useState, useEffect } from 'react'
import { X, GitMerge } from 'lucide-react'
import { api } from '../api/client'
import type { Application, Contact } from '../types'
import { MAIN_STATUS_LABELS } from '../types'
import clsx from 'clsx'

// ── Field definitions ────────────────────────────────────────────────────────

interface FieldDef { key: string; label: string }

const APP_FIELDS: FieldDef[] = [
  { key: 'firma', label: 'Firma' },
  { key: 'rolle', label: 'Stelle' },
  { key: 'main_status', label: 'Status' },
  { key: 'sub_status', label: 'Unterstatus' },
  { key: 'is_headhunter', label: 'Headhunter' },
  { key: 'zielfirma_bei_hh', label: 'Zielfirma (HH)' },
  { key: 'quelle', label: 'Quelle' },
  { key: 'wurde_besetzt_von', label: 'Besetzt von' },
  { key: 'datum_bewerbung', label: 'Beworben am' },
  { key: 'letztes_update', label: 'Letztes Update' },
  { key: 'stellenanzeige_url', label: 'Stellenanzeige' },
  { key: 'kommentar', label: 'Kommentar' },
  { key: 'gespraech_1', label: 'Gespräch 1' },
  { key: 'gespraech_2', label: 'Gespräch 2' },
  { key: 'gespraech_3', label: 'Gespräch 3' },
  { key: 'gespraech_4', label: 'Gespräch 4' },
  { key: 'gespraech_5', label: 'Gespräch 5' },
]

const CONTACT_FIELDS: FieldDef[] = [
  { key: 'name', label: 'Name' },
  { key: 'email', label: 'E-Mail' },
  { key: 'telefon', label: 'Telefon' },
  { key: 'linkedin_url', label: 'LinkedIn' },
  { key: 'firma', label: 'Firma' },
  { key: 'rolle', label: 'Rolle' },
  { key: 'typ', label: 'Typ' },
  { key: 'notizen', label: 'Notizen' },
  { key: 'letzter_kontakt', label: 'Letzter Kontakt' },
]

function displayValue(obj: Record<string, unknown>, key: string): string {
  const val = obj[key]
  if (val === null || val === undefined || val === '') return ''
  if (typeof val === 'boolean') return val ? 'Ja' : 'Nein'
  if (key === 'main_status') return (MAIN_STATUS_LABELS as Record<string, string>)[val as string] ?? String(val)
  return String(val)
}

function entityLabel(obj: Record<string, unknown>): string {
  if ('firma' in obj && 'rolle' in obj) {
    return `${obj.firma || '?'} / ${obj.rolle || '?'}`
  }
  return String(obj['name'] || obj['id'] || '?')
}

// ── Application merge dialog ─────────────────────────────────────────────────

interface AppMergeProps {
  appIds: number[]
  onMerged: (winnerId: number) => void
  onClose: () => void
}

export function AppMergeDialog({ appIds, onMerged, onClose }: AppMergeProps) {
  const [apps, setApps] = useState<Application[]>([])
  const [loading, setLoading] = useState(true)
  const [winnerId, setWinnerId] = useState(appIds[0])
  const [fieldSources, setFieldSources] = useState<Record<string, number>>({})
  const [merging, setMerging] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    ;(async () => {
      setLoading(true)
      try {
        const loaded = await Promise.all(appIds.map(id => api.applications.get(id)))
        setApps(loaded)
        const init: Record<string, number> = {}
        for (const f of APP_FIELDS) init[f.key] = appIds[0]
        setFieldSources(init)
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  function changeWinner(id: number) {
    setWinnerId(id)
    const reset: Record<string, number> = {}
    for (const f of APP_FIELDS) reset[f.key] = id
    setFieldSources(reset)
  }

  async function handleMerge() {
    setMerging(true)
    setError(null)
    try {
      const res = await api.merge.applications({
        winner_id: winnerId,
        loser_ids: appIds.filter(id => id !== winnerId),
        field_overrides: fieldSources,
      })
      onMerged(res.winner_id)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Unbekannter Fehler')
    } finally {
      setMerging(false)
    }
  }

  const records = apps as unknown as Record<string, unknown>[]
  const visibleFields = APP_FIELDS.filter(f =>
    records.some(r => {
      const v = displayValue(r, f.key)
      return v !== '' && v !== 'Nein'
    })
  )

  return (
    <MergeShell
      title={`${apps.length} Bewerbungen zusammenführen`}
      loading={loading}
      merging={merging}
      error={error}
      onClose={onClose}
      onMerge={handleMerge}
    >
      <WinnerPicker entities={records} winnerId={winnerId} onChange={changeWinner} />
      <FieldTable
        fields={visibleFields}
        entities={records}
        fieldSources={fieldSources}
        onSelect={(key, id) => setFieldSources(p => ({ ...p, [key]: id }))}
      />
      <p className="text-xs text-gray-500">
        Ereignisse und Kontakte aller Einträge werden zusammengeführt. Nicht-Basis-Einträge werden danach gelöscht.
        Zukünftige Syncs erkennen die alten Bezeichnungen und legen keine Duplikate mehr an.
      </p>
    </MergeShell>
  )
}

// ── Contact merge dialog ─────────────────────────────────────────────────────

interface ContactMergeProps {
  contactIds: number[]
  contacts: Contact[]
  onMerged: (winnerId: number) => void
  onClose: () => void
}

export function ContactMergeDialog({ contactIds, contacts, onMerged, onClose }: ContactMergeProps) {
  const [winnerId, setWinnerId] = useState(contactIds[0])
  const [fieldSources, setFieldSources] = useState<Record<string, number>>(() => {
    const init: Record<string, number> = {}
    for (const f of CONTACT_FIELDS) init[f.key] = contactIds[0]
    return init
  })
  const [merging, setMerging] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function changeWinner(id: number) {
    setWinnerId(id)
    const reset: Record<string, number> = {}
    for (const f of CONTACT_FIELDS) reset[f.key] = id
    setFieldSources(reset)
  }

  async function handleMerge() {
    setMerging(true)
    setError(null)
    try {
      const res = await api.merge.contacts({
        winner_id: winnerId,
        loser_ids: contactIds.filter(id => id !== winnerId),
        field_overrides: fieldSources,
      })
      onMerged(res.winner_id)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Unbekannter Fehler')
    } finally {
      setMerging(false)
    }
  }

  const records = contacts as unknown as Record<string, unknown>[]
  const visibleFields = CONTACT_FIELDS.filter(f =>
    records.some(r => displayValue(r, f.key) !== '')
  )

  return (
    <MergeShell
      title={`${contacts.length} Kontakte zusammenführen`}
      loading={false}
      merging={merging}
      error={error}
      onClose={onClose}
      onMerge={handleMerge}
    >
      <WinnerPicker entities={records} winnerId={winnerId} onChange={changeWinner} />
      <FieldTable
        fields={visibleFields}
        entities={records}
        fieldSources={fieldSources}
        onSelect={(key, id) => setFieldSources(p => ({ ...p, [key]: id }))}
      />
      <p className="text-xs text-gray-500">
        Verknüpfte Bewerbungen werden auf den Basis-Kontakt übertragen. Nicht-Basis-Einträge werden danach gelöscht.
      </p>
    </MergeShell>
  )
}

// ── Shared sub-components ────────────────────────────────────────────────────

function MergeShell({
  title, loading, merging, error, onClose, onMerge, children,
}: {
  title: string
  loading: boolean
  merging: boolean
  error: string | null
  onClose: () => void
  onMerge: () => void
  children: React.ReactNode
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-3xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b shrink-0">
          <div className="flex items-center gap-2">
            <GitMerge className="h-4 w-4 text-indigo-600" />
            <h2 className="text-base font-semibold text-gray-900">{title}</h2>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body */}
        <div className="overflow-y-auto flex-1 p-6 space-y-5">
          {loading ? (
            <p className="text-sm text-gray-500">Lade Daten…</p>
          ) : (
            children
          )}
          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t bg-gray-50 shrink-0">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 transition-colors"
          >
            Abbrechen
          </button>
          <button
            onClick={onMerge}
            disabled={merging || loading}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            <GitMerge className="h-3.5 w-3.5" />
            {merging ? 'Zusammenführen…' : 'Zusammenführen'}
          </button>
        </div>
      </div>
    </div>
  )
}

function WinnerPicker({
  entities, winnerId, onChange,
}: {
  entities: Record<string, unknown>[]
  winnerId: number
  onChange: (id: number) => void
}) {
  return (
    <div>
      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
        Basis-Eintrag (ID und Ereignisse bleiben erhalten)
      </p>
      <div className="flex gap-2 flex-wrap">
        {entities.map(e => {
          const id = e['id'] as number
          return (
            <label
              key={id}
              className={clsx(
                'flex items-center gap-2 px-3 py-2 rounded-lg border cursor-pointer transition-colors text-sm',
                winnerId === id
                  ? 'border-indigo-500 bg-indigo-50 text-indigo-800'
                  : 'border-gray-200 hover:bg-gray-50 text-gray-700'
              )}
            >
              <input
                type="radio"
                checked={winnerId === id}
                onChange={() => onChange(id)}
                className="text-indigo-600 shrink-0"
              />
              <span className="font-medium">{entityLabel(e)}</span>
              <span className="text-xs text-gray-400">#{id}</span>
            </label>
          )
        })}
      </div>
    </div>
  )
}

function FieldTable({
  fields, entities, fieldSources, onSelect,
}: {
  fields: FieldDef[]
  entities: Record<string, unknown>[]
  fieldSources: Record<string, number>
  onSelect: (key: string, id: number) => void
}) {
  return (
    <div className="rounded-lg border border-gray-200 overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-gray-50 border-b">
            <th className="text-left px-4 py-2.5 text-xs font-medium text-gray-400 uppercase w-28 shrink-0">Feld</th>
            {entities.map(e => (
              <th key={e['id'] as number} className="text-left px-4 py-2.5 text-xs font-medium text-gray-600">
                {entityLabel(e)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {fields.map(field => {
            const values = entities.map(e => displayValue(e, field.key))
            const allSame = values.every(v => v === values[0])
            const currentSource = fieldSources[field.key]
            return (
              <tr key={field.key} className="even:bg-gray-50/40">
                <td className="px-4 py-2 text-xs text-gray-400 font-medium align-middle">{field.label}</td>
                {allSame ? (
                  <td colSpan={entities.length} className="px-4 py-2 text-xs text-gray-400 italic">
                    Identisch: {values[0] || '(leer)'}
                  </td>
                ) : (
                  entities.map((e, idx) => {
                    const id = e['id'] as number
                    const val = values[idx]
                    const selected = currentSource === id
                    return (
                      <td key={id} className="px-4 py-2">
                        <label
                          className={clsx(
                            'flex items-start gap-2 cursor-pointer rounded px-2 py-1 -mx-2 transition-colors',
                            selected ? 'bg-indigo-100' : 'hover:bg-gray-100'
                          )}
                        >
                          <input
                            type="radio"
                            name={`field-${field.key}`}
                            checked={selected}
                            onChange={() => onSelect(field.key, id)}
                            className="mt-0.5 text-indigo-600 shrink-0"
                          />
                          <span className={clsx('text-xs break-words max-w-[200px]', val ? 'text-gray-800' : 'text-gray-300 italic')}>
                            {val || '(leer)'}
                          </span>
                        </label>
                      </td>
                    )
                  })
                )}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
