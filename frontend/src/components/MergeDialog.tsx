import { useState, useEffect, useMemo } from 'react'
import { X, GitMerge } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { Application, Contact, CompanyProfile } from '../types'
import { mainStatusLabel } from '../i18n/statusLabels'
import { errorMessage } from '../i18n/errorMessage'
import i18n from '../i18n'
import clsx from 'clsx'

// ── Field definitions ────────────────────────────────────────────────────────

interface FieldDef { key: string; label: string }

const APP_FIELD_KEYS = [
  'firma', 'rolle', 'main_status', 'sub_status', 'is_headhunter', 'zielfirma_bei_hh',
  'quelle', 'wurde_besetzt_von', 'datum_bewerbung', 'letztes_update', 'stellenanzeige_url',
  'kommentar', 'gespraech_1', 'gespraech_2', 'gespraech_3', 'gespraech_4', 'gespraech_5',
] as const

const CONTACT_FIELD_KEYS = [
  'name', 'email', 'linkedin_url', 'firma', 'rolle', 'typ', 'notizen', 'letzter_kontakt',
] as const

const COMPANY_FIELD_KEYS = [
  'name_display', 'industry', 'company_type', 'employee_range', 'employee_count',
  'founded_year', 'hq_city', 'hq_country', 'website', 'linkedin_company_url', 'description',
] as const

function useAppFields(): FieldDef[] {
  const { t } = useTranslation('merge')
  return useMemo(() => APP_FIELD_KEYS.map(key => ({ key, label: t(`appFields.${key}`) })), [t])
}

function useContactFields(): FieldDef[] {
  const { t } = useTranslation('merge')
  return useMemo(() => CONTACT_FIELD_KEYS.map(key => ({ key, label: t(`contactFields.${key}`) })), [t])
}

function useCompanyFields(): FieldDef[] {
  const { t } = useTranslation('merge')
  return useMemo(() => COMPANY_FIELD_KEYS.map(key => ({ key, label: t(`companyFields.${key}`) })), [t])
}

/** Non-hook variant — displayValue is called from plain filter/map callbacks,
 * not component bodies, so it reads the current language via the i18n
 * singleton directly (same pattern as i18n/statusLabels.ts). */
