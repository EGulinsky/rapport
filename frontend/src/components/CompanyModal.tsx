import { useState, useEffect, useCallback, useRef } from 'react'
import { X, ExternalLink, Clock, CheckCircle, XCircle, Pencil, GitMerge, Save, RotateCcw, Linkedin, Mail, Phone, Upload, Trash2, UserPlus, UserMinus, ChevronsUp, ChevronsDown, Check } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { CompanyProfile, MainStatus, ContactWithApp } from '../types'
import { StatusBadge } from './StatusBadge'
import { displayName } from './ContactModal'
import { CompanyLogo } from './CompanyLogo'
import { CompanyFilterPicker, type CompanyFilter } from './CompanyFilterPicker'
import { useLocale } from '../i18n/useLocale'
import { formatDate as formatDateI18n } from '../i18n/formatDate'
import { errorMessage } from '../i18n/errorMessage'
import clsx from 'clsx'

interface Props {
  id: number
  onClose: () => void
  onOpenApplication?: (id: number) => void
  onOpenContact?: (id: number) => void
  onOpenCompany?: (id: number) => void
  onMergeRequest?: (ids: number[]) => void
  onSaved?: () => void
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

const COMPANY_TYPES = ['startup', 'konzern', 'kmu', 'beratung', 'headhunter', 'nonprofit', 'public', 'other']
const CONTACT_TYPES = ['HR', 'Headhunter', 'FB', 'CEO', 'Netzwerk']

type Tab = 'info' | 'apps' | 'contacts'

interface EditState {
  name_display: string
  industry: string
  company_type: string
  employee_range: string
  employee_count: string
  founded_year: string
  hq_city: string
  hq_country: string
  website: string
  linkedin_company_url: string
  description: string
  parent_company_id: number | null
  parent_name: string
}

function toEditState(c: CompanyProfile): EditState {
  return {
    name_display: c.name_display ?? '',
    industry: c.industry ?? '',
    company_type: c.company_type ?? '',
    employee_range: c.employee_range ?? '',
    employee_count: c.employee_count != null ? String(c.employee_count) : '',
    founded_year: c.founded_year != null ? String(c.founded_year) : '',
    hq_city: c.hq_city ?? '',
    hq_country: c.hq_country ?? '',
    website: c.website ?? '',
    linkedin_company_url: c.linkedin_company_url ?? '',
    description: c.description ?? '',
    parent_company_id: c.parent_company_id ?? null,
    parent_name: c.parent_name ?? '',
  }
}

export function CompanyModal({ id, onClose, onOpenApplication, onOpenContact, onOpenCompany, onMergeRequest, onSaved }: Props) {
  const { t } = useTranslation('companies')
  const { t: tContacts } = useTranslation('contacts')
  const { t: tCommon } = useTranslation('common')
  const locale = useLocale()
  const [company, setCompany] = useState<CompanyProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('info')
  const [editing, setEditing] = useState(false)
  const [editState, setEditState] = useState<EditState | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [logoPreview, setLogoPreview] = useState<string | null>(null)
  const [logoUploading, setLogoUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [addingContact, setAddingContact] = useState(false)
  const [addContactMode, setAddContactMode] = useState<'new' | 'link'>('new')
  const [contactQuery, setContactQuery] = useState('')
  const [contactResults, setContactResults] = useState<ContactWithApp[]>([])
  const [contactSearching, setContactSearching] = useState(false)
  const [newContactDraft, setNewContactDraft] = useState<{ vorname: string; name: string; email: string; telefon: string; rolle: string; typ: string; linkedin_url: string }>({ vorname: '', name: '', email: '', telefon: '', rolle: '', typ: '', linkedin_url: '' })
  const [savingNewContact, setSavingNewContact] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.companies.get(id)
      setCompany(data)
    } catch (e) {
      setError(errorMessage(e, t))
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (!addingContact || addContactMode !== 'link') { setContactQuery(''); setContactResults([]); return }
    const t = setTimeout(async () => {
      setContactSearching(true)
      try { setContactResults(await api.contacts.listAll({ search: contactQuery || undefined })) }
      finally { setContactSearching(false) }
    }, 200)
    return () => clearTimeout(t)
  }, [contactQuery, addingContact, addContactMode])

