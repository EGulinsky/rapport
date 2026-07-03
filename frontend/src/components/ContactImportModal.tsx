import { useState } from 'react'
import { X, Check, Search, Linkedin as LinkedinIcon, Cloud } from 'lucide-react'
import { api } from '../api/client'
import type { ICloudContactCandidate, LinkedInPeopleCandidate } from '../types'
import clsx from 'clsx'

type Candidate = ICloudContactCandidate | LinkedInPeopleCandidate

interface Props {
  source: 'icloud' | 'linkedin'
  onClose: () => void
  onImported: () => void
}

function candidateKey(source: 'icloud' | 'linkedin', c: Candidate): string {
  if (source === 'icloud') return (c as ICloudContactCandidate).email ?? c.name
  return (c as LinkedInPeopleCandidate).profile_url
}

function candidateSubtitle(source: 'icloud' | 'linkedin', c: Candidate): string {
  if (source === 'icloud') {
    const ic = c as ICloudContactCandidate
    return [ic.rolle, ic.firma].filter(Boolean).join(' bei ') || ic.email || ''
  }
  return (c as LinkedInPeopleCandidate).headline ?? ''
}

const META = {
  icloud: { title: 'Aus iCloud importieren', icon: Cloud, placeholder: 'Name, E-Mail oder Firma…', color: 'sky' },
  linkedin: { title: 'Aus LinkedIn importieren', icon: LinkedinIcon, placeholder: 'Name suchen…', color: 'blue' },
} as const

export function ContactImportModal({ source, onClose, onImported }: Props) {
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [searched, setSearched] = useState(false)
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [error, setError] = useState<string | null>(null)
  const [importing, setImporting] = useState(false)
  const [result, setResult] = useState<{ imported: number; skipped: number } | null>(null)

  const meta = META[source]
  const Icon = meta.icon

  async function runSearch() {
    if (query.trim().length < 2) return
    setLoading(true)
    setError(null)
    setSearched(true)
    setSelected(new Set())
    setResult(null)
    try {
      const res = source === 'icloud'
        ? await api.contacts.searchICloud(query.trim())
        : await api.contacts.searchLinkedIn(query.trim())
      setCandidates(res)
    } catch (e) {
      setCandidates([])
      setError(e instanceof Error ? e.message.replace(/^\d+:\s*/, '') : String(e))
    } finally {
      setLoading(false)
    }
  }

  function toggle(c: Candidate) {
    const key = candidateKey(source, c)
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  async function doImport() {
    const picked = candidates.filter(c => selected.has(candidateKey(source, c)))
    if (picked.length === 0) return
    setImporting(true)
    setError(null)
    try {
      const res = source === 'icloud'
        ? await api.contacts.importFromICloud(picked as ICloudContactCandidate[])
        : await api.contacts.importFromLinkedIn(picked as LinkedInPeopleCandidate[])
      setResult(res)
      setCandidates(prev => prev.filter(c => !selected.has(candidateKey(source, c))))
      setSelected(new Set())
      onImported()
    } catch (e) {
      setError(e instanceof Error ? e.message.replace(/^\d+:\s*/, '') : String(e))
    } finally {
      setImporting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <div className="w-full max-w-lg rounded-2xl bg-white shadow-2xl flex flex-col max-h-[85vh]">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <Icon className="h-4 w-4 text-gray-400" />
            <h2 className="text-base font-semibold text-gray-900">{meta.title}</h2>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="px-5 py-3 border-b border-gray-100 flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-gray-400" />
            <input
              autoFocus
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && runSearch()}
              placeholder={meta.placeholder}
              className="w-full rounded-lg border border-gray-200 pl-8 pr-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <button
            onClick={runSearch}
            disabled={query.trim().length < 2 || loading}
            className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {loading ? 'Suche…' : 'Suchen'}
          </button>
        </div>

        <div className="overflow-y-auto flex-1 px-5 py-3 space-y-2">
          {error && (
            <p className="text-xs text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2">{error}</p>
          )}
          {result && (
            <p className="text-xs text-green-700 bg-green-50 border border-green-100 rounded-lg px-3 py-2">
              {result.imported} importiert{result.skipped > 0 ? `, ${result.skipped} übersprungen (bereits vorhanden)` : ''}
            </p>
          )}
          {!loading && searched && candidates.length === 0 && !error && (
            <p className="text-sm text-gray-400 text-center py-6">Keine Treffer</p>
          )}
          {!searched && !loading && (
            <p className="text-sm text-gray-400 text-center py-6">
              {source === 'icloud'
                ? 'Durchsucht dein gesamtes iCloud-Adressbuch, nicht nur bereits verknüpfte Kontakte.'
                : 'Sucht LinkedIn-Personen nach Namen (benötigt eine gültige LinkedIn-Session). Firma wird aus der Kurzbeschreibung erkannt — bei individuell angepassten Beschreibungen ohne Firmenerwähnung bleibt sie leer und muss ggf. nach dem Import ergänzt werden.'}
            </p>
          )}
          {candidates.map(c => {
            const key = candidateKey(source, c)
            const subtitle = candidateSubtitle(source, c)
            const alreadyImported = source === 'icloud' && (c as ICloudContactCandidate).already_imported
            return (
              <label
                key={key}
                className={clsx(
                  'flex items-start gap-2.5 rounded-lg border p-2.5 transition-colors',
                  alreadyImported ? 'cursor-not-allowed opacity-60 border-gray-200' :
                    selected.has(key) ? 'cursor-pointer border-indigo-300 bg-indigo-50' : 'cursor-pointer border-gray-200 hover:bg-gray-50'
                )}
              >
                <input
                  type="checkbox"
                  className="mt-0.5 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500 shrink-0"
                  checked={selected.has(key)}
                  disabled={alreadyImported}
                  onChange={() => toggle(c)}
                />
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5">
                    <p className="text-sm font-medium text-gray-800 truncate">{c.name}</p>
                    {alreadyImported && (
                      <span className="shrink-0 text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-gray-100 text-gray-500">
                        bereits vorhanden
                      </span>
                    )}
                  </div>
                  {subtitle && <p className="text-xs text-gray-500 truncate">{subtitle}</p>}
                </div>
              </label>
            )
          })}
        </div>

        <div className="flex items-center justify-between px-5 py-3 border-t border-gray-100">
          <span className="text-xs text-gray-400">{selected.size > 0 ? `${selected.size} ausgewählt` : ''}</span>
          <button
            onClick={doImport}
            disabled={selected.size === 0 || importing}
            className="flex items-center gap-1.5 rounded-lg bg-green-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
          >
            <Check className="h-3.5 w-3.5" />
            {importing ? 'Importiere…' : `${selected.size || ''} importieren`.trim()}
          </button>
        </div>
      </div>
    </div>
  )
}
