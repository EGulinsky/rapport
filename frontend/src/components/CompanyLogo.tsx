import { useState } from 'react'
import clsx from 'clsx'

const COLORS = [
  'bg-indigo-100 text-indigo-700',
  'bg-blue-100 text-blue-700',
  'bg-emerald-100 text-emerald-700',
  'bg-amber-100 text-amber-700',
  'bg-rose-100 text-rose-700',
]

export function CompanyLogo({
  name,
  website,
  size = 'md',
}: {
  name: string
  website?: string | null
  size?: 'sm' | 'md'
}) {
  const [err, setErr] = useState(false)
  const domain = website
    ? (() => { try { return new URL(website).hostname.replace(/^www\./, '') } catch { return null } })()
    : null
  const initials = name.split(/\s+/).slice(0, 2).map(w => w[0]).join('').toUpperCase()
  const color = COLORS[name.charCodeAt(0) % COLORS.length]
  const cls = size === 'sm' ? 'h-6 w-6 text-[10px]' : 'h-8 w-8 text-xs'

  if (domain && !err) {
    return (
      <img
        src={`https://www.google.com/s2/favicons?domain=${domain}&sz=64`}
        alt={name}
        onError={() => setErr(true)}
        className={clsx(cls, 'rounded object-contain bg-white border border-gray-100 p-0.5 shrink-0')}
      />
    )
  }
  return (
    <div className={clsx(cls, 'rounded flex items-center justify-center font-bold shrink-0', color)}>
      {initials || '?'}
    </div>
  )
}
