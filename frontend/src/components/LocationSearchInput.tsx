import { useState, useEffect, useRef } from 'react'
import { MapPin } from 'lucide-react'
import { api } from '../api/client'

interface Props {
  value: string
  onChange: (v: string) => void
  placeholder?: string
  className?: string
}

export function LocationSearchInput({ value, onChange, placeholder = 'Ort…', className }: Props) {
  const [open, setOpen] = useState(false)
  const [suggestions, setSuggestions] = useState<{ label: string }[]>([])
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!value.trim() || value.trim().length < 2) { setSuggestions([]); return }
    const t = setTimeout(async () => {
      const results = await api.geo.search(value.trim()).catch(() => [])
      setSuggestions(results)
    }, 300)
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
    <div className={className ?? 'relative'} ref={ref}>
      <input
        value={value}
        onChange={e => { onChange(e.target.value); setOpen(true) }}
        onFocus={() => setOpen(true)}
        placeholder={placeholder}
        className="w-full rounded-lg border border-gray-200 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
      />
      {open && value.trim() && suggestions.length > 0 && (
        <div className="absolute z-50 top-full left-0 mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg py-1 max-h-56 overflow-y-auto">
          {suggestions.map((s, i) => (
            <button
              key={i}
              type="button"
              onClick={() => { onChange(s.label); setOpen(false) }}
              className="w-full text-left px-3 py-1.5 text-xs hover:bg-indigo-50 hover:text-indigo-700 flex items-center gap-1.5"
            >
              <MapPin className="h-3 w-3 text-gray-400 shrink-0" />
              <span className="truncate">{s.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
