import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import AuditLogModal from './AuditLogModal'
import { api } from '../api/client'
import i18n from '../i18n'
import type { AuditEntry } from '../types'

vi.mock('../api/client', () => ({
  api: {
    audit: {
      list: vi.fn(),
      clear: vi.fn(),
    },
  },
}))

function makeEntry(overrides: Partial<AuditEntry> = {}): AuditEntry {
  return {
    id: 1,
    app_id: 42,
    app_firma: 'Acme GmbH',
    app_rolle: 'Backend Engineer',
    contact_id: null,
    contact_name: null,
    company_profile_id: null,
    company_name: null,
    event_id: null,
    event_titel: null,
    entity_type: 'application',
    timestamp: '2026-07-12T10:00:00Z',
    action: 'update',
    field: null,
    old_value: null,
    new_value: null,
    source: 'user',
    reason: null,
    ...overrides,
  }
}

describe('AuditLogModal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Fixes the language so these assertions on exact text stay meaningful
    // regardless of the app's current pre-login default (see i18n/index.ts).
    i18n.changeLanguage('de')
    ;(api.audit.list as ReturnType<typeof vi.fn>).mockResolvedValue({
      total: 1,
      items: [makeEntry()],
    })
  })

  it('positiv: zeigt deutsche Titel, Tabellenkopf- und Aktions-Labels', async () => {
    render(<AuditLogModal onClose={vi.fn()} />)

    expect(screen.getByText('Audit-Log')).toBeInTheDocument()
    expect(screen.getByText('Zeitpunkt')).toBeInTheDocument()
    expect(screen.getByText('Quelle')).toBeInTheDocument()
    // Action label only appears once the mocked entry has actually loaded and
    // re-rendered — findByText (not getByText) avoids a race against that.
    expect(await screen.findByText('Geändert')).toBeInTheDocument()
  })

  it('positiv: leere Liste zeigt den deutschen Leer-Hinweis', async () => {
    ;(api.audit.list as ReturnType<typeof vi.fn>).mockResolvedValue({ total: 0, items: [] })
    render(<AuditLogModal onClose={vi.fn()} />)

    expect(await screen.findByText('Keine Einträge')).toBeInTheDocument()
  })

  it('positiv: sperrt Body-Scroll waehrend geoeffnet und stellt ihn beim Schliessen wieder her', async () => {
    // Regression: without this, mouse/trackpad scrolling chained straight
    // through the fixed-position backdrop to the page underneath -- min-h-0
    // alone (the earlier fix) only bounds the table's own height, it doesn't
    // stop an unconsumed scroll gesture from reaching whatever's behind a
    // `position: fixed` element.
    document.body.style.overflow = ''
    const { unmount } = render(<AuditLogModal onClose={vi.fn()} />)
    await screen.findByText('Zeitpunkt')

    expect(document.body.style.overflow).toBe('hidden')

    unmount()
    expect(document.body.style.overflow).toBe('')
  })

  it('positiv: Tabellen-Container hat overscroll-contain, um Scroll-Chaining zu stoppen', async () => {
    const { container } = render(<AuditLogModal onClose={vi.fn()} />)
    await screen.findByText('Zeitpunkt')

    const scrollContainer = container.querySelector('.overflow-auto')
    expect(scrollContainer?.className).toContain('overscroll-contain')
  })

  describe('in English', () => {
    beforeEach(() => {
      i18n.changeLanguage('en')
    })

    it('shows English title, table headers, and action labels', async () => {
      render(<AuditLogModal onClose={vi.fn()} />)

      expect(screen.getByText('Audit log')).toBeInTheDocument()
      expect(screen.getByText('Timestamp')).toBeInTheDocument()
      expect(screen.getByText('Source')).toBeInTheDocument()
      // Action label only appears once the mocked entry has actually loaded and
      // re-rendered — findByText (not getByText) avoids a race against that.
      expect(await screen.findByText('Updated')).toBeInTheDocument()
    })
  })
})
