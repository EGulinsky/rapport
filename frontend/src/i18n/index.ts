import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import commonDe from './locales/de/common.json'
import commonEn from './locales/en/common.json'
import errorsDe from './locales/de/errors.json'
import errorsEn from './locales/en/errors.json'
import authDe from './locales/de/auth.json'
import authEn from './locales/en/auth.json'

export const SUPPORTED_LANGUAGES = ['de', 'en'] as const
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number]

const LANGUAGE_PREF_KEY = 'rapport_ui_language_pref'

/** Language shown before login (no user object yet): a remembered prior choice
 * (e.g. bounced back to /login after registering), otherwise 'en' — the new
 * global default. Existing users keep their server-stored 'de'/'en' once logged in. */
export function getPreLoginLanguage(): SupportedLanguage {
  const stored = localStorage.getItem(LANGUAGE_PREF_KEY)
  return stored === 'de' || stored === 'en' ? stored : 'en'
}

export function rememberPreLoginLanguage(lang: SupportedLanguage): void {
  localStorage.setItem(LANGUAGE_PREF_KEY, lang)
}

i18n.use(initReactI18next).init({
  resources: {
    de: { common: commonDe, errors: errorsDe, auth: authDe },
    en: { common: commonEn, errors: errorsEn, auth: authEn },
  },
  lng: getPreLoginLanguage(),
  fallbackLng: 'en',
  defaultNS: 'common',
  interpolation: { escapeValue: false }, // React already escapes
})

export default i18n
