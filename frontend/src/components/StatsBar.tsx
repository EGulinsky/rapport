import type { Stats } from '../types'
import { Briefcase, CheckCircle, XCircle, TrendingUp } from 'lucide-react'

interface Props {
  stats: Stats
}

export function StatsBar({ stats }: Props) {
  const conversionRate = stats.total > 0
    ? Math.round(((stats.by_status['hr_done'] ?? 0) + (stats.by_status['interview_2'] ?? 0) + (stats.by_status['fb_scheduled'] ?? 0) + (stats.by_status['interview_3'] ?? 0) + (stats.by_status['fb_2'] ?? 0) + (stats.by_status['final_decision'] ?? 0) + (stats.by_status['offer'] ?? 0)) / stats.total * 100)
    : 0

  const tiles = [
    { label: 'Gesamt',   value: stats.total,    icon: Briefcase,    color: 'text-gray-700 bg-white' },
    { label: 'Aktiv',    value: stats.active,   icon: TrendingUp,   color: 'text-indigo-700 bg-indigo-50' },
    { label: 'Abgesagt', value: stats.rejected, icon: XCircle,      color: 'text-red-700 bg-red-50' },
    { label: 'Interview-Rate', value: `${conversionRate}%`, icon: CheckCircle, color: 'text-green-700 bg-green-50' },
  ]

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
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
