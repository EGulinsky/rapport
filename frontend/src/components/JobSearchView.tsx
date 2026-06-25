import { useState, useRef, useEffect } from 'react'
import { Search, MapPin, ExternalLink, Check, Loader2, AlertCircle, Plus, ChevronRight } from 'lucide-react'
import { api } from '../api/client'
import type { JobResult, LinkPortal, JobPortal } from '../types'
import clsx from 'clsx'

interface Props {
  onImported?: () => void
}

function SourceBadge({ source, color }: { source: string; color?: string }) {
  const bg = color ? undefined : '#6b7280'
  return (
    <span
      className="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold text-white"
      style={{ backgroundColor: color || bg }}
    >
      {source}
    </span>
  )
}

function JobCard({
  job,
  selected,
  active,
  onToggle,
  onActivate,
}: {
  job: JobResult
  selected: boolean
  active: boolean
  onToggle: () => void
  onActivate: () => void
}) {
  return (
    <div
      className={clsx(
        'flex items-start gap-3 rounded-xl border p-3 cursor-pointer transition-all',
        active
          ? 'border-indigo-300 bg-indigo-50/60 shadow-sm'
          : 'border-gray-200 bg-white hover:border-gray-300 hover:shadow-sm',
      )}
      onClick={onActivate}
    >
      <input
        type="checkbox"
        checked={selected}
        onChange={e => { e.stopPropagation(); onToggle() }}
        onClick={e => e.stopPropagation()}
        className="mt-0.5 h-4 w-4 rounded border-gray-300 text-indigo-600 cursor-pointer shrink-0"
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-start gap-2 flex-wrap">
          <SourceBadge source={job.source === 'linkedin' ? 'LinkedIn' : job.source} color="#0a66c2" />
          {job.easy_apply && (
            <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold bg-green-100 text-green-700">
              Easy Apply
            </span>
          )}
        </div>
        <p className="mt-1 font-medium text-sm text-gray-900 leading-tight">{job.title || '—'}</p>
        <p className="text-xs text-gray-500 mt-0.5">{job.company || '—'}</p>
        {job.location && (
          <p className="text-[11px] text-gray-400 mt-0.5 flex items-center gap-1">
            <MapPin className="h-3 w-3" />{job.location}
          </p>
        )}
      </div>
      <ChevronRight className={clsx('h-4 w-4 shrink-0 mt-1 transition-colors', active ? 'text-indigo-400' : 'text-gray-300')} />
    </div>
  )
}

