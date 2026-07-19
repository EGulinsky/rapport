import { describe, it, expect } from 'vitest'
import { compareTimelineEventsNewestFirst } from './ApplicationModal'
import type { Event } from '../types'

function ev(overrides: Partial<Event>): Event {
  return { id: 1, application_id: 1, typ: 'mail', ...overrides }
}

describe('compareTimelineEventsNewestFirst', () => {
  it('sorts events on different days newest-first by date', () => {
    const older = ev({ id: 1, datum: '2026-07-01' })
    const newer = ev({ id: 2, datum: '2026-07-18' })
    expect([older, newer].sort(compareTimelineEventsNewestFirst)).toEqual([newer, older])
  })

  it('reproduces the reported bug fix: same-day events sort by datum_zeit, not insertion order', () => {
    const morning = ev({ id: 10, datum: '2026-07-18', datum_zeit: '2026-07-18T08:00:00' })
    const evening = ev({ id: 11, datum: '2026-07-18', datum_zeit: '2026-07-18T18:00:00' })
    // Evening inserted first in the array -- must still sort after morning is "older".
    expect([evening, morning].sort(compareTimelineEventsNewestFirst)).toEqual([evening, morning])
    expect([morning, evening].sort(compareTimelineEventsNewestFirst)).toEqual([evening, morning])
  })

  it('treats a date-only event as midnight, so a same-day timed event sorts as newer', () => {
    const dateOnly = ev({ id: 20, datum: '2026-07-18' })
    const timed = ev({ id: 21, datum: '2026-07-18', datum_zeit: '2026-07-18T09:30:00' })
    expect([dateOnly, timed].sort(compareTimelineEventsNewestFirst)).toEqual([timed, dateOnly])
  })

  it('falls back to id as the final tiebreaker for true ties', () => {
    const a = ev({ id: 5, datum: '2026-07-18' })
    const b = ev({ id: 6, datum: '2026-07-18' })
    expect([a, b].sort(compareTimelineEventsNewestFirst)).toEqual([b, a])
  })

  it('sorts undated events last', () => {
    const dated = ev({ id: 1, datum: '2026-07-18' })
    const undated = ev({ id: 2 })
    expect([undated, dated].sort(compareTimelineEventsNewestFirst)).toEqual([dated, undated])
  })
})
