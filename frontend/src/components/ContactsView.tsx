import { useState, useEffect, useCallback, useMemo } from 'react'
import { Search, Linkedin, Mail, Phone, Trash2, ArrowUpDown, GitMerge } from 'lucide-react'
import { api } from '../api/client'
import type { ContactWithApp } from '../types'
import { ContactMergeDialog } from './MergeDialog'
import { CompanyLogo } from './CompanyLogo'
import clsx from 'clsx'

const TYPE_COLORS: Record<string, string> = {
  HR:          'bg-blue-100 text-blue-700',
  Headhunter:  'bg-purple-100 text-purple-700',
  FB:          'bg-orange-100 text-orange-700',
  CEO:         'bg-red-100 text-red-700',
  Netzwerk:    'bg-green-100 text-green-700',
}

type SortKey = 'name' | 'firma' | 'typ' | 'letzter_kontakt'

interface Props {
  onOpenApplication: (id: number) => void
  onOpenCompany?: (id: number) => void
  initialSearch?: string
}

export function ContactsView({ onOpenApplication, onOpenCompany, initialSearch = '' }: Props) {
  const [contacts, setContacts] = useState<ContactWithApp[]>([])
  const [search, setSearch] = useState(initialSearch)
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [deleting, setDeleting] = useState(false)
  const [showMerge, setShowMerge] = useState(false)
  const [sortKey, setSortKey] = useState<SortKey>('name')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')

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

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('asc') }
  }

  const sorted = useMemo(() => {
    return [...contacts].sort((a, b) => {
      let av: string
      let bv: string
      if (sortKey === 'letzter_kontakt') {
        av = a.letzter_kontakt ?? ''
        bv = b.letzter_kontakt ?? ''
      } else {
        av = (a[sortKey] ?? '').toLowerCase()
        bv = (b[sortKey] ?? '').toLowerCase()
      }
      const cmp = av.localeCompare(bv, 'de')
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [contacts, sortKey, sortDir])

  const allSelected = contacts.length > 0 && selected.size === contacts.length

  function toggleAll() {
    setSelected(allSelected ? new Set() : new Set(contacts.map(c => c.id)))
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
    if (!confirm(`${selected.size} Kontakt${selected.size !== 1 ? 'e' : ''} löschen?`)) return
    setDeleting(true)
    try {
      await api.contacts.bulkDelete(isAll ? [] : [...selected], isAll)
      await load()
    } finally {
      setDeleting(false)
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
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Name, E-Mail oder Firma…"
            className="w-full rounded-lg border border-gray-200 pl-9 pr-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>

        {selected.size >= 2 && (
          <button
            onClick={() => setShowMerge(true)}
            className="flex items-center gap-1.5 rounded-lg bg-violet-50 border border-violet-200 px-3 py-1.5 text-sm font-medium text-violet-700 hover:bg-violet-100 transition-colors"
          >
            <GitMerge className="h-3.5 w-3.5" />
            Mergen ({selected.size})
          </button>
        )}
        {selected.size > 0 && (
          <button
            onClick={deleteSelected}
            disabled={deleting}
            className="flex items-center gap-1.5 rounded-lg bg-red-50 border border-red-200 px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-100 disabled:opacity-50 transition-colors"
          >
            <Trash2 className="h-3.5 w-3.5" />
            {deleting ? 'Löschen…' : `${selected.size} löschen`}
          </button>
        )}
      </div>

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
              <Th k="name" label="Name" />
              <Th k="firma" label="Firma" />
              <Th k="typ" label="Typ" className="w-28" />
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Kontakt</th>
              <Th k="letzter_kontakt" label="Letzter Kontakt" className="w-36" />
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Bewerbung</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {loading && (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-gray-400">Laden…</td>
              </tr>
            )}
            {!loading && sorted.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-gray-400 italic">Keine Kontakte gefunden</td>
              </tr>
            )}
            {sorted.map(c => (
              <tr
                key={c.id}
                className={clsx('transition-colors', selected.has(c.id) ? 'bg-indigo-50' : 'hover:bg-gray-50')}
              >
                <td className="pl-4 pr-2 py-3 w-8">
                  <input
                    type="checkbox"
                    checked={selected.has(c.id)}
                    onChange={() => toggleOne(c.id)}
                    className="rounded border-gray-300 text-indigo-600 cursor-pointer"
                  />
                </td>
                <td className="px-4 py-3">
                  <p className="font-medium text-gray-900">{c.name}</p>
                  {c.rolle && <p className="text-xs text-gray-500">{c.rolle}</p>}
                </td>
                <td className="px-4 py-3">
                  {c.firma ? (
                    <div className="flex items-center gap-2">
                      <CompanyLogo name={c.firma} website={c.company_website} size="sm" />
                      {c.company_profile_id && onOpenCompany ? (
                        <button
                          onClick={e => { e.stopPropagation(); onOpenCompany(c.company_profile_id!) }}
                          className="text-sm text-gray-700 hover:text-indigo-600 hover:underline text-left"
                        >{c.firma}</button>
                      ) : (
                        <span className="text-sm text-gray-700">{c.firma}</span>
                      )}
                    </div>
                  ) : <span className="text-gray-300">—</span>}
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
                    {c.telefon && (
                      <a href={`tel:${c.telefon}`} className="flex items-center gap-1 text-xs text-gray-600 hover:text-indigo-600">
                        <Phone className="h-3 w-3 shrink-0" />
                        {c.telefon}
                      </a>
                    )}
                    {c.linkedin_url && (
                      <a href={c.linkedin_url} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-xs text-indigo-500 hover:underline">
                        <Linkedin className="h-3 w-3 shrink-0" />
                        LinkedIn
                      </a>
                    )}
                    {!c.email && !c.telefon && !c.linkedin_url && (
                      <span className="text-xs text-gray-300">—</span>
                    )}
                  </div>
                </td>
                <td className="px-4 py-3 text-xs text-gray-500 whitespace-nowrap">
                  {c.letzter_kontakt
                    ? new Date(c.letzter_kontakt).toLocaleDateString('de-DE')
                    : <span className="text-gray-300">—</span>}
                </td>
                <td className="px-4 py-3">
                  {c.applications && c.applications.length > 0 ? (
                    <div className="flex flex-col gap-1">
                      {c.applications.map(a => (
                        <button
                          key={a.id}
                          onClick={() => onOpenApplication(a.id)}
                          className="text-left hover:text-indigo-600 transition-colors"
                        >
                          <p className="font-medium text-gray-800 hover:text-indigo-600 leading-tight">{a.firma}</p>
                          <p className="text-xs text-gray-500 truncate max-w-[160px]">{a.rolle}</p>
                        </button>
                      ))}
                    </div>
                  ) : (
                    <span className="text-xs text-gray-300">Kein Bezug</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!loading && contacts.length > 0 && (
          <div className="border-t border-gray-100 bg-gray-50 px-4 py-2 text-xs text-gray-400 flex items-center justify-between">
            <span>{contacts.length} {contacts.length === 1 ? 'Kontakt' : 'Kontakte'}</span>
            {selected.size > 0 && (
              <span className="text-indigo-600 font-medium">{selected.size} ausgewählt</span>
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
    </div>
  )
}
