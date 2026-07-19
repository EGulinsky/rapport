import { useState, useEffect, useCallback, useRef } from 'react'
import { X, Pencil, Save, RotateCcw, Mail, Phone, Linkedin, Building2, ExternalLink, RefreshCw, Calendar } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { ContactWithApp, ContactEvents, ContactEventItem } from '../types'
import { CompanyLogo } from './CompanyLogo'
import { buildDeepLink, SourceBadge } from './ApplicationModal'
import { PhoneListEditor, type PhoneEntry } from './PhoneListEditor'
import { useLocale } from '../i18n/useLocale'
import { formatDate } from '../i18n/formatDate'
import { errorMessage } from '../i18n/errorMessage'
import clsx from 'clsx'

interface Props {
  id: number
  onClose: () => void
  onOpenApplication?: (id: number) => void
  onOpenCompany?: (id: number) => void
  onChanged?: () => void
}

type Tab = 'overview' | 'apps' | 'calls' | 'mails' | 'calendar' | 'messages'

const TYP_OPTIONS = ['HR', 'Headhunter', 'FB', 'CEO', 'Netzwerk', 'Sonstiges']

const TYPE_COLORS: Record<string, string> = {
  HR:         'bg-blue-100 text-blue-700',
  Headhunter: 'bg-purple-100 text-purple-700',
  FB:         'bg-orange-100 text-orange-700',
  CEO:        'bg-red-100 text-red-700',
  Netzwerk:   'bg-green-100 text-green-700',
}

interface EditState {
  vorname: string
  name: string
  email: string
  phones: PhoneEntry[]
  linkedin_url: string
  rolle: string
  typ: string
  firma: string
  notizen: string
  letzter_kontakt: string
}

function toEditState(c: ContactWithApp): EditState {
  return {
    vorname: c.vorname ?? '',
    name: c.name,
    email: c.email ?? '',
    phones: (c.phones ?? []).map(p => ({ number: p.number, type: p.type })),
    linkedin_url: c.linkedin_url ?? '',
    rolle: c.rolle ?? '',
    typ: c.typ ?? '',
    firma: c.firma ?? '',
    notizen: c.notizen ?? '',
    letzter_kontakt: c.letzter_kontakt ?? '',
  }
}

export function displayName(c: { name: string; vorname?: string | null }): string {
  return c.vorname ? `${c.vorname} ${c.name}` : c.name
}

