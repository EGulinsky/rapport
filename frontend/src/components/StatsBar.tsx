import type { Stats } from '../types'
import { Briefcase, XCircle, TrendingUp } from 'lucide-react'
import { useTranslation } from 'react-i18next'

interface Props {
  stats: Stats
}

export function StatsBar({ stats }: Props) {
  const { t } = useTranslation('app')
  const tiles = [
    { label: t('stats.total'),    value: stats.total,    icon: Briefcase,  color: 'text-gray-700 bg-white' },
    { label: t('stats.active'),   value: stats.active,   icon: TrendingUp, color: 'text-indigo-700 bg-indigo-50' },
    { label: t('stats.rejected'), value: stats.rejected, icon: XCircle,    color: 'text-red-700 bg-red-50' },
  ]

  return (
    <div className="grid grid-cols-3 gap-3" data-testid="stats-bar">
      {tiles.map(({ label, value, icon: Icon, color }) => (
        <div key={label} className={`rounded-xl px-4 py-3 flex items-center gap-3 border border-gray-100 shadow-sm ${color}`}>
          <Icon className="h-5 w-5 shrink-0 opacity-80" />
          <div>
            <p className="text-xl font-bold leading-none">{value}</p>
            <p className="text-xs opacity-70 mt-0.5">{label}</p>
          </div>
        </div>
      ))}
    </div>
  )
}
