import { useState, useEffect, useRef } from 'react'
import { Building2, X, ChevronDown } from 'lucide-react'
import { api } from '../api/client'
import type { CompanyProfile } from '../types'

export interface CompanyFilter {
  id: number
  name: string
  subsidiaryIds?: number[]
}

interface Props {
  value: CompanyFilter | null
  onChange: (v: CompanyFilter | null) => void
  placeholder?: string
}

export function CompanyFilterPicker({ value, onChange, placeholder = 'Firma' }: Props) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<CompanyProfile[]>([])
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) { setQuery(''); return }
    const t = setTimeout(async () => {
      setResults(await api.companies.list({ search: query || undefined }))
    }, 200)
    return () => clearTimeout(t)
  }, [query, open])

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  if (value) {
    return (
      <div className="flex items-center gap-1 rounded-full bg-indigo-100 text-indigo-700 pl-2 pr-1 py-1 text-xs font-medium whitespace-nowrap">
        <Building2 className="h-3 w-3 shrink-0" />
        <span className="max-w-[140px] truncate">{value.name}</span>
        <button onClick={() => onChange(null)} className="ml-0.5 hover:text-indigo-900 shrink-0">
          <X className="h-3 w-3" />
        </button>
      </div>
    )
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-1 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs text-gray-500 hover:border-indigo-300 hover:text-indigo-600 transition-colors whitespace-nowrap"
      >
        <Building2 className="h-3.5 w-3.5" />
        {placeholder}
        <ChevronDown className="h-3 w-3 opacity-50" />
      </button>
      {open && (
        <div className="absolute z-50 top-full left-0 mt-1 w-64 bg-white border border-gray-200 rounded-lg shadow-lg">
          <div className="p-2 border-b border-gray-100">
            <input
              autoFocus
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Firma suchen…"
              className="w-full rounded border border-gray-200 px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>
          <div className="max-h-56 overflow-y-auto py-1">
            {results.length === 0 && <p className="text-xs text-gray-400 px-3 py-2 italic">Keine Treffer</p>}
            {results.slice(0, 15).map(c => (
              <button
                key={c.id}
                onClick={async () => {
                  const detail = await api.companies.get(c.id)
                  const subsidiaryIds = detail.subsidiaries?.map(s => s.id) ?? []
                  onChange({ id: c.id, name: c.name_display ?? c.name_norm, subsidiaryIds })
                  setOpen(false)
                }}
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
