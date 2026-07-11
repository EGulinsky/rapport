import { describe, it, expect } from 'vitest'
import { formatDate, formatDateTime, collate } from '../formatDate'

describe('formatDate', () => {
  it('formats a date string using the given locale', () => {
    expect(formatDate('2026-03-05', 'de-DE')).toBe('5.3.2026')
    expect(formatDate('2026-03-05', 'en-US')).toBe('3/5/2026')
  })

  it('accepts a Date object as well as a string', () => {
    expect(formatDate(new Date('2026-03-05'), 'de-DE')).toBe('5.3.2026')
  })

  it('supports Intl.DateTimeFormatOptions', () => {
    expect(formatDate('2026-03-05', 'de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })).toBe('05.03.2026')
  })
})

describe('formatDateTime', () => {
  it('includes time in the formatted output', () => {
    const result = formatDateTime('2026-03-05T14:30:00Z', 'de-DE', { hour: '2-digit', minute: '2-digit' })
    expect(result).toMatch(/\d{2}:\d{2}/)
  })
})

describe('collate', () => {
  it('sorts using locale-aware comparison', () => {
    // German collation treats 'ä' as close to 'a', unlike a plain code-point compare.
    const words = ['Zebra', 'Ärger', 'Apfel']
    const sorted = [...words].sort((a, b) => collate(a, b, 'de-DE'))
    expect(sorted).toEqual(['Apfel', 'Ärger', 'Zebra'])
  })

  it('returns 0 for equal strings', () => {
    expect(collate('foo', 'foo', 'en-US')).toBe(0)
  })
})