function displayValue(obj: Record<string, unknown>, key: string): string {
  const val = obj[key]
  if (val === null || val === undefined || val === '') return ''
  if (typeof val === 'boolean') return val ? i18n.t('yes', { ns: 'merge' }) : i18n.t('no', { ns: 'merge' })
  if (key === 'main_status') return mainStatusLabel(String(val))
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
  const { t } = useTranslation('merge')
  const APP_FIELDS = useAppFields()
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
      setError(e instanceof Error ? errorMessage(e, t) : t('unknownError'))
    } finally {
      setMerging(false)
    }
  }

  const records = apps as unknown as Record<string, unknown>[]
  const visibleFields = APP_FIELDS.filter(f =>
    records.some(r => {
      const v = displayValue(r, f.key)
      return v !== '' && v !== t('no')
    })
  )

  return (
    <MergeShell
      title={t('mergeAppsTitle', { count: apps.length })}
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
        {t('mergeAppsFooter')}
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
  const { t } = useTranslation('merge')
  const CONTACT_FIELDS = useContactFields()
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
      setError(e instanceof Error ? errorMessage(e, t) : t('unknownError'))
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
      title={t('mergeContactsTitle', { count: contacts.length })}
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
        {t('mergeContactsFooter')}
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
  const { t } = useTranslation('merge')
  const { t: tCommon } = useTranslation('common')
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-3xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b shrink-0">
          <div className="flex items-center gap-2">
            <GitMerge className="h-4 w-4 text-indigo-600" />
            <h2 className="text-base font-semibold text-gray-900" data-testid="merge-dialog-title">{title}</h2>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body */}
        <div className="overflow-y-auto flex-1 p-6 space-y-5">
          {loading ? (
            <p className="text-sm text-gray-500">{t('loading')}</p>
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
            {tCommon('cancel')}
          </button>
          <button
            onClick={onMerge}
            disabled={merging || loading}
            data-testid="merge-confirm-button"
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            <GitMerge className="h-3.5 w-3.5" />
            {merging ? t('merging') : t('merge')}
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
  const { t } = useTranslation('merge')
  return (
    <div>
      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
        {t('winnerPickerLabel')}
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
  const { t } = useTranslation('merge')
  return (
    <div className="rounded-lg border border-gray-200 overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-gray-50 border-b">
            <th className="text-left px-4 py-2.5 text-xs font-medium text-gray-400 uppercase w-28 shrink-0">{t('fieldColumn')}</th>
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
                    {t('identical', { value: values[0] || t('empty') })}
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
                            {val || t('empty')}
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

// ── Company merge dialog ──────────────────────────────────────────────────────

interface CompanyMergeProps {
  companyIds: number[]
  onMerged: (winnerId: number) => void
  onClose: () => void
}

export function CompanyMergeDialog({ companyIds, onMerged, onClose }: CompanyMergeProps) {
  const { t } = useTranslation('merge')
  const COMPANY_FIELDS = useCompanyFields()
  const [allCompanyIds, setAllCompanyIds] = useState(companyIds)
  const [companies, setCompanies] = useState<CompanyProfile[]>([])
  const [loading, setLoading] = useState(true)
  const [winnerId, setWinnerId] = useState(companyIds[0])
  const [fieldSources, setFieldSources] = useState<Record<string, number>>({})
  const [merging, setMerging] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Search for second company (single-ID mode)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<CompanyProfile[]>([])
  const [searching, setSearching] = useState(false)
  const needsPick = allCompanyIds.length < 2

  useEffect(() => {
    if (needsPick) return
    ;(async () => {
      setLoading(true)
      try {
        const loaded = await Promise.all(allCompanyIds.map(id => api.companies.get(id)))
        setCompanies(loaded)
        const init: Record<string, number> = {}
        for (const f of COMPANY_FIELDS) init[f.key] = allCompanyIds[0]
        setFieldSources(init)
      } finally {
        setLoading(false)
      }
    })()
  }, [allCompanyIds])

  useEffect(() => {
    if (!searchQuery.trim() || !needsPick) { setSearchResults([]); return }
    const t = setTimeout(async () => {
      setSearching(true)
      try {
        const results = await api.companies.list({ search: searchQuery })
        setSearchResults(results.filter(c => !allCompanyIds.includes(c.id)).slice(0, 8))
      } finally {
        setSearching(false)
      }
    }, 250)
    return () => clearTimeout(t)
  }, [searchQuery])

  if (needsPick) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
        <div className="bg-white rounded-xl shadow-xl w-full max-w-md flex flex-col">
          <div className="flex items-center justify-between px-5 py-4 border-b">
            <div className="flex items-center gap-2">
              <GitMerge className="h-4 w-4 text-indigo-600" />
              <h2 className="text-base font-semibold text-gray-900">{t('pickCompanyTitle')}</h2>
            </div>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X className="h-5 w-5" /></button>
          </div>
          <div className="p-5 space-y-3">
            <p className="text-xs text-gray-500">{t('pickCompanyPrompt')}</p>
            <input
              autoFocus
              type="text"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder={t('searchCompanyPlaceholder')}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            {searching && <p className="text-xs text-gray-400">{t('searching')}</p>}
            <div className="space-y-1 max-h-64 overflow-y-auto">
              {searchResults.map(c => (
                <button
                  key={c.id}
                  onClick={() => setAllCompanyIds([...allCompanyIds, c.id])}
                  className="w-full text-left rounded-lg border border-gray-100 px-3 py-2 text-sm hover:bg-indigo-50 hover:border-indigo-200 transition-colors"
                >
                  <span className="font-medium text-gray-900">{c.name_display || c.name_norm}</span>
                  {c.industry && <span className="text-gray-400 text-xs ml-2">{c.industry}</span>}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    )
  }

  function changeWinner(id: number) {
    setWinnerId(id)
    const reset: Record<string, number> = {}
    for (const f of COMPANY_FIELDS) reset[f.key] = id
    setFieldSources(reset)
  }

  async function handleMerge() {
    setMerging(true)
    setError(null)
    try {
      const res = await api.merge.companies({
        winner_id: winnerId,
        loser_ids: allCompanyIds.filter(id => id !== winnerId),
        field_overrides: fieldSources,
      })
      onMerged(res.winner_id)
    } catch (e: unknown) {
      setError(e instanceof Error ? errorMessage(e, t) : t('unknownError'))
    } finally {
      setMerging(false)
    }
  }

  function companyLabel(c: Record<string, unknown>): string {
    return String(c['name_display'] || c['name_norm'] || c['id'] || '?')
  }

  const records = companies as unknown as Record<string, unknown>[]
  const visibleFields = COMPANY_FIELDS.filter(f =>
    records.some(r => {
      const v = r[f.key]
      return v !== null && v !== undefined && v !== ''
    })
  )

  return (
    <MergeShell
      title={t('mergeCompaniesTitle', { count: companies.length })}
      loading={loading}
      merging={merging}
      error={error}
      onClose={onClose}
      onMerge={handleMerge}
    >
      <div>
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
          {t('mergeCompaniesWinnerLabel')}
        </p>
        <div className="flex gap-2 flex-wrap">
          {records.map(e => {
            const eid = e['id'] as number
            return (
              <label
                key={eid}
                className={clsx(
                  'flex items-center gap-2 px-3 py-2 rounded-lg border cursor-pointer transition-colors text-sm',
                  winnerId === eid ? 'border-indigo-500 bg-indigo-50 text-indigo-800' : 'border-gray-200 hover:bg-gray-50 text-gray-700'
                )}
              >
                <input type="radio" checked={winnerId === eid} onChange={() => changeWinner(eid)} className="text-indigo-600 shrink-0" />
                <span className="font-medium">{companyLabel(e)}</span>
                <span className="text-xs text-gray-400">#{eid}</span>
              </label>
            )
          })}
        </div>
      </div>
      <FieldTable
        fields={visibleFields}
        entities={records}
        fieldSources={fieldSources}
        onSelect={(key, id) => setFieldSources(p => ({ ...p, [key]: id }))}
      />
      <p className="text-xs text-gray-500">
        {t('mergeCompaniesFooter')}
      </p>
    </MergeShell>
  )
}
