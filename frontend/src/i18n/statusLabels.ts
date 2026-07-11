import { useTranslation } from 'react-i18next'
import i18n from './index'

/** Non-hook variant for standalone helper functions that aren't components
 * (e.g. MergeDialog's displayValue) — reads the current language directly
 * from the i18n singleton. Falls back to the raw code, matching the old
 * `MAIN_STATUS_LABELS[x] ?? x` / `SUB_STATUS_LABELS[x] ?? x` pattern. */
export function mainStatusLabel(status: string): string {
  return i18n.t(status, { ns: 'status', defaultValue: status })
}

export function subStatusLabel(status: string): string {
  return i18n.t(status, { ns: 'status', defaultValue: status })
}

/** Hook variant for use inside component render bodies — subscribes to
 * language changes so the component re-renders when the user switches UI language. */
export function useStatusLabels() {
  const { t } = useTranslation('status')
  return {
    mainStatusLabel: (status: string) => t(status, { defaultValue: status }),
    subStatusLabel: (status: string) => t(status, { defaultValue: status }),
  }
}
