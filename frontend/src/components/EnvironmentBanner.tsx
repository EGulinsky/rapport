import { AlertOctagon } from 'lucide-react'

export function EnvironmentBanner() {
  const label = import.meta.env.VITE_ENV_LABEL
  if (!label) return null

  return (
    <div className="bg-red-600 text-white text-xs font-semibold tracking-wide">
      <div className="flex items-center justify-center gap-1.5 px-4 py-1.5">
        <AlertOctagon className="h-3.5 w-3.5" />
        {label}
      </div>
    </div>
  )
}
