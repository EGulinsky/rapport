import { MAIN_STATUS_LABELS, MAIN_STATUS_COLORS, SUB_STATUS_LABELS, type MainStatus } from '../types'
import clsx from 'clsx'

interface Props {
  status: MainStatus
  subStatus?: string
  size?: 'sm' | 'md'
}

export function StatusBadge({ status, subStatus, size = 'md' }: Props) {
  const label = subStatus
    ? SUB_STATUS_LABELS[subStatus] ?? subStatus
    : MAIN_STATUS_LABELS[status]

  return (
    <span
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
