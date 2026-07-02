import { useState, useEffect, useRef } from 'react'
import { Search, Building2 } from 'lucide-react'
import { api } from '../api/client'
import type { CompanyProfile } from '../types'

interface Props {
  value: string
  onChange: (v: string) => void
  placeholder?: string
  containerClassName?: string
  inputClassName?: string
}

export function CompanySearchInput({ value, onChange, placeholder, containerClassName, inputClassName }: Props) {
  const [open, setOpen] = useState(false)
  const [suggestions, setSuggestions] = useState<CompanyProfile[]>([])
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!value.trim()) { setSuggestions([]); return }
    const t = setTimeout(async () => {
      const results = await api.companies.list({ search: value }).catch(() => [])
      setSuggestions(results.slice(0, 8))
    }, 200)
    return () => clearTimeout(t)
  }, [value])

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  return (
    <div className={containerClassName ?? 'relative flex-1'} ref={ref}>
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
      <input
        value={value}
        onChange={e => { onChange(e.target.value); setOpen(true) }}
        onFocus={() => setOpen(true)}
        placeholder={placeholder}
        className={inputClassName ?? 'w-full rounded-lg border border-gray-200 pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white'}
      />
      {open && value.trim() && suggestions.length > 0 && (
        <div className="absolute z-50 top-full left-0 mt-1 w-full max-w-xs bg-white border border-gray-200 rounded-lg shadow-lg py-1 max-h-56 overflow-y-auto">
          {suggestions.map(c => (
            <button
              key={c.id}
              onClick={() => { onChange(c.name_display ?? c.name_norm); setOpen(false) }}
              className="w-full text-left px-3 py-1.5 text-xs hover:bg-indigo-50 hover:text-indigo-700 flex items-center gap-1.5"
            >
              <Building2 className="h-3 w-3 text-gray-400 shrink-0" />
              <span className="truncate">{c.name_display ?? c.name_norm}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
