import { useState, useEffect, useCallback, useRef } from 'react'
import { X, ExternalLink, Clock, CheckCircle, XCircle, Pencil, GitMerge, Save, RotateCcw, Linkedin, Mail, Phone, Upload, Trash2, UserPlus, UserMinus } from 'lucide-react'
import { api } from '../api/client'
import type { CompanyProfile, MainStatus, ContactWithApp } from '../types'
import { StatusBadge } from './StatusBadge'
import { CompanyLogo } from './CompanyLogo'
import clsx from 'clsx'

interface Props {
  id: number
  onClose: () => void
  onOpenApplication?: (id: number) => void
  onOpenContact?: (id: number) => void
  onMergeRequest?: (ids: number[]) => void
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

const SYNC_SOURCE_LABELS: Record<string, string> = {
  ai: 'KI', linkedin: 'LinkedIn', manual: 'Manuell',
}

const COMPANY_TYPES = ['startup', 'konzern', 'kmu', 'beratung', 'headhunter', 'nonprofit', 'public', 'other']

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
  }
}

export function CompanyModal({ id, onClose, onOpenApplication, onOpenContact, onMergeRequest }: Props) {
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
  const [contactQuery, setContactQuery] = useState('')
  const [contactResults, setContactResults] = useState<ContactWithApp[]>([])
  const [contactSearching, setContactSearching] = useState(false)
  const addContactRef = useRef<HTMLDivElement>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.companies.get(id)
      setCompany(data)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (!addingContact) { setContactQuery(''); setContactResults([]); return }
    const t = setTimeout(async () => {
      setContactSearching(true)
      try { setContactResults(await api.contacts.listAll(contactQuery || undefined)) }
      finally { setContactSearching(false) }
    }, 200)
    return () => clearTimeout(t)
  }, [contactQuery, addingContact])

  useEffect(() => {
    if (!addingContact) return
    function handler(e: MouseEvent) {
      if (addContactRef.current && !addContactRef.current.contains(e.target as Node)) setAddingContact(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [addingContact])

  async function assignContact(contactId: number) {
    await api.companies.assignContact(id, contactId)
    setAddingContact(false)
    load()
  }

  async function unassignContact(contactId: number) {
    await api.companies.unassignContact(id, contactId)
    load()
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
      })
      setCompany(updated)
      setEditing(false)
      setEditState(null)
    } catch (e) {
      setSaveError(String(e))
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
    } catch (e) {
      setSaveError(String(e))
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
    } catch (e) {
      setSaveError(String(e))
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
    return new Date(s).toLocaleDateString('de-DE')
  }

  const location = [company?.hq_city, company?.hq_country].filter(Boolean).join(', ')

  const tabs: [Tab, string, number | undefined][] = [
    ['info', 'Profil', undefined],
    ['apps', 'Bewerbungen', company?.app_count],
    ['contacts', 'Kontakte', company?.contact_count],
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
                      {SYNC_SOURCE_LABELS[company.sync_source] ?? company.sync_source}
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
                    title="Mit anderer Firma zusammenführen"
                    className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 transition-colors"
                  >
                    <GitMerge className="h-4 w-4" />
                  </button>
                )}
                <button
                  onClick={startEdit}
                  title="Bearbeiten"
                  className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 transition-colors"
                >
                  <Pencil className="h-4 w-4" />
                </button>
              </>
            )}
            {editing && (
              <>
                <button onClick={cancelEdit} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 transition-colors" title="Abbrechen">
                  <RotateCcw className="h-4 w-4" />
                </button>
                <button
                  onClick={saveEdit}
                  disabled={saving}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-xs font-medium hover:bg-indigo-700 disabled:opacity-50"
                >
                  <Save className="h-3.5 w-3.5" />
                  {saving ? 'Speichern…' : 'Speichern'}
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
                    <Clock className="h-3 w-3" /> Ausstehend
                  </span>
                )}
                {company.sync_status === 'done' && (
                  <span className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium bg-green-100 text-green-700">
                    <CheckCircle className="h-3 w-3" /> Synchronisiert
                  </span>
                )}
                {company.sync_status === 'failed' && (
                  <span className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium bg-red-100 text-red-700" title={company.sync_error ?? undefined}>
                    <XCircle className="h-3 w-3" /> Fehler
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
                  <Field label="Anzeigename">{company.name_display || <Dash />}</Field>
                  <Field label="Branche">{company.industry || <Dash />}</Field>
                  <Field label="Typ">
                    {company.company_type ? (
                      <span className={clsx('inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium', COMPANY_TYPE_COLORS[company.company_type] ?? 'bg-gray-100 text-gray-600')}>
                        {COMPANY_TYPE_LABELS[company.company_type] ?? company.company_type}
                      </span>
                    ) : <Dash />}
                  </Field>
                  <Field label="Mitarbeiter">{company.employee_range || (company.employee_count != null ? String(company.employee_count) : <Dash />)}</Field>
                  <Field label="Gegründet">{company.founded_year ?? <Dash />}</Field>
                  <Field label="Standort">{location || <Dash />}</Field>
                  {company.website && (
                    <Field label="Website">
                      <a href={company.website} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-indigo-600 hover:text-indigo-800 text-xs">
                        <ExternalLink className="h-3 w-3" />
                        {company.website.replace(/^https?:\/\//, '').replace(/\/$/, '')}
                      </a>
                    </Field>
                  )}
                  {company.linkedin_company_url && (
                    <Field label="LinkedIn">
                      <a href={company.linkedin_company_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-indigo-600 hover:text-indigo-800 text-xs">
                        <ExternalLink className="h-3 w-3" /> LinkedIn
                      </a>
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
                      Logo hochladen
                    </button>
                    {(logoPreview ?? company.logo_data) && (
                      <button
                        type="button"
                        onClick={deleteLogo}
                        disabled={logoUploading}
                        className="flex items-center gap-1.5 rounded-lg border border-red-200 px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-50 transition-colors"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                        Logo entfernen
                      </button>
                    )}
                    {logoUploading && <span className="text-xs text-gray-400">Wird hochgeladen…</span>}
                    <span className="text-xs text-gray-400">oder Bild einfügen (Strg+V)</span>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-x-4 gap-y-3">
                  <EditField label="Anzeigename" value={editState.name_display} onChange={ef('name_display')} />
                  <EditField label="Branche" value={editState.industry} onChange={ef('industry')} />
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">Typ</label>
                    <select value={editState.company_type} onChange={ef('company_type')}
                      className="w-full rounded-lg border border-gray-200 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
                      <option value="">—</option>
                      {COMPANY_TYPES.map(t => <option key={t} value={t}>{COMPANY_TYPE_LABELS[t]}</option>)}
                    </select>
                  </div>
                  <EditField label="Mitarbeiter (Range)" value={editState.employee_range} onChange={ef('employee_range')} placeholder="z.B. 50-200" />
                  <EditField label="Mitarbeiteranzahl" value={editState.employee_count} onChange={ef('employee_count')} type="number" />
                  <EditField label="Gegründet" value={editState.founded_year} onChange={ef('founded_year')} type="number" />
                  <EditField label="Stadt" value={editState.hq_city} onChange={ef('hq_city')} />
                  <EditField label="Land" value={editState.hq_country} onChange={ef('hq_country')} />
                  <div className="col-span-2">
                    <EditField label="Website" value={editState.website} onChange={ef('website')} placeholder="https://…" />
                  </div>
                  <div className="col-span-2">
                    <EditField label="LinkedIn URL" value={editState.linkedin_company_url} onChange={ef('linkedin_company_url')} placeholder="https://linkedin.com/company/…" />
                  </div>
                  <div className="col-span-2">
                    <label className="block text-xs text-gray-400 mb-1">Beschreibung</label>
                    <textarea
                      value={editState.description}
                      onChange={ef('description')}
                      rows={4}
                      className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
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
                          {new Date(app.datum_bewerbung).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })}
                        </p>
                      )}
                    </div>
                    <StatusBadge status={app.main_status as MainStatus} size="sm" />
                  </button>
                ))}
              </div>
            ) : (
              <p className="text-sm text-gray-400 text-center py-8">Keine verknüpften Bewerbungen</p>
            )
          )}

          {/* ── Kontakte Tab ── */}
          {tab === 'contacts' && !loading && company && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-400">{company.contacts?.length ?? 0} Kontakte</span>
                <div className="relative" ref={addContactRef}>
                  <button
                    onClick={() => setAddingContact(o => !o)}
                    className="flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-800 font-medium"
                  >
                    <UserPlus className="h-3.5 w-3.5" />
                    Kontakt hinzufügen
                  </button>
                  {addingContact && (
                    <div className="absolute z-50 right-0 mt-1 w-72 bg-white border border-gray-200 rounded-lg shadow-lg">
                      <div className="p-2 border-b border-gray-100">
                        <input
                          autoFocus
                          value={contactQuery}
                          onChange={e => setContactQuery(e.target.value)}
                          placeholder="Name oder Firma suchen…"
                          className="w-full rounded border border-gray-200 px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500"
                        />
                      </div>
                      <div className="max-h-56 overflow-y-auto py-1">
                        {contactSearching && <p className="text-xs text-gray-400 px-3 py-2">Suche…</p>}
                        {!contactSearching && contactResults.length === 0 && (
                          <p className="text-xs text-gray-400 px-3 py-2 italic">Keine Treffer</p>
                        )}
                        {contactResults.slice(0, 15).map(c => (
                          <button
                            key={c.id}
                            onClick={() => assignContact(c.id)}
                            className="w-full text-left px-3 py-1.5 hover:bg-indigo-50 hover:text-indigo-700 transition-colors"
                          >
                            <p className="text-xs font-medium text-gray-900">{c.name}</p>
                            {(c.firma || c.rolle) && (
                              <p className="text-[11px] text-gray-400">{[c.rolle, c.firma].filter(Boolean).join(' · ')}</p>
                            )}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>

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
                        <p className="text-sm font-medium text-gray-900 truncate">{contact.name}</p>
                        {contact.rolle && <p className="text-xs text-gray-500 truncate">{contact.rolle}</p>}
                        <div className="flex items-center gap-3 mt-1 flex-wrap">
                          {contact.email && (
                            <span className="inline-flex items-center gap-1 text-[11px] text-gray-400">
                              <Mail className="h-3 w-3" />{contact.email}
                            </span>
                          )}
                          {contact.telefon && (
                            <span className="inline-flex items-center gap-1 text-[11px] text-gray-400">
                              <Phone className="h-3 w-3" />{contact.telefon}
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
                          title="Verknüpfung lösen"
                        >
                          <UserMinus className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-gray-400 text-center py-6">Keine verknüpften Kontakte</p>
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
