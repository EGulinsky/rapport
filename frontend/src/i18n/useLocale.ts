import { useTranslation } from 'react-i18next'

/** BCP-47 tag for Intl/date APIs, one switch statement — the single place a
 * newly supported language registers its date-locale mapping. */
export function localeTagFor(language: string): string {
  switch (language) {
    case 'de':
      return 'de-DE'
    default:
      return 'en-US'
  }
}

/** Current UI language as a BCP-47 tag, for Intl.DateTimeFormat/toLocaleDateString/localeCompare. */
export function useLocale(): string {
  const { i18n } = useTranslation()
  return localeTagFor(i18n.language)
}
