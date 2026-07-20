// Shared by ApplicationModal.tsx (Salary tab) and KanbanBoard.tsx (card
// summary) -- falls back to EUR so older rows with salary_currency = NULL
// (pre-v4.5.2) still show a labeled currency instead of a bare number.
export function formatCurrencyAmount(value: number, currency: string | null | undefined, locale: string): string {
  const fmt = new Intl.NumberFormat(locale, { style: 'currency', currency: currency || 'EUR', maximumFractionDigits: 0 })
  return fmt.format(value)
}

export function formatSalaryRange(min: number | null | undefined, max: number | null | undefined, currency: string | null | undefined, locale: string): string | null {
  if (min == null) return null
  return max == null
    ? formatCurrencyAmount(min, currency, locale)
    : `${formatCurrencyAmount(min, currency, locale)} – ${formatCurrencyAmount(max, currency, locale)}`
}
