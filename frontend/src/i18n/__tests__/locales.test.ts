import { describe, it, expect } from 'vitest'
import { SUPPORTED_LANGUAGES } from '..'

// Loads every locale JSON file so this test needs no manual updates as new
// namespaces are added in later i18n phases — it just discovers whatever exists.
const modules = import.meta.glob<Record<string, unknown>>('../locales/*/*.json', { eager: true })

interface NamespaceEntry {
  lang: string
  namespace: string
  data: Record<string, unknown>
}

function parseEntries(): NamespaceEntry[] {
  return Object.entries(modules).map(([path, mod]) => {
    const match = path.match(/\.\.\/locales\/([^/]+)\/([^/]+)\.json$/)
    if (!match) throw new Error(`Unexpected locale file path: ${path}`)
    const [, lang, namespace] = match
    return { lang, namespace, data: (mod as { default: Record<string, unknown> }).default }
  })
}

function flatten(obj: Record<string, unknown>, prefix = ''): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [key, value] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${key}` : key
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      Object.assign(out, flatten(value as Record<string, unknown>, path))
    } else {
      out[path] = String(value)
    }
  }
  return out
}

function interpolationPlaceholders(value: string): string[] {
  return [...value.matchAll(/\{\{\s*([\w.]+)\s*\}\}/g)].map((m) => m[1]).sort()
}

describe('i18n locale catalogs', () => {
  const entries = parseEntries()
  const namespaces = [...new Set(entries.map((e) => e.namespace))]

  it('has at least one namespace to check', () => {
    expect(namespaces.length).toBeGreaterThan(0)
  })

  it('only contains supported languages', () => {
    const languages = new Set(entries.map((e) => e.lang))
    for (const lang of languages) {
      expect(SUPPORTED_LANGUAGES).toContain(lang)
    }
  })

  for (const namespace of namespaces) {
    describe(`namespace: ${namespace}`, () => {
      const byLang = new Map(entries.filter((e) => e.namespace === namespace).map((e) => [e.lang, flatten(e.data)]))

      it('is present for every supported language', () => {
        for (const lang of SUPPORTED_LANGUAGES) {
          expect(byLang.has(lang), `missing ${namespace}.json for '${lang}'`).toBe(true)
        }
      })

      it('has identical keys across all languages', () => {
        const [first, ...rest] = SUPPORTED_LANGUAGES
        const referenceKeys = Object.keys(byLang.get(first) ?? {}).sort()
        for (const lang of rest) {
          const keys = Object.keys(byLang.get(lang) ?? {}).sort()
          expect(keys, `key mismatch in ${namespace} for '${lang}' vs '${first}'`).toEqual(referenceKeys)
        }
      })

      it('has no empty string values', () => {
        for (const [lang, flat] of byLang) {
          for (const [key, value] of Object.entries(flat)) {
            expect(value.trim(), `${namespace}.${key} is empty for '${lang}'`).not.toBe('')
          }
        }
      })

      it('has matching interpolation placeholders across languages for the same key', () => {
        const [first, ...rest] = SUPPORTED_LANGUAGES
        const referenceFlat = byLang.get(first) ?? {}
        for (const lang of rest) {
          const flat = byLang.get(lang) ?? {}
          for (const key of Object.keys(referenceFlat)) {
            const refPlaceholders = interpolationPlaceholders(referenceFlat[key])
            const langPlaceholders = interpolationPlaceholders(flat[key] ?? '')
            expect(langPlaceholders, `placeholder mismatch in ${namespace}.${key} for '${lang}'`).toEqual(refPlaceholders)
          }
        }
      })
    })
  }
})