export function ContactModal({ id, onClose, onOpenApplication, onOpenCompany, onChanged }: Props) {
  const { t } = useTranslation('contacts')
  const { t: tCommon } = useTranslation('common')
  const locale = useLocale()
  const [contact, setContact] = useState<ContactWithApp | null>(null)
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [editState, setEditState] = useState<EditState | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [syncing, setSyncing] = useState<'sync' | 'resync' | null>(null)
  const [syncResult, setSyncResult] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('overview')
  const [events, setEvents] = useState<ContactEvents | null>(null)
  const [eventsLoading, setEventsLoading] = useState(true)
  const tabsScrollRef = useRef<HTMLDivElement>(null)
  const [tabsOverflowRight, setTabsOverflowRight] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const contacts = await api.contacts.listAll()
      const c = contacts.find(x => x.id === id)
      if (c) setContact(c)
    } finally {
      setLoading(false)
    }
  }, [id])

  const loadEvents = useCallback(async () => {
    setEventsLoading(true)
    try {
      setEvents(await api.contacts.getEvents(id))
    } finally {
      setEventsLoading(false)
    }
  }, [id])

  useEffect(() => { load(); loadEvents() }, [load, loadEvents])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  // The tabs row hides its native scrollbar (v4.6.13) for a cleaner look,
  // but that also hid any hint that scrolling right reveals more tabs --
  // the LinkedIn tab in particular ended up practically undiscoverable.
  // Track whether there's still hidden content to the right and show a
  // fade-out edge instead, only when it's actually needed.
  useEffect(() => {
    const el = tabsScrollRef.current
    if (!el) return
    function update() {
      if (!el) return
      setTabsOverflowRight(el.scrollWidth - el.clientWidth - el.scrollLeft > 1)
    }
    update()
    el.addEventListener('scroll', update)
    window.addEventListener('resize', update)
    return () => {
      el.removeEventListener('scroll', update)
      window.removeEventListener('resize', update)
    }
  }, [contact, events, tab])

  function startEdit() {
    if (!contact) return
    setEditState(toEditState(contact))
    setEditing(true)
    setSaveError(null)
  }

  function cancelEdit() {
    setEditing(false)
    setEditState(null)
    setSaveError(null)
  }

  function set(field: keyof Omit<EditState, 'phones'>, value: string) {
    setEditState(prev => prev ? { ...prev, [field]: value } : prev)
  }

  function setPhones(phones: PhoneEntry[]) {
    setEditState(prev => prev ? { ...prev, phones } : prev)
  }

  async function saveEdit() {
    if (!editState || !contact) return
    setSaving(true)
    setSaveError(null)
    try {
      await api.contacts.patch(contact.id, {
        name: editState.name || contact.name,
        vorname: editState.vorname || undefined,
        email: editState.email || undefined,
        phones: editState.phones.filter(p => p.number.trim()),
        linkedin_url: editState.linkedin_url || undefined,
        rolle: editState.rolle || undefined,
        typ: editState.typ || undefined,
        firma: editState.firma || undefined,
        notizen: editState.notizen || undefined,
        letzter_kontakt: editState.letzter_kontakt || undefined,
      })
      await load()
      setEditing(false)
      setEditState(null)
      onChanged?.()
    } catch (e) {
      setSaveError(errorMessage(e, t))
    } finally {
      setSaving(false)
    }
  }

  async function runSync(force: boolean) {
    if (!contact) return
    setSyncing(force ? 'resync' : 'sync')
    setSyncResult(null)
    try {
      const result = await api.contacts.syncICloud(force, [contact.id])
      if (result.not_found.includes(contact.id)) {
        setSyncResult(t('contactModal.syncNotFound'))
      } else if (result.errors.length > 0) {
        setSyncResult(result.errors[0])
      } else {
        setSyncResult(force ? t('contactModal.resyncDone') : t('contactModal.syncDone'))
      }
      await load()
      onChanged?.()
    } catch (e) {
      setSyncResult(errorMessage(e, t))
    } finally {
      setSyncing(null)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm" onClick={onClose}>
      <div
        className="relative bg-white rounded-2xl shadow-2xl w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between px-6 pt-5 pb-4 border-b border-gray-100">
          <div className="flex-1 min-w-0">
            {loading ? (
              <div className="h-6 w-48 bg-gray-100 rounded animate-pulse" />
            ) : contact ? (
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-700 font-semibold text-sm shrink-0">
                  {displayName(contact).slice(0, 2).toUpperCase()}
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-gray-900 leading-tight">{displayName(contact)}</h2>
                  {contact.rolle && <p className="text-sm text-gray-500">{contact.rolle}</p>}
                  {contact.icloud_last_synced_at && (
                    <p className="text-xs text-gray-400 mt-0.5">
                      {t('contactModal.lastSynced', { date: formatDate(contact.icloud_last_synced_at, locale) })}
                    </p>
                  )}
                </div>
              </div>
            ) : (
              <p className="text-gray-500">{t('contactModal.notFound')}</p>
            )}
          </div>
          <div className="flex items-center gap-2 ml-4 shrink-0">
            {contact && !editing && (
              <>
                <button
                  onClick={() => runSync(false)}
                  disabled={syncing !== null}
                  title={t('contactModal.syncHint')}
                  className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium text-gray-600 hover:bg-gray-100 transition-colors disabled:opacity-50"
                >
                  <RefreshCw className={clsx('h-3.5 w-3.5', syncing === 'sync' && 'animate-spin')} />
                  {t('contactModal.sync')}
                </button>
                <button
                  onClick={() => runSync(true)}
                  disabled={syncing !== null}
                  title={t('contactModal.resyncHint')}
                  className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium text-gray-600 hover:bg-gray-100 transition-colors disabled:opacity-50"
                >
                  <RefreshCw className={clsx('h-3.5 w-3.5', syncing === 'resync' && 'animate-spin')} />
                  {t('contactModal.resync')}
                </button>
                <button
                  onClick={startEdit}
                  className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium text-gray-600 hover:bg-gray-100 transition-colors"
                >
                  <Pencil className="h-3.5 w-3.5" />
                  {t('contactModal.edit')}
                </button>
              </>
            )}
            {editing && (
              <>
                <button
                  onClick={cancelEdit}
                  className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium text-gray-600 hover:bg-gray-100 transition-colors"
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                  {tCommon('cancel')}
                </button>
                <button
                  onClick={saveEdit}
                  disabled={saving}
                  className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors"
                >
                  <Save className="h-3.5 w-3.5" />
                  {saving ? tCommon('saving') : tCommon('save')}
                </button>
              </>
            )}
            <button onClick={onClose} className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors">
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Tabs */}
        {contact && (
          <div className="relative border-b border-gray-100">
            <div
              ref={tabsScrollRef}
              className="flex px-6 gap-1 overflow-x-auto [&::-webkit-scrollbar]:hidden"
              style={{ scrollbarWidth: 'none' }}
            >
              {([
                ['overview', t('contactModal.tabOverview'), undefined],
                ['apps', t('contactModal.tabApplications'), contact.applications?.length],
                ['calls', t('contactModal.tabCalls'), events?.calls.length],
                ['mails', t('contactModal.tabMails'), events?.mails.length],
                ['calendar', t('contactModal.tabCalendar'), events?.calendar.length],
                ['messages', t('contactModal.tabMessages'), events?.messages.length],
              ] as [Tab, string, number | undefined][]).map(([tabKey, label, count]) => (
                <button
                  key={tabKey}
                  onClick={() => setTab(tabKey)}
                  className={clsx(
                    'flex items-center gap-1.5 px-3 py-2.5 text-xs font-medium border-b-2 -mb-px transition-colors whitespace-nowrap',
                    tab === tabKey
                      ? 'border-indigo-500 text-indigo-700'
                      : 'border-transparent text-gray-500 hover:text-gray-800'
                  )}
                >
                  {label}
                  {!!count && (
                    <span className={clsx(
                      'rounded-full px-1.5 py-0.5 text-[10px] font-semibold',
                      tab === tabKey ? 'bg-indigo-100 text-indigo-700' : 'bg-gray-100 text-gray-500'
                    )}>
                      {count}
                    </span>
                  )}
                </button>
              ))}
            </div>
            {tabsOverflowRight && (
              <div className="pointer-events-none absolute right-0 top-0 bottom-0 w-8 bg-gradient-to-l from-white to-transparent" />
            )}
          </div>
        )}

        {saveError && (
          <div className="mx-6 mt-4 rounded-lg bg-red-50 border border-red-200 px-4 py-2 text-sm text-red-700">{saveError}</div>
        )}

        {syncResult && (
          <div className="mx-6 mt-4 rounded-lg bg-indigo-50 border border-indigo-100 px-4 py-2 text-sm text-indigo-700">{syncResult}</div>
        )}

        {loading && (
          <div className="px-6 py-8 text-center text-gray-400">{t('view.loading')}</div>
        )}

        {!loading && contact && !editing && tab === 'overview' && (
          <div className="px-6 py-5 space-y-5">
            {/* Kontaktdaten */}
            <div className="space-y-2">
              <p className="text-xs font-medium text-gray-400 uppercase tracking-wide">{t('view.contact')}</p>
              {contact.email && (
                <a href={`mailto:${contact.email}`} className="flex items-center gap-2 text-sm text-gray-700 hover:text-indigo-600">
                  <Mail className="h-3.5 w-3.5 text-gray-400 shrink-0" />
                  {contact.email}
                </a>
              )}
              {(contact.phones ?? []).map(p => (
                <a key={p.id} href={`tel:${p.number}`} className="flex items-center gap-2 text-sm text-gray-700 hover:text-indigo-600">
                  <Phone className="h-3.5 w-3.5 text-gray-400 shrink-0" />
                  {p.number}
                  <span className="text-xs text-gray-400">{t(`phoneTypes.${p.type}`)}</span>
                </a>
              ))}
              {contact.linkedin_url && (
                <a href={contact.linkedin_url} target="_blank" rel="noreferrer" className="flex items-center gap-2 text-sm text-indigo-600 hover:underline">
                  <Linkedin className="h-3.5 w-3.5 shrink-0" />
                  {t('view.linkedin')}
                  <ExternalLink className="h-3 w-3" />
                </a>
              )}
              {!contact.email && (contact.phones ?? []).length === 0 && !contact.linkedin_url && (
                <p className="text-sm text-gray-300">{t('contactModal.noContactData')}</p>
              )}
            </div>

            {/* Rolle is already shown under the name in the header -- no need to repeat it here. */}
            {contact.firma && (
              <div>
                <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-1">{t('view.company')}</p>
                <div className="flex items-center gap-2">
                  <CompanyLogo name={contact.firma} website={contact.company_website ?? undefined} size="sm" />
                  {contact.company_profile_id && onOpenCompany ? (
                    <button
                      onClick={() => onOpenCompany(contact.company_profile_id!)}
                      className="text-sm text-gray-700 hover:text-indigo-600 hover:underline text-left flex items-center gap-1"
                    >
                      {contact.firma}
                      <Building2 className="h-3 w-3 text-gray-400" />
                    </button>
                  ) : (
                    <span className="text-sm text-gray-700">{contact.firma}</span>
                  )}
                </div>
              </div>
            )}

            {contact.typ && (
              <div>
                <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-1">{t('view.type')}</p>
                <span className={clsx('inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium', TYPE_COLORS[contact.typ] ?? 'bg-gray-100 text-gray-600')}>
                  {contact.typ}
                </span>
              </div>
            )}

            {contact.letzter_kontakt && (
              <div>
                <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-1">{t('view.lastContact')}</p>
                <p className="text-sm text-gray-900">{formatDate(contact.letzter_kontakt, locale)}</p>
              </div>
            )}

            {contact.notizen && (
              <div>
                <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-1">{t('contactModal.notes')}</p>
                <p className="text-sm text-gray-700 whitespace-pre-wrap">{contact.notizen}</p>
              </div>
            )}
          </div>
        )}

        {/* Applications tab */}
        {!loading && contact && !editing && tab === 'apps' && (
          <div className="px-6 py-5">
            {contact.applications && contact.applications.length > 0 ? (
              <div className="space-y-1">
                {contact.applications.map(a => (
                  <button
                    key={a.id}
                    onClick={() => onOpenApplication?.(a.id)}
                    className="w-full text-left rounded-lg border border-gray-100 px-3 py-2 hover:border-indigo-200 hover:bg-indigo-50 transition-colors"
                  >
                    <p className="text-sm font-medium text-gray-800">{a.company_name_display ?? a.firma}</p>
                    <p className="text-xs text-gray-500 truncate">{a.rolle}</p>
                  </button>
                ))}
              </div>
            ) : (
              <p className="text-sm text-gray-400 text-center py-8">{t('contactModal.noApplications')}</p>
            )}
          </div>
        )}

        {/* Calls / Mails / Calendar / Messages tabs */}
        {!loading && contact && !editing && (tab === 'calls' || tab === 'mails' || tab === 'calendar' || tab === 'messages') && (
          <div className="px-6 py-5">
            {eventsLoading ? (
              <div className="py-8 text-center text-gray-400">{t('view.loading')}</div>
            ) : (
              <EventList
                items={
                  tab === 'calls' ? (events?.calls ?? [])
                  : tab === 'mails' ? (events?.mails ?? [])
                  : tab === 'calendar' ? (events?.calendar ?? [])
                  : (events?.messages ?? [])
                }
                emptyLabel={
                  tab === 'calls' ? t('contactModal.noCalls')
                  : tab === 'mails' ? t('contactModal.noMails')
                  : tab === 'calendar' ? t('contactModal.noCalendar')
                  : t('contactModal.noMessages')
                }
                icon={
                  tab === 'calls' ? <Phone className="h-3.5 w-3.5" />
                  : tab === 'mails' ? <Mail className="h-3.5 w-3.5" />
                  : tab === 'calendar' ? <Calendar className="h-3.5 w-3.5" />
                  : <Linkedin className="h-3.5 w-3.5" />
                }
                locale={locale}
                onOpenApplication={onOpenApplication}
              />
            )}
          </div>
        )}

        {/* Edit form */}
        {!loading && contact && editing && editState && (
          <div className="px-6 py-5 space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">{t('view.firstName')}</label>
                <input
                  value={editState.vorname}
                  onChange={e => set('vorname', e.target.value)}
                  className="w-full rounded-lg border border-gray-200 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder={t('view.firstName')}
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">{t('view.lastName')} *</label>
                <input
                  value={editState.name}
                  onChange={e => set('name', e.target.value)}
                  className="w-full rounded-lg border border-gray-200 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder={t('view.lastName')}
                  required
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">{t('contactModal.emailRequired')}</label>
              <input
                type="email"
                value={editState.email}
                onChange={e => set('email', e.target.value)}
                className="w-full rounded-lg border border-gray-200 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder={t('newContact.emailPlaceholder')}
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">{t('contactModal.phoneLabel')}</label>
              <PhoneListEditor phones={editState.phones} onChange={setPhones} />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">{t('contactModal.linkedinLabel')}</label>
              <input
                value={editState.linkedin_url}
                onChange={e => set('linkedin_url', e.target.value)}
                className="w-full rounded-lg border border-gray-200 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder={t('contactModal.linkedinPlaceholder')}
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">{t('view.company')}</label>
                <input
                  value={editState.firma}
                  onChange={e => set('firma', e.target.value)}
                  className="w-full rounded-lg border border-gray-200 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder={t('newContact.companyPlaceholder')}
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">{t('contactModal.role')}</label>
                <input
                  value={editState.rolle}
                  onChange={e => set('rolle', e.target.value)}
                  className="w-full rounded-lg border border-gray-200 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder={t('contactModal.rolePlaceholder')}
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">{t('view.type')}</label>
                <select
                  value={editState.typ}
                  onChange={e => set('typ', e.target.value)}
                  className="w-full rounded-lg border border-gray-200 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
                >
                  <option value="">—</option>
                  {TYP_OPTIONS.map(opt => <option key={opt} value={opt}>{opt}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">{t('view.lastContact')}</label>
                <input
                  type="date"
                  value={editState.letzter_kontakt}
                  onChange={e => set('letzter_kontakt', e.target.value)}
                  className="w-full rounded-lg border border-gray-200 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">{t('contactModal.notes')}</label>
              <textarea
                value={editState.notizen}
                onChange={e => set('notizen', e.target.value)}
                rows={3}
                className="w-full rounded-lg border border-gray-200 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
                placeholder={t('contactModal.notesPlaceholder')}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export function EventList({ items, emptyLabel, icon, locale, onOpenApplication }: {
  items: ContactEventItem[]
  emptyLabel: string
  icon: React.ReactNode
  locale: string
  onOpenApplication?: (id: number) => void
}) {
  if (items.length === 0) {
    return <p className="text-sm text-gray-400 text-center py-8">{emptyLabel}</p>
  }
  return (
    <div className="space-y-1.5">
      {items.map(item => {
        // Same "click to open" behavior as the application timeline's
        // SourceBadge: opens the synced item directly (Gmail/Calendar/etc.)
        // when a deep link is available for this source, falls back to
        // jumping to the application otherwise (e.g. calls/LinkedIn
        // messages, which have no external app link to open).
        const deepLink = buildDeepLink(item.source, item.external_id, item.external_url)
        function handleActivate() {
          if (deepLink) window.open(deepLink, '_blank', 'noreferrer')
          else onOpenApplication?.(item.application_id)
        }
        return (
          <div
            key={item.id}
            role="button"
            tabIndex={0}
            onClick={handleActivate}
            onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleActivate() } }}
            className="w-full text-left rounded-lg border border-gray-100 bg-gray-50 hover:bg-indigo-50 hover:border-indigo-200 px-3 py-2 transition-colors cursor-pointer"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-start gap-2 min-w-0">
                <span className="mt-0.5 text-gray-400 shrink-0">{icon}</span>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-gray-800 truncate">{item.titel || '—'}</p>
                  <div className="flex items-center gap-1.5 flex-wrap mt-0.5">
                    {(item.company_name || item.rolle) && (
                      <p className="text-xs text-gray-500 truncate">
                        {[item.company_name, item.rolle].filter(Boolean).join(' · ')}
                      </p>
                    )}
                    <span onClick={e => e.stopPropagation()}>
                      <SourceBadge source={item.source} external_id={item.external_id} external_url={item.external_url} />
                    </span>
                  </div>
                  {item.notiz && (
                    <p className="text-xs text-gray-400 truncate mt-0.5">{item.notiz}</p>
                  )}
                </div>
              </div>
              {item.datum && (
                <span className="text-xs text-gray-400 shrink-0">{formatDate(item.datum, locale)}</span>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
