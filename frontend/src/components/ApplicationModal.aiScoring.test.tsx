import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { ApplicationModal } from './ApplicationModal'
import { api } from '../api/client'
import i18n from '../i18n'
import type { Application } from '../types'

vi.mock('../api/client', () => ({
  api: {
    applications: {
      get: vi.fn(),
      addEvent: vi.fn(),
    },
    linkedin: {
      getConfig: vi.fn().mockResolvedValue({ configured: false }),
    },
    sync: {
      progress: vi.fn().mockResolvedValue({}),
    },
  },
}))

function makeApp(overrides: Partial<Application>): Application {
  return {
    id: 42,
    firma: 'Acme GmbH',
    rolle: 'Backend Engineer',
    main_status: 'applied',
    events: [],
    contacts: [],
    ...overrides,
  } as unknown as Application
}

describe('ApplicationModal — AI-Einschätzung im Overview-Tab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.changeLanguage('de')
  })

  it('positiv: beide Scores samt Begründung werden angezeigt', async () => {
    ;(api.applications.get as ReturnType<typeof vi.fn>).mockResolvedValue(makeApp({
      match_score: 78,
      match_score_reasoning: 'Guter Fit wegen Python-Erfahrung',
      success_probability: 55,
      success_probability_reasoning: 'HR-Gespräch bereits stattgefunden',
    }))

    render(<ApplicationModal appId={42} onClose={vi.fn()} onSaved={vi.fn()} />)
    await waitFor(() => expect(api.applications.get).toHaveBeenCalled())

    expect(await screen.findByText('78 / 100')).toBeInTheDocument()
    expect(screen.getByText('55 / 100')).toBeInTheDocument()
    expect(screen.getByText('Guter Fit wegen Python-Erfahrung')).toBeInTheDocument()
    expect(screen.getByText('HR-Gespräch bereits stattgefunden')).toBeInTheDocument()
  })

  it('negativ: ohne berechnete Scores wird der "noch nicht berechnet"-Hinweis angezeigt', async () => {
    ;(api.applications.get as ReturnType<typeof vi.fn>).mockResolvedValue(makeApp({
      match_score: null,
      success_probability: null,
    }))

    render(<ApplicationModal appId={42} onClose={vi.fn()} onSaved={vi.fn()} />)
    await waitFor(() => expect(api.applications.get).toHaveBeenCalled())

    expect(await screen.findByText('Noch nicht berechnet')).toBeInTheDocument()
    expect(screen.queryByText(/\/ 100/)).not.toBeInTheDocument()
  })

  it('positiv: ein 0-Wert wird als echter Score angezeigt, nicht als "noch nicht berechnet"', async () => {
    ;(api.applications.get as ReturnType<typeof vi.fn>).mockResolvedValue(makeApp({
      match_score: 0,
      match_score_reasoning: 'Kein erkennbarer Zusammenhang',
      success_probability: null,
    }))

    render(<ApplicationModal appId={42} onClose={vi.fn()} onSaved={vi.fn()} />)
    await waitFor(() => expect(api.applications.get).toHaveBeenCalled())

    expect(await screen.findByText('0 / 100')).toBeInTheDocument()
    expect(screen.queryByText('Noch nicht berechnet')).not.toBeInTheDocument()
  })

  it('positiv: gespeichertes Feedback wird als Liste angezeigt, neuestes zuerst', async () => {
    ;(api.applications.get as ReturnType<typeof vi.fn>).mockResolvedValue(makeApp({
      match_score: 78,
      feedback_entries: [
        { id: 1, text: 'Erste Notiz.', created_at: '2026-07-01T10:00:00Z' },
        { id: 2, text: 'Zweite Notiz.', created_at: '2026-07-15T10:00:00Z' },
      ],
    }))

    render(<ApplicationModal appId={42} onClose={vi.fn()} onSaved={vi.fn()} />)
    await waitFor(() => expect(api.applications.get).toHaveBeenCalled())

    const firstNote = await screen.findByText('Zweite Notiz.')
    const secondNote = await screen.findByText('Erste Notiz.')
    expect(firstNote).toBeInTheDocument()
    expect(secondNote).toBeInTheDocument()
    // Newest first: "Zweite Notiz." (15.07) must appear before "Erste Notiz." (01.07) in the DOM.
    expect(firstNote.compareDocumentPosition(secondNote) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('negativ: ohne Feedback-Einträge wird keine Feedback-Sektion angezeigt', async () => {
    ;(api.applications.get as ReturnType<typeof vi.fn>).mockResolvedValue(makeApp({
      match_score: 78,
      feedback_entries: [],
    }))

    render(<ApplicationModal appId={42} onClose={vi.fn()} onSaved={vi.fn()} />)
    await waitFor(() => expect(api.applications.get).toHaveBeenCalled())
    await screen.findByText('78 / 100')

    expect(screen.queryByText('Dein Feedback')).not.toBeInTheDocument()
  })
})

describe('ApplicationModal — Anzahl Bewerber im Overview-Tab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.changeLanguage('de')
  })

  it('positiv: gesetzte Bewerberzahl wird angezeigt', async () => {
    ;(api.applications.get as ReturnType<typeof vi.fn>).mockResolvedValue(makeApp({ bewerberzahl: 150 }))

    render(<ApplicationModal appId={42} onClose={vi.fn()} onSaved={vi.fn()} />)
    await waitFor(() => expect(api.applications.get).toHaveBeenCalled())

    expect(await screen.findByText('150')).toBeInTheDocument()
  })

  it('negativ: ohne Bewerberzahl wird "Unbekannt" angezeigt', async () => {
    ;(api.applications.get as ReturnType<typeof vi.fn>).mockResolvedValue(makeApp({ bewerberzahl: null }))

    render(<ApplicationModal appId={42} onClose={vi.fn()} onSaved={vi.fn()} />)
    await waitFor(() => expect(api.applications.get).toHaveBeenCalled())

    expect(await screen.findByText('Unbekannt')).toBeInTheDocument()
  })
})
