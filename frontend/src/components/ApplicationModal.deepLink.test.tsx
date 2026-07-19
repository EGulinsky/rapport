import { describe, it, expect } from 'vitest'
import { buildDeepLink } from './ApplicationModal'

describe('buildDeepLink', () => {
  it('returns null when source or external_id is missing', () => {
    expect(buildDeepLink(undefined, 'evt-1', undefined)).toBeNull()
    expect(buildDeepLink('gcal', undefined, 'https://calendar.google.com/x')).toBeNull()
  })

  it('builds a gmail link from external_id alone, ignoring external_url', () => {
    expect(buildDeepLink('gmail', '19f4afd3fdcdeadb', undefined))
      .toBe('https://mail.google.com/mail/u/0/#all/19f4afd3fdcdeadb')
  })

  it('strips the PendingMatch __status suffix from external_id for gmail', () => {
    expect(buildDeepLink('gmail', '19f4afd3fdcdeadb__status', undefined))
      .toBe('https://mail.google.com/mail/u/0/#all/19f4afd3fdcdeadb')
  })

  it('uses external_url as-is for gcal instead of reconstructing from external_id', () => {
    // Regression: the old implementation did btoa(external_id) alone, which
    // Google Calendar's "eventedit" link format doesn't accept (it also
    // needs the calendar ID baked into the same base64 blob) -- every such
    // link was broken. external_url is the API's own ready-made link.
    expect(buildDeepLink('gcal', 'evt-1', 'https://www.google.com/calendar/event?eid=abc123'))
      .toBe('https://www.google.com/calendar/event?eid=abc123')
  })

  it('returns null for gcal when external_url is missing (no broken link shown)', () => {
    expect(buildDeepLink('gcal', 'evt-1', undefined)).toBeNull()
  })

  it('builds icloud_mail/icloud_cal/icloud_notes links from external_id', () => {
    expect(buildDeepLink('icloud_mail', 'msg-1', undefined)).toBe('message://msg-1')
    expect(buildDeepLink('icloud_cal', 'cal-1', undefined)).toBe('x-apple-calevent:///cal-1')
    expect(buildDeepLink('icloud_notes', 'note-1', undefined)).toBe('applenotes://note-1')
  })

  it('returns null for unknown sources', () => {
    expect(buildDeepLink('linkedin_msg', 'conv-1', undefined)).toBeNull()
  })
})
