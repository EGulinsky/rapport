import { useState } from 'react'
import clsx from 'clsx'
import { useLogoKey } from '../context/LogoContext'

const COLORS = [
  'bg-indigo-100 text-indigo-700',
  'bg-blue-100 text-blue-700',
  'bg-emerald-100 text-emerald-700',
  'bg-amber-100 text-amber-700',
  'bg-rose-100 text-rose-700',
]

function getDomain(website?: string | null): string | null {
  if (!website) return null
  try { return new URL(website).hostname.replace(/^www\./, '') } catch { return null }
}

export function CompanyLogo({
  name,
  website,
  size = 'md',
  logoData,
}: {
  name: string
  website?: string | null
  size?: 'sm' | 'md'
  logoData?: string | null
}) {
  const { logoDevKey } = useLogoKey()
  const [logoDevErr, setLogoDevErr] = useState(false)
  const [faviconErr, setFaviconErr] = useState(false)

  const domain = getDomain(website)
  const initials = name.split(/\s+/).slice(0, 2).map(w => w[0]).join('').toUpperCase()
  const color = COLORS[name.charCodeAt(0) % COLORS.length]
  const cls = size === 'sm' ? 'h-6 w-6 text-[10px]' : 'h-8 w-8 text-xs'

  if (logoData) {
    return (
      <img
        src={logoData}
        alt={name}
        className={clsx(cls, 'rounded object-contain bg-white border border-gray-100 p-0.5 shrink-0')}
      />
    )
  }

  if (domain && logoDevKey && !logoDevErr) {
    return (
      <img
        src={`https://img.logo.dev/${domain}?token=${logoDevKey}&size=64&format=png`}
        alt={name}
        onError={() => setLogoDevErr(true)}
        className={clsx(cls, 'rounded object-contain bg-white border border-gray-100 p-0.5 shrink-0')}
      />
    )
  }

  if (domain && !faviconErr) {
    return (
      <img
        src={`https://www.google.com/s2/favicons?domain=${domain}&sz=64`}
        alt={name}
        onError={() => setFaviconErr(true)}
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
