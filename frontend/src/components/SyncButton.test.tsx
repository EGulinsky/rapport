import { describe, it, expect } from 'vitest'
import { filterProgressEntries } from './SyncButton'

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

  it('omits sources with no progress and not done', () => {
    const progress = {
      gmail: entry({ total: 0, done: false }),
    }

    expect(filterProgressEntries(progress)).toHaveLength(0)
  })
})
