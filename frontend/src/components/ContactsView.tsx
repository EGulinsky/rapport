import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { Linkedin, Mail, Phone, Trash2, ArrowUpDown, GitMerge, Building2, X, RefreshCw, ChevronDown } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { ContactWithApp, CompanyProfile } from '../types'
import { ContactMergeDialog } from './MergeDialog'
import { ContactModal } from './ContactModal'
import { CompanyLogo } from './CompanyLogo'
import { CompanySearchInput } from './CompanySearchInput'
import { useLocale } from '../i18n/useLocale'
import { formatDate, collate } from '../i18n/formatDate'
import clsx from 'clsx'

function CompanyCell({ contact, onOpenCompany, onChanged }: {
  contact: ContactWithApp
  onOpenCompany?: (id: number) => void
  onChanged: () => void
}) {
  const { t } = useTranslation('contacts')
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<CompanyProfile[]>([])
  const [loading, setLoading] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) { setQuery(''); setResults([]); return }
    const t = setTimeout(async () => {
      setLoading(true)
      try { setResults(await api.companies.list({ search: query || undefined })) }
      finally { setLoading(false) }
    }, 200)
    return () => clearTimeout(t)
  }, [query, open])

  useEffect(() => {
    if (!open) return
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  async function pick(company: CompanyProfile) {
    await api.contacts.patch(contact.id, { company_profile_id: company.id, firma: company.name_display ?? company.name_norm })
    setOpen(false)
    onChanged()
  }

  async function unlink(e: React.MouseEvent) {
    e.stopPropagation()
    await api.contacts.patch(contact.id, { company_profile_id: null })
    onChanged()
  }

  return (
    <div className="relative" ref={ref}>
      {contact.firma ? (
        <div className="flex items-center gap-2">
          <CompanyLogo name={contact.firma} website={contact.company_website} size="sm" />
          {contact.company_profile_id && onOpenCompany ? (
            <button
              onClick={e => { e.stopPropagation(); onOpenCompany(contact.company_profile_id!) }}
              className="text-sm text-gray-700 hover:text-indigo-600 hover:underline text-left"
            >{contact.firma}</button>
          ) : (
            <span className="text-sm text-gray-700">{contact.firma}</span>
          )}
          {contact.company_profile_id ? (
            <button onClick={unlink} className="text-gray-300 hover:text-red-400 transition-colors" title={t('view.unlinkCompany')}>
              <X className="h-3 w-3" />
            </button>
          ) : (
            <button onClick={e => { e.stopPropagation(); setOpen(o => !o) }} className="text-gray-300 hover:text-indigo-500 transition-colors" title={t('view.assignCompany')}>
              <Building2 className="h-3 w-3" />
            </button>
          )}
        </div>
      ) : (
        <button onClick={e => { e.stopPropagation(); setOpen(o => !o) }} className="flex items-center gap-1 text-xs text-gray-300 hover:text-indigo-500 transition-colors">
          <Building2 className="h-3 w-3" />
          <span>{t('view.assign')}</span>
        </button>
      )}
      {open && (
        <div className="absolute z-50 top-full left-0 mt-1 w-64 bg-white border border-gray-200 rounded-lg shadow-lg" onClick={e => e.stopPropagation()}>
          <div className="p-2 border-b border-gray-100">
            <input
              autoFocus
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder={t('view.searchCompanyPlaceholder')}
              className="w-full rounded border border-gray-200 px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>
          <div className="max-h-48 overflow-y-auto py-1">
            {loading && <p className="text-xs text-gray-400 px-3 py-2">{t('view.searching')}</p>}
            {!loading && results.length === 0 && <p className="text-xs text-gray-400 px-3 py-2 italic">{t('view.noResults')}</p>}
            {results.slice(0, 12).map(c => (
              <button
                key={c.id}
                onClick={() => pick(c)}
                className="w-full text-left px-3 py-1.5 text-xs hover:bg-indigo-50 hover:text-indigo-700 transition-colors"
              >
                {c.name_display ?? c.name_norm}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

const TYPE_COLORS: Record<string, string> = {
  HR:          'bg-blue-100 text-blue-700',
  Headhunter:  'bg-purple-100 text-purple-700',
  FB:          'bg-orange-100 text-orange-700',
  CEO:         'bg-red-100 text-red-700',
  Netzwerk:    'bg-green-100 text-green-700',
}

type SortKey = 'vorname' | 'name' | 'firma' | 'typ' | 'letzter_kontakt'

interface Props {
  onOpenApplication: (id: number) => void
  onOpenCompany?: (id: number) => void
  search: string
  onSearchChange: (v: string) => void
  reloadKey?: number
}

export function ContactsView({ onOpenApplication, onOpenCompany, search, onSearchChange: setSearch, reloadKey }: Props) {
  const { t } = useTranslation('contacts')
  const locale = useLocale()
  const [contacts, setContacts] = useState<ContactWithApp[]>([])
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [deleting, setDeleting] = useState(false)
  const [showMerge, setShowMerge] = useState(false)
  const [sortKey, setSortKey] = useState<SortKey>('name')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')
  const [appsFilter, setAppsFilter] = useState<'all' | 'yes' | 'no'>('all')
  const [openContactId, setOpenContactId] = useState<number | null>(null)
  const [syncing, setSyncing] = useState(false)
  const [syncMenuOpen, setSyncMenuOpen] = useState(false)
  const [syncMsg, setSyncMsg] = useState<string | null>(null)
  const syncMenuRef = useRef<HTMLDivElement>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setContacts(await api.contacts.listAll(search || undefined))
      setSelected(new Set())
    } finally {
      setLoading(false)
    }
  }, [search])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    const t = setTimeout(load, 300)
    return () => clearTimeout(t)
  }, [search])

  // Neuanlage/Import laufen über das globale "Neu"-Menü in App.tsx — reloadKey
  // signalisiert von dort, dass die Liste neu geladen werden soll.
  useEffect(() => {
    if (reloadKey !== undefined) load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reloadKey])

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('asc') }
  }

  const sorted = useMemo(() => {
    let list = contacts
    if (appsFilter === 'yes') list = list.filter(c => (c.applications?.length ?? 0) > 0)
    if (appsFilter === 'no') list = list.filter(c => (c.applications?.length ?? 0) === 0)
    return [...list].sort((a, b) => {
      let av: string
      let bv: string
      if (sortKey === 'letzter_kontakt') {
        av = a.letzter_kontakt ?? ''
        bv = b.letzter_kontakt ?? ''
      } else {
        av = (a[sortKey] ?? '').toLowerCase()
        bv = (b[sortKey] ?? '').toLowerCase()
      }
      const cmp = collate(av, bv, locale)
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [contacts, sortKey, sortDir, appsFilter])

  const allSelected = sorted.length > 0 && sorted.every(c => selected.has(c.id))

  function toggleAll() {
    setSelected(allSelected ? new Set() : new Set(sorted.map(c => c.id)))
  }

  function toggleOne(id: number) {
    setSelected(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  async function deleteSelected() {
    if (selected.size === 0) return
    const isAll = selected.size === contacts.length && search === ''
    if (!confirm(t('view.deleteConfirm', { count: selected.size }))) return
    setDeleting(true)
    try {
      await api.contacts.bulkDelete(isAll ? [] : [...selected], isAll)
      await load()
    } finally {
      setDeleting(false)
    }
  }

  useEffect(() => {
    if (!syncMenuOpen) return
    const handler = (e: MouseEvent) => {
      if (syncMenuRef.current && !syncMenuRef.current.contains(e.target as Node)) setSyncMenuOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [syncMenuOpen])

  async function startSync(force: boolean) {
    setSyncMenuOpen(false)
    setSyncing(true)
    setSyncMsg(null)
    const scopedIds = selected.size > 0 ? [...selected] : undefined
    try {
      const r = await api.contacts.syncICloud(force, scopedIds)
      setSyncMsg(t('view.syncResult', { synced: r.synced.length, notFound: r.not_found.length }))
      await load()
    } catch (e) {
      setSyncMsg(e instanceof Error ? e.message : t('view.genericError'))
    } finally {
      setSyncing(false)
    }
  }

  const Th = ({ k, label, className }: { k: SortKey; label: string; className?: string }) => (
    <th
      className={clsx(
        'px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide cursor-pointer hover:text-gray-900 select-none',
        className,
      )}
      onClick={() => toggleSort(k)}
    >
      <span className="flex items-center gap-1">
        {label}
        <ArrowUpDown className={clsx('h-3 w-3 shrink-0', sortKey === k ? 'text-indigo-600' : 'text-gray-300')} />
      </span>
    </th>
  )

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center gap-3">
        <CompanySearchInput
          value={search}
          onChange={setSearch}
          placeholder={t('view.searchPlaceholder')}
          containerClassName="relative flex-1 max-w-sm"
          inputClassName="w-full rounded-lg border border-gray-200 pl-9 pr-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
        <div className="flex items-center gap-1 shrink-0">
          <span className="text-xs text-gray-400">{t('view.applicationsLabel')}</span>
          {(['all', 'yes', 'no'] as const).map(v => (
            <button key={v} onClick={() => setAppsFilter(v)}
              className={`px-2 py-1 rounded text-xs font-medium transition-colors ${appsFilter === v ? 'bg-indigo-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}>
              {v === 'all' ? t('view.filterAll') : v === 'yes' ? t('view.filterYes') : t('view.filterNo')}
            </button>
          ))}
        </div>


        <div className="relative shrink-0" ref={syncMenuRef}>
          <button
            onClick={() => !syncing && setSyncMenuOpen(o => !o)}
            disabled={syncing}
            className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {syncing
              ? <span className="animate-spin inline-block h-3.5 w-3.5 border-b-2 border-white rounded-full" />
              : <RefreshCw className="h-3.5 w-3.5" />}
            {selected.size > 0 ? t('view.syncCount', { count: selected.size }) : t('view.sync')}
            {!syncing && <ChevronDown className="h-3.5 w-3.5 opacity-70" />}
          </button>
          {syncMenuOpen && (
            <div className="absolute z-50 top-full left-0 mt-1 w-56 bg-white border border-gray-200 rounded-lg shadow-lg py-1">
              <button
                onClick={() => startSync(false)}
                className="w-full text-left px-3 py-2 text-sm hover:bg-indigo-50 hover:text-indigo-700 transition-colors"
              >
                <div className="font-medium">{t('view.syncMenuTitle')}</div>
                <div className="text-xs text-gray-400">{t('view.syncMenuSubtitle')}</div>
              </button>
              <button
                onClick={() => startSync(true)}
                className="w-full text-left px-3 py-2 text-sm hover:bg-indigo-50 hover:text-indigo-700 transition-colors"
              >
                <div className="font-medium">{t('view.resyncMenuTitle')}</div>
                <div className="text-xs text-gray-400">{t('view.resyncMenuSubtitle')}</div>
              </button>
            </div>
          )}
        </div>
        {selected.size >= 2 && (
          <button
            onClick={() => setShowMerge(true)}
            className="flex items-center gap-1.5 rounded-lg bg-violet-50 border border-violet-200 px-3 py-1.5 text-sm font-medium text-violet-700 hover:bg-violet-100 transition-colors"
          >
            <GitMerge className="h-3.5 w-3.5" />
            {t('view.merge', { count: selected.size })}
          </button>
        )}
        {selected.size > 0 && (
          <button
            onClick={deleteSelected}
            disabled={deleting}
            className="flex items-center gap-1.5 rounded-lg bg-red-50 border border-red-200 px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-100 disabled:opacity-50 transition-colors"
          >
            <Trash2 className="h-3.5 w-3.5" />
            {deleting ? t('view.deleting') : t('view.deleteCount', { count: selected.size })}
          </button>
        )}
      </div>

      {syncMsg && (
        <div className="rounded-lg bg-indigo-50 border border-indigo-100 px-4 py-2 text-sm text-indigo-700">{syncMsg}</div>
      )}

      {/* Tabelle */}
      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 bg-gray-50">
              <th className="pl-4 pr-2 py-3 w-8">
                <input
                  type="checkbox"
                  checked={allSelected}
                  ref={el => { if (el) el.indeterminate = selected.size > 0 && !allSelected }}
                  onChange={toggleAll}
                  className="rounded border-gray-300 text-indigo-600 cursor-pointer"
                />
              </th>
              <Th k="vorname" label={t('view.firstName')} />
              <Th k="name" label={t('view.lastName')} />
              <Th k="firma" label={t('view.company')} />
              <Th k="typ" label={t('view.type')} className="w-28" />
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">{t('view.contact')}</th>
              <Th k="letzter_kontakt" label={t('view.lastContact')} className="w-36" />
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">{t('view.application')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {loading && (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-gray-400">{t('view.loading')}</td>
              </tr>
            )}
            {!loading && sorted.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-gray-400 italic">{t('view.noContacts')}</td>
              </tr>
            )}
            {sorted.map(c => (
              <tr
                key={c.id}
                className={clsx('transition-colors cursor-pointer', selected.has(c.id) ? 'bg-indigo-50' : 'hover:bg-gray-50')}
                onClick={() => setOpenContactId(c.id)}
              >
                <td className="pl-4 pr-2 py-3 w-8" onClick={e => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    checked={selected.has(c.id)}
                    onChange={() => toggleOne(c.id)}
                    className="rounded border-gray-300 text-indigo-600 cursor-pointer"
                  />
                </td>
                <td className="px-4 py-3">
                  <p className="text-gray-700">{c.vorname || <span className="text-gray-300">—</span>}</p>
                </td>
                <td className="px-4 py-3">
                  <p className="font-medium text-gray-900">{c.name}</p>
                  {c.rolle && <p className="text-xs text-gray-500">{c.rolle}</p>}
                </td>
                <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                  <CompanyCell contact={c} onOpenCompany={onOpenCompany} onChanged={load} />
                </td>
                <td className="px-4 py-3">
                  {c.typ ? (
                    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${TYPE_COLORS[c.typ] ?? 'bg-gray-100 text-gray-600'}`}>
                      {c.typ}
                    </span>
                  ) : (
                    <span className="text-gray-300">—</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-col gap-0.5">
                    {c.email && (
                      <a href={`mailto:${c.email}`} className="flex items-center gap-1 text-xs text-gray-600 hover:text-indigo-600">
                        <Mail className="h-3 w-3 shrink-0" />
                        <span className="truncate max-w-[180px]">{c.email}</span>
                      </a>
                    )}
                    {(c.phones?.length ?? 0) > 0 && (
                      <a href={`tel:${c.phones![0].number}`} className="flex items-center gap-1 text-xs text-gray-600 hover:text-indigo-600">
                        <Phone className="h-3 w-3 shrink-0" />
                        {c.phones![0].number}
                        {c.phones!.length > 1 && <span className="text-gray-400">+{c.phones!.length - 1}</span>}
                      </a>
                    )}
                    {c.linkedin_url && (
                      <a href={c.linkedin_url} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-xs text-indigo-500 hover:underline">
                        <Linkedin className="h-3 w-3 shrink-0" />
                        {t('view.linkedin')}
                      </a>
                    )}
                    {!c.email && !(c.phones?.length) && !c.linkedin_url && (
                      <span className="text-xs text-gray-300">—</span>
                    )}
                  </div>
                </td>
                <td className="px-4 py-3 text-xs text-gray-500 whitespace-nowrap">
                  {c.letzter_kontakt
                    ? formatDate(c.letzter_kontakt, locale)
                    : <span className="text-gray-300">—</span>}
                </td>
                <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                  {c.applications && c.applications.length > 0 ? (
                    <div className="flex flex-col gap-1">
                      {c.applications.map(a => (
                        <button
                          key={a.id}
                          onClick={() => onOpenApplication(a.id)}
                          className="text-left hover:text-indigo-600 transition-colors"
                        >
                          <p className="font-medium text-gray-800 hover:text-indigo-600 leading-tight">{a.company_name_display ?? a.firma}</p>
                          <p className="text-xs text-gray-500 truncate max-w-[160px]">{a.rolle}</p>
                        </button>
                      ))}
                    </div>
                  ) : (
                    <span className="text-xs text-gray-300">{t('view.noApplication')}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!loading && contacts.length > 0 && (
          <div className="border-t border-gray-100 bg-gray-50 px-4 py-2 text-xs text-gray-400 flex items-center justify-between">
            <span>
              {t('view.contactCount', { count: sorted.length })}
              {sorted.length !== contacts.length && <span className="ml-1 text-gray-300">{t('view.ofTotal', { count: contacts.length })}</span>}
            </span>
            {selected.size > 0 && (
              <span className="text-indigo-600 font-medium">{t('view.selectedCount', { count: selected.size })}</span>
            )}
          </div>
        )}
      </div>

      {showMerge && selected.size >= 2 && (
        <ContactMergeDialog
          contactIds={[...selected]}
          contacts={contacts.filter(c => selected.has(c.id))}
          onMerged={() => { setShowMerge(false); load() }}
          onClose={() => setShowMerge(false)}
        />
      )}

      {openContactId !== null && (
        <ContactModal
          id={openContactId}
          onClose={() => setOpenContactId(null)}
          onOpenApplication={id => { setOpenContactId(null); onOpenApplication(id) }}
          onOpenCompany={onOpenCompany}
          onChanged={load}
        />
      )}
    </div>
  )
}
