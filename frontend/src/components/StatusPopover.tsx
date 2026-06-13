import { useEffect, useRef } from 'react'
import { MAIN_PIPELINE, MAIN_STATUS_LABELS, MAIN_STATUS_COLORS, SUB_STATUS_LABELS, SUB_STATUS_SEQUENCE, type MainStatus } from '../types'
import clsx from 'clsx'

interface Props {
  currentMain: MainStatus
  currentSub?: string
  onSelect: (main: MainStatus, sub?: string) => void
  onClose: () => void
}

export function StatusPopover({ currentMain, currentSub, onSelect, onClose }: Props) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose()
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [onClose])

  const allStatuses: MainStatus[] = [...MAIN_PIPELINE, 'rejected']

  return (
    <div
      ref={ref}
      className="absolute z-50 mt-1 w-56 rounded-xl border border-gray-200 bg-white shadow-lg p-2 space-y-1"
      onClick={e => e.stopPropagation()}
    >
      <div className="flex flex-wrap gap-1 pb-1 border-b border-gray-100">
        {allStatuses.map(s => (
          <button
            key={s}
            type="button"
            onClick={() => {
              if (s === 'hr' || s === 'fb') {
                onSelect(s, currentMain === s ? currentSub : '1_scheduled')
              } else {
                onSelect(s, undefined)
              }
              if (s !== 'hr' && s !== 'fb') onClose()
            }}
            className={clsx(
              'text-xs px-2 py-0.5 rounded-full border transition-all',
              currentMain === s
                ? `${MAIN_STATUS_COLORS[s]} border-transparent font-medium`
                : 'border-gray-200 text-gray-600 hover:border-gray-300'
            )}
          >
            {MAIN_STATUS_LABELS[s]}
          </button>
        ))}
      </div>
      {(currentMain === 'hr' || currentMain === 'fb') && (
        <div className="flex flex-wrap gap-1 pt-1">
          {SUB_STATUS_SEQUENCE.map(sub => (
            <button
              key={sub}
              type="button"
              onClick={() => { onSelect(currentMain, sub); onClose() }}
              className={clsx(
                'text-xs px-2 py-0.5 rounded-full border transition-all',
                currentSub === sub
                  ? 'bg-indigo-100 text-indigo-800 border-indigo-300 font-medium'
                  : 'border-gray-200 text-gray-500 hover:border-gray-300'
              )}
            >
              {SUB_STATUS_LABELS[sub]}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