  function closeAddContact() {
    setAddingContact(false)
    setNewContactDraft({ vorname: '', name: '', email: '', telefon: '', rolle: '', typ: '', linkedin_url: '' })
    setContactQuery('')
    setContactResults([])
  }

  async function assignContact(contactId: number) {
    await api.companies.assignContact(id, contactId)
    closeAddContact()
    load()
    onSaved?.()
  }

  async function createContact() {
    if (!newContactDraft.name) return
    setSavingNewContact(true)
    try {
      const { telefon, ...rest } = newContactDraft
      const contact = await api.contacts.create({
        ...rest,
        phones: telefon.trim() ? [{ number: telefon.trim(), type: 'other' }] : [],
        firma: company?.name_display ?? company?.name_norm,
        company_profile_id: id,
      })
      await api.companies.assignContact(id, contact.id)
      closeAddContact()
      load()
      onSaved?.()
    } finally {
      setSavingNewContact(false)
    }
  }

  async function unassignContact(contactId: number) {
    await api.companies.unassignContact(id, contactId)
    load()
    onSaved?.()
  }

  function startEdit() {
    if (!company) return
    setEditState(toEditState(company))
    setEditing(true)
    setSaveError(null)
  }

  function cancelEdit() {
    setEditing(false)
    setEditState(null)
    setSaveError(null)
  }

  async function saveEdit() {
    if (!editState || !company) return
    setSaving(true)
    setSaveError(null)
    try {
      const updated = await api.companies.update(id, {
        name_display: editState.name_display || null,
        industry: editState.industry || null,
        company_type: editState.company_type || null,
        employee_range: editState.employee_range || null,
        employee_count: editState.employee_count ? parseInt(editState.employee_count) : null,
        founded_year: editState.founded_year ? parseInt(editState.founded_year) : null,
        hq_city: editState.hq_city || null,
        hq_country: editState.hq_country || null,
        website: editState.website || null,
        linkedin_company_url: editState.linkedin_company_url || null,
        description: editState.description || null,
        parent_company_id: editState.parent_company_id,
      })
      setCompany(updated)
      setEditing(false)
      setEditState(null)
      onSaved?.()
    } catch (e) {
      setSaveError(errorMessage(e, t))
    } finally {
      setSaving(false)
    }
  }

  async function uploadLogo(file: File) {
    if (!company) return
    setLogoUploading(true)
    try {
      // Show preview immediately
      const reader = new FileReader()
      reader.onload = e => setLogoPreview(e.target?.result as string)
      reader.readAsDataURL(file)
      await api.companies.uploadLogo(company.id, file)
      await load()
      onSaved?.()
    } catch (e) {
      setSaveError(errorMessage(e, t))
    } finally {
      setLogoUploading(false)
    }
  }

  async function deleteLogo() {
    if (!company) return
    setLogoUploading(true)
    try {
      await api.companies.deleteLogo(company.id)
      setLogoPreview(null)
      await load()
      onSaved?.()
    } catch (e) {
      setSaveError(errorMessage(e, t))
    } finally {
      setLogoUploading(false)
    }
  }

  function handlePaste(e: React.ClipboardEvent) {
    if (!editing) return
    const file = e.clipboardData.files[0]
    if (file && file.type.startsWith('image/')) {
      uploadLogo(file)
    }
  }

