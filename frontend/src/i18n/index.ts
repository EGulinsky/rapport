import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import commonDe from './locales/de/common.json'
import commonEn from './locales/en/common.json'
import errorsDe from './locales/de/errors.json'
import errorsEn from './locales/en/errors.json'
import authDe from './locales/de/auth.json'
import authEn from './locales/en/auth.json'
import statusDe from './locales/de/status.json'
import statusEn from './locales/en/status.json'
import appDe from './locales/de/app.json'
import appEn from './locales/en/app.json'
import companiesDe from './locales/de/companies.json'
import companiesEn from './locales/en/companies.json'
import contactsDe from './locales/de/contacts.json'
import contactsEn from './locales/en/contacts.json'
import mergeDe from './locales/de/merge.json'
import mergeEn from './locales/en/merge.json'
import calendarDe from './locales/de/calendar.json'
import calendarEn from './locales/en/calendar.json'
import analyticsDe from './locales/de/analytics.json'
import analyticsEn from './locales/en/analytics.json'
import cleanupDe from './locales/de/cleanup.json'
import cleanupEn from './locales/en/cleanup.json'
import reviewDe from './locales/de/review.json'
import reviewEn from './locales/en/review.json'
import applicationsDe from './locales/de/applications.json'
import applicationsEn from './locales/en/applications.json'
import settingsDe from './locales/de/settings.json'
import settingsEn from './locales/en/settings.json'
import auditLogDe from './locales/de/auditLog.json'
import auditLogEn from './locales/en/auditLog.json'

export const SUPPORTED_LANGUAGES = ['de', 'en'] as const
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number]

/** Native-script display names for the language picker (register form, Settings). */
export const LANGUAGE_NAMES: Record<SupportedLanguage, string> = { de: 'Deutsch', en: 'English' }

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
    de: { common: commonDe, errors: errorsDe, auth: authDe, status: statusDe, app: appDe, companies: companiesDe, contacts: contactsDe, merge: mergeDe, calendar: calendarDe, analytics: analyticsDe, cleanup: cleanupDe, review: reviewDe, applications: applicationsDe, settings: settingsDe, auditLog: auditLogDe },
    en: { common: commonEn, errors: errorsEn, auth: authEn, status: statusEn, app: appEn, companies: companiesEn, contacts: contactsEn, merge: mergeEn, calendar: calendarEn, analytics: analyticsEn, cleanup: cleanupEn, review: reviewEn, applications: applicationsEn, settings: settingsEn, auditLog: auditLogEn },
  },
  lng: getPreLoginLanguage(),
  fallbackLng: 'en',
  defaultNS: 'common',
  interpolation: { escapeValue: false }, // React already escapes
})

export default i18n