function DescriptionPanel({ job }: { job: JobResult }) {
  const [desc, setDesc] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const prevUrl = useRef<string>('')

  useEffect(() => {
    if (!job.url || job.url === prevUrl.current) return
    prevUrl.current = job.url
    setDesc(null)
    setError(null)
    setLoading(true)
    api.jobsearch.description(job.url)
      .then(r => setDesc(r.description || null))
      .catch(() => setError('Beschreibung konnte nicht geladen werden.'))
      .finally(() => setLoading(false))
  }, [job.url])

  return (
    <div className="h-full flex flex-col">
      <div className="p-4 border-b border-gray-100">
        <div className="flex items-center gap-2 flex-wrap mb-2">
          <SourceBadge source={job.source === 'linkedin' ? 'LinkedIn' : job.source} color="#0a66c2" />
          {job.easy_apply && (
            <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold bg-green-100 text-green-700">Easy Apply</span>
          )}
        </div>
        <h2 className="font-semibold text-gray-900 text-base leading-snug">{job.title}</h2>
        <p className="text-sm text-gray-600 mt-1">{job.company}</p>
        {job.location && (
          <p className="text-xs text-gray-400 mt-1 flex items-center gap-1">
            <MapPin className="h-3 w-3" />{job.location}
          </p>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-4 min-h-0">
        {loading && (
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <Loader2 className="h-4 w-4 animate-spin" />
            Stellenbeschreibung wird geladen…
          </div>
        )}
        {error && !loading && (
          <p className="text-sm text-amber-600 flex items-center gap-2">
            <AlertCircle className="h-4 w-4 shrink-0" />{error}
          </p>
        )}
        {desc && !loading && (
          <div
            className="prose prose-sm max-w-none text-gray-700 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_li]:my-0.5 [&_h1]:text-base [&_h2]:text-sm [&_h3]:text-sm [&_strong]:font-semibold [&_p]:my-1.5"
            dangerouslySetInnerHTML={{ __html: desc }}
          />
        )}
        {!loading && !desc && !error && (
          <p className="text-sm text-gray-400 italic">Beschreibung wird geladen…</p>
        )}
      </div>

      <div className="p-4 border-t border-gray-100 shrink-0">
        <a
          href={job.url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 w-full justify-center rounded-lg border border-indigo-200 bg-indigo-50 text-indigo-700 py-2 px-3 text-sm font-medium hover:bg-indigo-100 transition-colors"
        >
          <ExternalLink className="h-4 w-4" />
          Auf LinkedIn öffnen
        </a>
      </div>
    </div>
  )
}

// ── Portal config panel (shown in Settings via SettingsModal) ─────────────
export function JobPortalSettings() {
  const [portals, setPortals] = useState<JobPortal[]>([])
  const [loaded, setLoaded] = useState(false)
  const [adding, setAdding] = useState(false)
  const [newName, setNewName] = useState('')
  const [newUrl, setNewUrl] = useState('')
  const [newColor, setNewColor] = useState('#6b7280')

  async function load() {
    const data = await api.jobsearch.portals()
    setPortals(data)
    setLoaded(true)
  }

  if (!loaded) {
    load()
    return <div className="text-xs text-gray-400 py-2">Lade Portale…</div>
  }

  async function toggleEnabled(p: JobPortal) {
    await api.jobsearch.updatePortal(p.id, { enabled: !p.enabled })
    load()
  }

  async function deletePortal(p: JobPortal) {
    await api.jobsearch.deletePortal(p.id)
    load()
  }

  async function addPortal() {
    if (!newName.trim() || !newUrl.trim()) return
    await api.jobsearch.addPortal({ name: newName.trim(), url_template: newUrl.trim(), color: newColor })
    setNewName(''); setNewUrl(''); setNewColor('#6b7280'); setAdding(false)
    load()
  }

  return (
    <div className="space-y-3">
      <div className="space-y-2">
        {portals.map(p => (
          <div key={p.id} className="flex items-center gap-3 rounded-lg border border-gray-100 bg-gray-50 px-3 py-2">
            <span className="h-3 w-3 rounded-full shrink-0" style={{ backgroundColor: p.color || '#9ca3af' }} />
            <span className="flex-1 text-sm font-medium text-gray-800">{p.name}</span>
            {p.portal_type === 'link' && p.url_template && (
              <span className="text-[10px] text-gray-400 truncate max-w-[180px]">{p.url_template}</span>
            )}
            {p.portal_type === 'linkedin' && (
              <span className="text-[10px] text-indigo-500 font-medium">Integriert</span>
            )}
            <label className="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" className="sr-only peer" checked={p.enabled} onChange={() => toggleEnabled(p)} />
              <div className="w-9 h-5 bg-gray-200 peer-checked:bg-indigo-600 rounded-full transition-colors after:content-[''] after:absolute after:top-0.5 after:left-0.5 after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:after:translate-x-4" />
            </label>
            {!p.is_builtin && (
              <button onClick={() => deletePortal(p)} className="text-gray-300 hover:text-red-400 transition-colors text-xs">✕</button>
            )}
          </div>
        ))}
      </div>

      {adding ? (
        <div className="rounded-lg border border-gray-200 p-3 space-y-2">
          <input value={newName} onChange={e => setNewName(e.target.value)} placeholder="Name (z.B. Monster)" className="w-full text-sm rounded border border-gray-200 px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-500" />
          <input value={newUrl} onChange={e => setNewUrl(e.target.value)} placeholder="URL-Template mit {q} und {location}" className="w-full text-sm rounded border border-gray-200 px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-500" />
          <div className="flex items-center gap-2">
            <input type="color" value={newColor} onChange={e => setNewColor(e.target.value)} className="h-8 w-10 rounded border border-gray-200 cursor-pointer" />
            <button onClick={addPortal} className="flex-1 rounded bg-indigo-600 text-white text-xs font-medium py-1.5 hover:bg-indigo-700 transition-colors">Hinzufügen</button>
            <button onClick={() => setAdding(false)} className="text-xs text-gray-400 hover:text-gray-600 px-2">Abbrechen</button>
          </div>
        </div>
      ) : (
        <button onClick={() => setAdding(true)} className="flex items-center gap-1.5 text-xs text-indigo-600 hover:text-indigo-700 transition-colors font-medium">
          <Plus className="h-3.5 w-3.5" /> Jobportal hinzufügen
        </button>
      )}
    </div>
  )
}

// ── Main view ─────────────────────────────────────────────────────────────────

export function JobSearchView({ onImported }: Props) {
  const [query, setQuery] = useState('')
  const [location, setLocation] = useState('Deutschland')
  const [searching, setSearching] = useState(false)
  const [results, setResults] = useState<JobResult[]>([])
  const [linkPortals, setLinkPortals] = useState<LinkPortal[]>([])
  const [liError, setLiError] = useState<string | null>(null)
  const [searched, setSearched] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [activeJob, setActiveJob] = useState<JobResult | null>(null)
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState<{ created: number; skipped: number } | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  async function doSearch() {
    if (!query.trim()) return
    setSearching(true)
    setSearched(false)
    setResults([])
    setLinkPortals([])
    setLiError(null)
    setSelected(new Set())
    setActiveJob(null)
    setImportResult(null)
    try {
      const res = await api.jobsearch.search(query.trim(), location.trim() || 'Deutschland')
      setResults(res.results)
      setLinkPortals(res.portals)
      setLiError(res.linkedin_error || null)
      setSearched(true)
      if (res.results.length > 0) setActiveJob(res.results[0])
    } catch (e: unknown) {
      setLiError(e instanceof Error ? e.message : 'Suche fehlgeschlagen')
      setSearched(true)
    } finally {
      setSearching(false)
    }
  }

  function toggleSelect(id: string) {
    setSelected(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  function toggleAll() {
    if (selected.size === results.length) {
      setSelected(new Set())
    } else {
      setSelected(new Set(results.map(j => j.id)))
    }
  }

  async function doImport() {
    const jobs = results.filter(j => selected.has(j.id))
    if (!jobs.length) return
    setImporting(true)
    try {
      const res = await api.jobsearch.importJobs(jobs)
      setImportResult({ created: res.created, skipped: res.skipped })
      setSelected(new Set())
      onImported?.()
    } catch {
      // ignore
    } finally {
      setImporting(false)
    }
  }

  return (
    <div className="flex flex-col gap-5">
      {/* Search bar */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
        <div className="flex gap-3 flex-wrap sm:flex-nowrap">
          <div className="relative flex-1 min-w-0">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <input
              ref={inputRef}
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && doSearch()}
              placeholder="Stelle suchen, z.B. VP Engineering, Head of Product…"
              className="w-full rounded-lg border border-gray-200 pl-9 pr-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <div className="relative">
            <MapPin className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <input
              value={location}
              onChange={e => setLocation(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && doSearch()}
              placeholder="Ort / Region"
              className="w-48 rounded-lg border border-gray-200 pl-9 pr-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <button
            onClick={doSearch}
            disabled={searching || !query.trim()}
            className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shrink-0"
          >
            {searching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
            Suchen
          </button>
        </div>
      </div>

      {/* Other portals quick-links */}
      {linkPortals.length > 0 && (
        <div className="flex flex-wrap gap-2 items-center">
          <span className="text-xs text-gray-400 font-medium">Auch suchen auf:</span>
          {linkPortals.map(p => (
            <a
              key={p.id}
              href={p.url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium text-white hover:opacity-90 transition-opacity"
              style={{ backgroundColor: p.color || '#6b7280' }}
            >
              {p.name}
              <ExternalLink className="h-3 w-3" />
            </a>
          ))}
        </div>
      )}

      {/* LinkedIn error */}
      {liError && (
        <div className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <AlertCircle className="h-4 w-4 mt-0.5 shrink-0 text-amber-500" />
          <span>{liError}</span>
        </div>
      )}

      {/* Results */}
      {searched && results.length === 0 && !liError && (
        <p className="text-center text-sm text-gray-400 py-8">Keine LinkedIn-Ergebnisse gefunden.</p>
      )}

      {results.length > 0 && (
        <div className="flex gap-4 items-start">
          {/* Results list */}
          <div className="flex flex-col gap-2 w-80 shrink-0">
            {/* Select all + import bar */}
            <div className="flex items-center justify-between bg-white rounded-xl border border-gray-200 px-3 py-2">
              <label className="flex items-center gap-2 cursor-pointer text-xs text-gray-600">
                <input
                  type="checkbox"
                  checked={selected.size === results.length && results.length > 0}
                  onChange={toggleAll}
                  className="h-4 w-4 rounded border-gray-300 text-indigo-600"
                />
                {selected.size > 0 ? `${selected.size} ausgewählt` : `${results.length} Ergebnisse`}
              </label>
              {selected.size > 0 && (
                <button
                  onClick={doImport}
                  disabled={importing}
                  className="flex items-center gap-1.5 rounded-lg bg-indigo-600 text-white text-xs font-medium px-3 py-1.5 hover:bg-indigo-700 disabled:opacity-50 transition-colors"
                >
                  {importing
                    ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    : <Plus className="h-3.5 w-3.5" />}
                  Übernehmen
                </button>
              )}
            </div>

            {importResult && (
              <div className="flex items-center gap-2 rounded-lg bg-green-50 border border-green-200 px-3 py-2 text-xs text-green-700">
                <Check className="h-4 w-4 text-green-500" />
                {importResult.created} übernommen{importResult.skipped > 0 ? `, ${importResult.skipped} bereits vorhanden` : ''}
              </div>
            )}

            <div className="space-y-2 max-h-[calc(100vh-280px)] overflow-y-auto pr-1">
              {results.map(job => (
                <JobCard
                  key={job.id}
                  job={job}
                  selected={selected.has(job.id)}
                  active={activeJob?.id === job.id}
                  onToggle={() => toggleSelect(job.id)}
                  onActivate={() => setActiveJob(job)}
                />
              ))}
            </div>
          </div>

          {/* Description panel */}
          {activeJob && (
            <div className="flex-1 min-w-0 bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden sticky top-4" style={{ maxHeight: 'calc(100vh-220px)' }}>
              <DescriptionPanel job={activeJob} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}