  function ef(field: keyof EditState) {
    return (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
      setEditState(s => s ? { ...s, [field]: e.target.value } : s)
  }

  function formatDate(s: string | null | undefined): string {
    if (!s) return '—'
    return formatDateI18n(s, locale)
  }

  const location = [company?.hq_city, company?.hq_country].filter(Boolean).join(', ')

  const tabs: [Tab, string, number | undefined][] = [
    ['info', t('modal.tabProfile'), undefined],
    ['apps', t('modal.tabApplications'), company?.app_count],
    ['contacts', t('modal.tabContacts'), company?.contact_count],
  ]

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
      onPaste={handlePaste}
    >
      <div className="w-full max-w-2xl rounded-2xl bg-white shadow-2xl flex flex-col max-h-[90vh]">

        {/* Header */}
        <div className="flex items-start justify-between gap-3 p-5 border-b border-gray-100">
          <div className="flex-1 min-w-0">
            {loading ? (
              <div className="h-6 w-48 bg-gray-100 rounded animate-pulse" />
            ) : (
              <>
                <div className="flex items-center gap-2.5 mb-0.5">
                  <CompanyLogo name={company?.name_display || company?.name_norm || ''} website={company?.website} logoData={logoPreview ?? company?.logo_data} />
                  <h2 className="text-lg font-semibold text-gray-900 truncate">
                    {company?.name_display || company?.name_norm}
                  </h2>
                </div>
                <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                  {company?.sync_source && (
                    <span className="text-xs text-gray-400 bg-gray-50 border border-gray-100 rounded px-1.5 py-0.5">
                      {t(`syncSource.${company.sync_source}`, { defaultValue: company.sync_source })}
                    </span>
                  )}
                  {company?.last_synced_at && (
                    <span className="text-xs text-gray-400">
                      Sync: {formatDate(company.last_synced_at)}
                    </span>
                  )}
                </div>
              </>
            )}
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            {!loading && company && !editing && (
              <>
                {onMergeRequest && (
                  <button
                    onClick={() => onMergeRequest([id])}
                    title={t('modal.mergeTitle')}
                    className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 transition-colors"
                  >
                    <GitMerge className="h-4 w-4" />
                  </button>
                )}
                <button
                  onClick={startEdit}
                  title={tContacts('contactModal.edit')}
                  className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 transition-colors"
                >
                  <Pencil className="h-4 w-4" />
                </button>
              </>
            )}
            {editing && (
              <>
                <button onClick={cancelEdit} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 transition-colors" title={tCommon('cancel')}>
                  <RotateCcw className="h-4 w-4" />
                </button>
                <button
                  onClick={saveEdit}
                  disabled={saving}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-xs font-medium hover:bg-indigo-700 disabled:opacity-50"
                >
                  <Save className="h-3.5 w-3.5" />
                  {saving ? tCommon('saving') : tCommon('save')}
                </button>
              </>
            )}
            <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 transition-colors">
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-100 px-5 gap-1">
          {tabs.map(([t, label, count]) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={clsx(
                'flex items-center gap-1.5 px-3 py-2.5 text-xs font-medium border-b-2 -mb-px transition-colors',
                tab === t
                  ? 'border-indigo-500 text-indigo-700'
                  : 'border-transparent text-gray-500 hover:text-gray-800'
              )}
            >
              {label}
              {count != null && (
                <span className={clsx(
                  'rounded-full px-1.5 py-0.5 text-[10px] font-semibold',
                  tab === t ? 'bg-indigo-100 text-indigo-700' : 'bg-gray-100 text-gray-500'
                )}>
                  {count}
                </span>
              )}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {error && (
            <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">{error}</div>
          )}
          {saveError && (
            <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">{saveError}</div>
          )}

          {/* ── Profil Tab ── */}
          {tab === 'info' && !loading && company && (
            <>
              {/* Sync status */}
              <div className="flex items-center gap-2">
                {company.sync_status === 'pending' && (
                  <span className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium bg-yellow-100 text-yellow-700">
                    <Clock className="h-3 w-3" /> {t('modal.syncPending')}
                  </span>
                )}
                {company.sync_status === 'done' && (
                  <span className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium bg-green-100 text-green-700">
                    <CheckCircle className="h-3 w-3" /> {t('modal.syncDone')}
                  </span>
                )}
                {company.sync_status === 'failed' && (
                  <span className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium bg-red-100 text-red-700" title={company.sync_error ?? undefined}>
                    <XCircle className="h-3 w-3" /> {t('modal.syncError')}
                  </span>
                )}
              </div>

              {company.sync_status === 'failed' && company.sync_error && (
                <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-xs text-red-700">
                  {company.sync_error}
                </div>
              )}

              {/* Fields — view or edit */}
              {!editing ? (
                <div className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
                  <Field label={t('modal.fieldDisplayName')}>{company.name_display || <Dash />}</Field>
                  <Field label={t('modal.fieldIndustry')}>{company.industry || <Dash />}</Field>
                  <Field label={t('modal.fieldType')}>
                    {company.company_type ? (
                      <span className={clsx('inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium', COMPANY_TYPE_COLORS[company.company_type] ?? 'bg-gray-100 text-gray-600')}>
                        {t(`companyType.${company.company_type}`, { defaultValue: company.company_type })}
                      </span>
                    ) : <Dash />}
                  </Field>
                  <Field label={t('modal.fieldEmployees')}>{company.employee_range || (company.employee_count != null ? String(company.employee_count) : <Dash />)}</Field>
                  <Field label={t('modal.fieldFounded')}>{company.founded_year ?? <Dash />}</Field>
                  <Field label={t('modal.fieldLocation')}>{location || <Dash />}</Field>
                  {company.website && (
                    <Field label={t('modal.fieldWebsite')}>
                      <a href={company.website} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-indigo-600 hover:text-indigo-800 text-xs">
                        <ExternalLink className="h-3 w-3" />
                        {company.website.replace(/^https?:\/\//, '').replace(/\/$/, '')}
                      </a>
                    </Field>
                  )}
                  {company.linkedin_company_url && (
                    <Field label={t('modal.fieldLinkedin')}>
                      <a href={company.linkedin_company_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-indigo-600 hover:text-indigo-800 text-xs">
                        <ExternalLink className="h-3 w-3" /> LinkedIn
                      </a>
                    </Field>
                  )}
                  {company.parent_company_id && (
                    <Field label={t('modal.fieldParentCompany')}>
                      <button
                        onClick={() => onOpenCompany?.(company.parent_company_id!)}
                        className="inline-flex items-center gap-1 text-indigo-600 hover:text-indigo-800 text-xs font-medium hover:underline"
                      >
                        <ChevronsUp className="h-3 w-3" />
                        {company.parent_name}
                      </button>
                    </Field>
                  )}
                  {company.subsidiaries && company.subsidiaries.length > 0 && (
                    <Field label={t('modal.fieldSubsidiaries')}>
                      <div className="flex flex-wrap gap-1">
                        {company.subsidiaries.map(s => (
                          <button
                            key={s.id}
                            onClick={() => onOpenCompany?.(s.id)}
                            className="inline-flex items-center gap-1 rounded-full bg-gray-100 hover:bg-indigo-100 text-gray-700 hover:text-indigo-700 px-2 py-0.5 text-xs font-medium transition-colors"
                          >
                            <ChevronsDown className="h-3 w-3" />
                            {s.name_display ?? s.name_norm}
                          </button>
                        ))}
                      </div>
                    </Field>
                  )}
                </div>
              ) : editState && (
                <>
                {/* Logo section */}
                <div className="flex items-center gap-4 mb-2">
                  <CompanyLogo
                    name={company.name_display || company.name_norm || ''}
                    website={company.website}
                    logoData={logoPreview ?? company.logo_data}
                    size="md"
                  />
                  <div className="flex items-center gap-2 flex-wrap">
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept="image/*"
                      className="hidden"
                      onChange={e => { const f = e.target.files?.[0]; if (f) uploadLogo(f) }}
                    />
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      disabled={logoUploading}
                      className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 transition-colors"
                    >
                      <Upload className="h-3.5 w-3.5" />
                      {t('modal.uploadLogo')}
                    </button>
                    {(logoPreview ?? company.logo_data) && (
                      <button
                        type="button"
                        onClick={deleteLogo}
                        disabled={logoUploading}
                        className="flex items-center gap-1.5 rounded-lg border border-red-200 px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-50 transition-colors"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                        {t('modal.removeLogo')}
                      </button>
                    )}
                    {logoUploading && <span className="text-xs text-gray-400">{t('modal.uploading')}</span>}
                    <span className="text-xs text-gray-400">{t('modal.orPasteImage')}</span>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-x-4 gap-y-3">
                  <EditField label={t('modal.fieldDisplayName')} value={editState.name_display} onChange={ef('name_display')} />
                  <EditField label={t('modal.fieldIndustry')} value={editState.industry} onChange={ef('industry')} />
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">{t('modal.fieldType')}</label>
                    <select value={editState.company_type} onChange={ef('company_type')}
                      className="w-full rounded-lg border border-gray-200 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
                      <option value="">—</option>
                      {COMPANY_TYPES.map(ct => <option key={ct} value={ct}>{t(`companyType.${ct}`)}</option>)}
                    </select>
                  </div>
                  <EditField label={t('modal.employeeRangeLabel')} value={editState.employee_range} onChange={ef('employee_range')} placeholder={t('modal.employeeRangePlaceholder')} />
                  <EditField label={t('modal.employeeCountLabel')} value={editState.employee_count} onChange={ef('employee_count')} type="number" />
                  <EditField label={t('modal.fieldFounded')} value={editState.founded_year} onChange={ef('founded_year')} type="number" />
                  <EditField label={t('modal.cityLabel')} value={editState.hq_city} onChange={ef('hq_city')} />
                  <EditField label={t('modal.countryLabel')} value={editState.hq_country} onChange={ef('hq_country')} />
                  <div className="col-span-2">
                    <EditField label={t('modal.fieldWebsite')} value={editState.website} onChange={ef('website')} placeholder="https://…" />
                  </div>
                  <div className="col-span-2">
                    <EditField label={t('modal.linkedinUrlLabel')} value={editState.linkedin_company_url} onChange={ef('linkedin_company_url')} placeholder={t('modal.linkedinUrlPlaceholder')} />
                  </div>
                  <div className="col-span-2">
                    <label className="block text-xs text-gray-400 mb-1">{t('modal.descriptionLabel')}</label>
                    <textarea
                      value={editState.description}
                      onChange={ef('description')}
                      rows={4}
                      className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
                    />
                  </div>
                  <div className="col-span-2">
                    <label className="block text-xs text-gray-400 mb-1">{t('modal.fieldParentCompany')}</label>
                    <CompanyFilterPicker
                      value={editState.parent_company_id ? { id: editState.parent_company_id, name: editState.parent_name || String(editState.parent_company_id) } : null}
                      onChange={v => setEditState(s => s ? { ...s, parent_company_id: v?.id ?? null, parent_name: v?.name ?? '' } : s)}
                      placeholder={t('modal.parentCompanyPlaceholder')}
                    />
                  </div>
                </div>
                </>
              )}

              {!editing && company.description && (
                <div className="rounded-lg bg-gray-50 border border-gray-100 px-3 py-2.5 text-sm text-gray-700 whitespace-pre-wrap">
                  {company.description}
                </div>
              )}
            </>
          )}

          {/* ── Bewerbungen Tab ── */}
          {tab === 'apps' && !loading && company && (
            company.applications && company.applications.length > 0 ? (
              <div className="space-y-1.5">
                {company.applications.map(app => (
                  <button
                    key={app.id}
                    onClick={() => onOpenApplication?.(app.id)}
                    className="w-full text-left rounded-lg border border-gray-100 bg-gray-50 hover:bg-indigo-50 hover:border-indigo-200 px-3 py-2 transition-colors flex items-center justify-between gap-2"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-900 truncate">{app.rolle}</p>
                      {app.datum_bewerbung && (
                        <p className="text-xs text-gray-400">
                          {formatDateI18n(app.datum_bewerbung, locale, { day: '2-digit', month: '2-digit', year: 'numeric' })}
                        </p>
                      )}
                    </div>
                    <StatusBadge status={app.main_status as MainStatus} size="sm" />
                  </button>
                ))}
              </div>
            ) : (
              <p className="text-sm text-gray-400 text-center py-8">{t('modal.noApplications')}</p>
            )
          )}

          {/* ── Kontakte Tab ── */}
          {tab === 'contacts' && !loading && company && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-400">{t('modal.contactCount', { count: company.contacts?.length ?? 0 })}</span>
                {!addingContact && (
                  <button
                    onClick={() => { setAddingContact(true); setAddContactMode('new') }}
                    className="flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-800 font-medium"
                  >
                    <UserPlus className="h-3.5 w-3.5" />
                    {t('modal.addContact')}
                  </button>
                )}
              </div>

              {addingContact && (
                <div className="rounded-lg border border-indigo-200 bg-indigo-50 p-3 space-y-2">
                  <div className="flex rounded-md overflow-hidden border border-indigo-200 text-xs font-medium">
                    <button type="button"
                      onClick={() => { setAddContactMode('new'); setContactQuery(''); setContactResults([]) }}
                      className={`flex-1 px-2 py-1.5 ${addContactMode === 'new' ? 'bg-indigo-600 text-white' : 'bg-white text-gray-600 hover:bg-indigo-50'}`}>
                      {t('modal.createNew')}
                    </button>
                    <button type="button"
                      onClick={() => setAddContactMode('link')}
                      className={`flex-1 px-2 py-1.5 ${addContactMode === 'link' ? 'bg-indigo-600 text-white' : 'bg-white text-gray-600 hover:bg-indigo-50'}`}>
                      {t('modal.linkExisting')}
                    </button>
                  </div>

                  {addContactMode === 'new' ? (
                    <>
                      <div className="grid grid-cols-2 gap-2">
                        <input autoFocus
                          className="rounded-md border border-gray-200 px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
                          placeholder={tContacts('newContact.firstNamePlaceholder')} value={newContactDraft.vorname}
                          onChange={e => setNewContactDraft(d => ({ ...d, vorname: e.target.value }))} />
                        <input
                          className="rounded-md border border-gray-200 px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
                          placeholder={tContacts('newContact.lastNamePlaceholder')} value={newContactDraft.name}
                          onChange={e => setNewContactDraft(d => ({ ...d, name: e.target.value }))} />
                        <input
                          className="rounded-md border border-gray-200 px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
                          placeholder={tContacts('newContact.emailPlaceholder')} value={newContactDraft.email}
                          onChange={e => setNewContactDraft(d => ({ ...d, email: e.target.value }))} />
                        <input
                          className="rounded-md border border-gray-200 px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
                          placeholder={tContacts('newContact.phonePlaceholder')} value={newContactDraft.telefon}
                          onChange={e => setNewContactDraft(d => ({ ...d, telefon: e.target.value }))} />
                        <input
                          className="rounded-md border border-gray-200 px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
                          placeholder={tContacts('newContact.rolePlaceholder')} value={newContactDraft.rolle}
                          onChange={e => setNewContactDraft(d => ({ ...d, rolle: e.target.value }))} />
                        <select
                          className="rounded-md border border-gray-200 px-2 py-1.5 text-xs bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                          value={newContactDraft.typ}
                          onChange={e => setNewContactDraft(d => ({ ...d, typ: e.target.value }))}>
                          <option value="">{t('modal.typePlaceholder')}</option>
                          {CONTACT_TYPES.map(ct => <option key={ct} value={ct}>{ct}</option>)}
                        </select>
                      </div>
                      <input
                        className="w-full rounded-md border border-gray-200 px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
                        placeholder={tContacts('newContact.linkedinPlaceholder')} value={newContactDraft.linkedin_url}
                        onChange={e => setNewContactDraft(d => ({ ...d, linkedin_url: e.target.value }))} />
                      <div className="flex justify-end gap-2 pt-1">
                        <button type="button" onClick={closeAddContact} className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700">
                          <Trash2 className="h-3 w-3" /> {tCommon('cancel')}
                        </button>
                        <button type="button" disabled={!newContactDraft.name || savingNewContact} onClick={createContact}
                          className="flex items-center gap-1 rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50">
                          <Check className="h-3 w-3" />
                          {savingNewContact ? tCommon('saving') : tCommon('save')}
                        </button>
                      </div>
                    </>
                  ) : (
                    <>
                      <input
                        autoFocus
                        value={contactQuery}
                        onChange={e => setContactQuery(e.target.value)}
                        placeholder={t('modal.searchContactPlaceholder')}
                        className="w-full rounded-md border border-gray-200 px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500"
                      />
                      <div className="max-h-40 overflow-y-auto">
                        {contactSearching && <p className="text-xs text-gray-400 px-1 py-1.5">{t('modal.searching')}</p>}
                        {!contactSearching && contactResults.length === 0 && (
                          <p className="text-xs text-gray-400 px-1 py-1.5 italic">{t('modal.noResults')}</p>
                        )}
                        {contactResults.slice(0, 15).map(c => (
                          <button key={c.id} onClick={() => assignContact(c.id)}
                            className="w-full text-left px-2 py-1.5 rounded hover:bg-indigo-100 hover:text-indigo-700 transition-colors">
                            <p className="text-xs font-medium text-gray-900">{displayName(c)}</p>
                            {(c.firma || c.rolle) && (
                              <p className="text-[11px] text-gray-400">{[c.rolle, c.firma].filter(Boolean).join(' · ')}</p>
                            )}
                          </button>
                        ))}
                      </div>
                      <div className="flex justify-end">
                        <button type="button" onClick={closeAddContact} className="text-xs text-gray-500 hover:text-gray-700">{tCommon('cancel')}</button>
                      </div>
                    </>
                  )}
                </div>
              )}


              {company.contacts && company.contacts.length > 0 ? (
                <div className="space-y-1.5">
                  {company.contacts.map(contact => (
                    <div
                      key={contact.id}
                      className="flex items-start justify-between gap-2 rounded-lg border border-gray-100 bg-gray-50 px-3 py-2.5 group"
                    >
                      <button
                        onClick={() => onOpenContact?.(contact.id)}
                        className="min-w-0 flex-1 text-left hover:text-indigo-600 transition-colors"
                      >
                        <p className="text-sm font-medium text-gray-900 truncate">{displayName(contact)}</p>
                        {contact.rolle && <p className="text-xs text-gray-500 truncate">{contact.rolle}</p>}
                        <div className="flex items-center gap-3 mt-1 flex-wrap">
                          {contact.email && (
                            <span className="inline-flex items-center gap-1 text-[11px] text-gray-400">
                              <Mail className="h-3 w-3" />{contact.email}
                            </span>
                          )}
                          {(contact.phones?.length ?? 0) > 0 && (
                            <span className="inline-flex items-center gap-1 text-[11px] text-gray-400">
                              <Phone className="h-3 w-3" />{contact.phones![0].number}
                            </span>
                          )}
                          {contact.linkedin_url && (
                            <span className="inline-flex items-center gap-1 text-[11px] text-gray-400">
                              <Linkedin className="h-3 w-3" />LinkedIn
                            </span>
                          )}
                        </div>
                      </button>
                      <div className="flex items-center gap-1.5 shrink-0">
                        {contact.typ && (
                          <span className="text-[10px] font-medium bg-gray-100 text-gray-600 rounded-full px-2 py-0.5">{contact.typ}</span>
                        )}
                        <button
                          onClick={() => unassignContact(contact.id)}
                          className="text-gray-200 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100"
                          title={t('modal.unlinkContact')}
                        >
                          <UserMinus className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-gray-400 text-center py-6">{t('modal.noContacts')}</p>
              )}
            </div>
          )}

          {loading && (
            <div className="space-y-3">
              <div className="h-4 w-32 bg-gray-100 rounded animate-pulse" />
              <div className="grid grid-cols-2 gap-3">
                {[...Array(6)].map((_, i) => (
                  <div key={i} className="h-10 bg-gray-100 rounded animate-pulse" />
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs text-gray-400 mb-0.5">{label}</p>
      <div className="text-gray-900 text-sm">{children}</div>
    </div>
  )
}

function Dash() {
  return <span className="text-gray-400">—</span>
}

function EditField({ label, value, onChange, type = 'text', placeholder }: {
  label: string
  value: string
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void
  type?: string
  placeholder?: string
}) {
  return (
    <div>
      <label className="block text-xs text-gray-400 mb-1">{label}</label>
      <input
        type={type}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        className="w-full rounded-lg border border-gray-200 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
      />
    </div>
  )
}
