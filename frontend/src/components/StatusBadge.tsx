import { MAIN_STATUS_COLORS, type MainStatus } from '../types'
import { useStatusLabels } from '../i18n/statusLabels'
import clsx from 'clsx'

interface Props {
  status: MainStatus
  subStatus?: string
  size?: 'sm' | 'md'
}

export function StatusBadge({ status, subStatus, size = 'md' }: Props) {
  const { mainStatusLabel, subStatusLabel } = useStatusLabels()
  const label = subStatus ? subStatusLabel(subStatus) : mainStatusLabel(status)

  return (
    <span
      data-testid={`status-badge-${status}`}
      className={clsx(
        'inline-flex items-center rounded-full font-medium',
        MAIN_STATUS_COLORS[status],
        size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-xs'
      )}
    >
      {label}
    </span>
  )
}
