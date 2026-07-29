import { useTranslation } from 'react-i18next'
import { Car } from 'lucide-react'

// Generic min/max + fixed/bonus breakdown + company-car editor, shared by
// ApplicationModal's Salary tab (expectation + budget slots) and the
// Account settings' salary expectation defaults section — same interaction
// rules in both places: a plain amount can be split into a fixed+bonus
// breakdown (kept in sync so the total always equals their sum), and a
// single amount can be expanded into a min/max range.
export interface SalarySlotValues {
  min?: number | null
  max?: number | null
  minFixed?: number | null
  minBonus?: number | null
  maxFixed?: number | null
  maxBonus?: number | null
  companyCar?: boolean | null
}

interface Props {
  value: SalarySlotValues
  onChange: (patch: Partial<SalarySlotValues>) => void
  label: string
  companyCarLabel: string
}

export function SalarySlotEditor({ value, onChange, label, companyCarLabel }: Props) {
  const { t } = useTranslation('applications')
  const { min, max, minFixed, minBonus, maxFixed, maxBonus, companyCar } = value
  const hasRange = max != null

  function renderAmountInput(which: 'min' | 'max') {
    const val = which === 'min' ? min : max
    const fixed = which === 'min' ? minFixed : maxFixed
    const bonus = which === 'min' ? minBonus : maxBonus
    const key = which
    const fixedKey = which === 'min' ? 'minFixed' : 'maxFixed'
    const bonusKey = which === 'min' ? 'minBonus' : 'maxBonus'
    const placeholder = which === 'min' ? t('salary.amountPlaceholder') : t('salary.amountMaxPlaceholder')
    const hasBreakdown = fixed != null || bonus != null

    return (
      <div className="flex items-center gap-2 flex-wrap">
        <input type="number" min={0} readOnly={hasBreakdown}
          className={`w-28 rounded-lg border px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 ${hasBreakdown ? 'bg-gray-50 text-gray-500 border-gray-200' : 'border-gray-200'}`}
          placeholder={placeholder}
          value={val ?? ''}
          onChange={hasBreakdown ? undefined : e => {
            const v = e.target.value === '' ? null : Number(e.target.value)
            onChange({ [key]: v })
          }}
        />
        {hasBreakdown ? (
          <>
            <span className="text-xs text-gray-400">=</span>
            <input type="number" min={0}
              className="w-24 rounded-lg border border-gray-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder={t('salary.fixed')}
              value={fixed ?? ''}
              onChange={e => {
                const v = e.target.value === '' ? null : Number(e.target.value)
                onChange({ [fixedKey]: v, [key]: (v ?? 0) + (bonus ?? 0) })
              }}
            />
            <span className="text-xs text-gray-400">+</span>
            <input type="number" min={0}
              className="w-24 rounded-lg border border-gray-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder={t('salary.bonus')}
              value={bonus ?? ''}
              onChange={e => {
                const v = e.target.value === '' ? null : Number(e.target.value)
                onChange({ [bonusKey]: v, [key]: (fixed ?? 0) + (v ?? 0) })
              }}
            />
            <button type="button" className="text-xs text-gray-400 hover:text-gray-600 underline whitespace-nowrap"
              onClick={() => onChange({ [fixedKey]: null, [bonusKey]: null })}>
              {t('salary.breakdownToggleOff')}
            </button>
          </>
        ) : (
          <button type="button" className="text-xs text-indigo-500 hover:text-indigo-700 whitespace-nowrap"
            disabled={val == null}
            onClick={() => onChange({ [fixedKey]: val ?? 0, [bonusKey]: 0 })}>
            {t('salary.breakdownToggleOn')}
          </button>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">{label}</p>
      <div className="flex items-center gap-3 flex-wrap">
        {renderAmountInput('min')}
        <label className="flex items-center gap-1.5 text-xs text-gray-500 cursor-pointer">
          <input type="checkbox" checked={hasRange}
            className="rounded border-gray-300 text-indigo-600"
            disabled={min == null}
            onChange={e => onChange({
              max: e.target.checked ? (min ?? 0) : null,
              ...(e.target.checked ? {} : { maxFixed: null, maxBonus: null }),
            })}
          />
          {t('salary.rangeToggle')}
        </label>
      </div>
      {hasRange && renderAmountInput('max')}
      <label className="flex items-center gap-1.5 text-xs text-gray-500 cursor-pointer pt-1">
        <input type="checkbox" checked={!!companyCar}
          className="rounded border-gray-300 text-indigo-600"
          onChange={e => onChange({ companyCar: e.target.checked })}
        />
        <Car className="h-3.5 w-3.5 text-gray-400" />
        {companyCarLabel}
      </label>
    </div>
  )
}
