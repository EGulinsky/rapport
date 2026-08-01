import { describe, it, expect } from 'vitest'
import { filterProgressEntries, computeLinkedInProgressPercent } from './SyncButton'
import type { LinkedInSyncStatus, LinkedInSyncCategoryCount } from '../types'

function entry(overrides: Partial<Parameters<typeof filterProgressEntries>[0][string]> = {}) {
  return {
    label: 'Gmail',
    step: '',
    current: 0,
    total: 0,
    percent: 0,
    done: false,
    created: 0,
    updated: 0,
    skipped: 0,
    ...overrides,
  }
}

describe('filterProgressEntries', () => {
  it('excludes a leftover targeted-sync entry even when its label collides with a real source', () => {
    // Reproduces the exact bug: an earlier per-application ("individual")
    // sync leaves a done "targeted_gmail" entry (auto-labeled "Gmail") in
    // the backend's global progress dict, and it's never cleared. A fresh
    // account-wide ("batch") Gmail sync then starts and writes its own
    // "gmail" entry — same real source, same visible label, different key.
    const progress = {
      targeted_gmail: entry({ done: true, percent: 100, created: 1 }),
      gmail: entry({ done: false, percent: 40, total: 10, current: 4 }),
    }

    const result = filterProgressEntries(progress)

    expect(result).toHaveLength(1)
    expect(result[0]).toEqual(progress.gmail)
  })

  it('includes every SOURCE_KEYS entry that is in progress or done', () => {
    const progress = {
      gmail: entry({ total: 10, current: 3, percent: 30 }),
      icloud_mail: entry({ label: 'iCloud Mail', done: true }),
      // Not a recognized batch-sync source key — should never be rendered
      // by the batch overlay regardless of its own done/total state.
      targeted_42: entry({ label: 'Some App', done: true }),
    }

    const result = filterProgressEntries(progress)

    expect(result).toHaveLength(2)
    expect(result).toEqual([progress.gmail, progress.icloud_mail])
  })

  it('includes an ai_scoring entry alongside the other sync sources', () => {
    const progress = {
      gmail: entry({ total: 10, current: 3, percent: 30 }),
      ai_scoring: entry({ label: 'AI Scoring', done: true, created: 2 }),
    }

    const result = filterProgressEntries(progress)

    expect(result).toHaveLength(2)
    expect(result).toEqual([progress.gmail, progress.ai_scoring])
  })

  it('omits sources with no progress and not done', () => {
    const progress = {
      gmail: entry({ total: 0, done: false }),
    }

    expect(filterProgressEntries(progress)).toHaveLength(0)
  })
})

function catCount(overrides: Partial<LinkedInSyncCategoryCount> = {}): LinkedInSyncCategoryCount {
  return {
    card_type: 'APPLIED', label: 'Applied', found: 0, created: 0, updated: 0, skipped: 0,
    status: 'pending', current_page: 0,
    ...overrides,
  }
}

function liStatus(overrides: Partial<LinkedInSyncStatus> = {}): LinkedInSyncStatus {
  return {
    status: 'running', step: '', processed: 0, total: 0, created: 0, updated: 0, skipped: 0,
    errors: [], category_counts: [], current_item: null, started_at: null, finished_at: null,
    ...overrides,
  }
}

describe('computeLinkedInProgressPercent', () => {
  it('is 0% before any category has started, instead of staying frozen once scraping begins', () => {
    const status = liStatus({
      category_counts: [catCount({ status: 'pending' }), catCount({ status: 'pending' })],
    })

    expect(computeLinkedInProgressPercent(status)).toBe(0)
  })

  it('reproduces the reported bug: total stays 0 through the whole category-scraping phase, so a', () => {
    // naive processed/total percent would sit at 0% here even though real
    // work (2 of 4 categories done, one active) is happening -- this is
    // exactly what the user saw as "the bar is always at 0%".
    const status = liStatus({
      total: 0, processed: 0,
      category_counts: [
        catCount({ status: 'done' }), catCount({ status: 'done' }),
        catCount({ status: 'active' }), catCount({ status: 'pending' }),
      ],
    })

    expect(computeLinkedInProgressPercent(status)).toBeGreaterThan(0)
    expect(computeLinkedInProgressPercent(status)).toBe(56) // (2 + 0.5) / 4 * 90, rounded
  })

  it('reaches 90% once every category is done but total/processed are not yet known', () => {
    const status = liStatus({
      total: 0, processed: 0,
      category_counts: [catCount({ status: 'done' }), catCount({ status: 'done' })],
    })

    expect(computeLinkedInProgressPercent(status)).toBe(90)
  })

  it('climbs from 90% to 100% during the final per-job processing pass once total is known', () => {
    const halfway = liStatus({
      total: 10, processed: 5,
      category_counts: [catCount({ status: 'done' }), catCount({ status: 'done' })],
    })
    const finished = liStatus({
      total: 10, processed: 10,
      category_counts: [catCount({ status: 'done' }), catCount({ status: 'done' })],
    })

    expect(computeLinkedInProgressPercent(halfway)).toBe(95)
    expect(computeLinkedInProgressPercent(finished)).toBe(100)
  })
})
