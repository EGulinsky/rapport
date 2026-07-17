import { Plus, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export interface PhoneEntry {
  number: string
  type: string
}

const PHONE_TYPES = ['mobile', 'home', 'work', 'main', 'other']

interface Props {
  phones: PhoneEntry[]
  onChange: (phones: PhoneEntry[]) => void
}

export function PhoneListEditor({ phones, onChange }: Props) {
  const { t } = useTranslation('contacts')

  function update(index: number, patch: Partial<PhoneEntry>) {
    onChange(phones.map((p, i) => (i === index ? { ...p, ...patch } : p)))
  }

  function remove(index: number) {
    onChange(phones.filter((_, i) => i !== index))
  }

  function add() {
    onChange([...phones, { number: '', type: 'mobile' }])
  }

  return (
    <div className="space-y-1.5">
      {phones.map((p, i) => (
        <div key={i} className="flex items-center gap-1.5">
          <select
            value={p.type}
            onChange={e => update(i, { type: e.target.value })}
            className="rounded-lg border border-gray-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white shrink-0"
          >
            {PHONE_TYPES.map(pt => (
              <option key={pt} value={pt}>{t(`phoneTypes.${pt}`)}</option>
            ))}
          </select>
          <input
            value={p.number}
            onChange={e => update(i, { number: e.target.value })}
            placeholder={t('contactModal.phonePlaceholder')}
            className="flex-1 min-w-0 rounded-lg border border-gray-200 px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
          <button
            type="button"
            onClick={() => remove(i)}
            className="p-1.5 rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors shrink-0"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={add}
        className="flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-700 px-1 py-1"
      >
        <Plus className="h-3 w-3" />
        {t('contactModal.addPhone')}
      </button>
    </div>
  )
}
