/** Pure locale-aware date/collation helpers — usable both inside components
 * (via useLocale()) and inside plain helper functions (sort comparators, etc.)
 * that aren't components themselves. Replaces hardcoded 'de-DE'/'de' call sites. */

export function formatDate(date: string | Date, locale: string, opts?: Intl.DateTimeFormatOptions): string {
  const d = typeof date === 'string' ? new Date(date) : date
  return d.toLocaleDateString(locale, opts)
}

export function formatDateTime(date: string | Date, locale: string, opts?: Intl.DateTimeFormatOptions): string {
  const d = typeof date === 'string' ? new Date(date) : date
  return d.toLocaleString(locale, opts)
}

export function collate(a: string, b: string, locale: string): number {
  return a.localeCompare(b, locale)
}
