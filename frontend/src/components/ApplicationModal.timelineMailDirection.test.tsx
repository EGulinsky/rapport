import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { ApplicationModal } from './ApplicationModal'
import { api } from '../api/client'
import i18n from '../i18n'
import type { Application, Event } from '../types'

vi.mock('../api/client', () => ({
  api: {
    applications: {
      get: vi.fn(),
    },
    linkedin: {
      getConfig: vi.fn().mockResolvedValue({ configured: false }),
    },
    sync: {
      progress: vi.fn().mockResolvedValue({}),
    },
  },
}))

function makeEvent(overrides: Partial<Event>): Event {
  return {
    id: 1, application_id: 42, typ: 'mail', datum: '2026-07-18',
    ...overrides,
  }
}

function baseApp(events: Event[]): Application {
  return { id: 42, firma: 'Acme GmbH', status: 'applied', events, contacts: [] } as unknown as Application
}

async function openTimeline(events: Event[]) {
  ;(api.applications.get as ReturnType<typeof vi.fn>).mockResolvedValue(baseApp(events))
  render(<ApplicationModal appId={42} onClose={vi.fn()} onSaved={vi.fn()} />)
  await waitFor(() => expect(api.applications.get).toHaveBeenCalled())
  fireEvent.click(await screen.findByText('Verlauf'))
}

describe('ApplicationModal — Timeline: Mail-Richtung und einklappbarer Inhalt', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.changeLanguage('de')
  })

  it('positiv: voller Mailinhalt ist standardmäßig eingeklappt', async () => {
    await openTimeline([
      makeEvent({ source: 'gmail', autor: 'Anna Recruiterin <anna@contoso.example>', notiz: 'Der vollständige Mailtext steht hier drin.' }),
    ])

    // jsdom doesn't implement the native <details>/[open] CSS hiding rule
    // browsers apply, so the child text stays present in the DOM either
    // way -- check the element's own .open property instead, which is
    // what actually drives the real collapsed/expanded behavior.
    const details = screen.getByText('Inhalt anzeigen').closest('details')
    expect(details).not.toBeNull()
    expect((details as HTMLDetailsElement).open).toBe(false)
  })

  it('positiv: Klick auf "Inhalt anzeigen" zeigt den vollen Mailinhalt', async () => {
    await openTimeline([
      makeEvent({ source: 'gmail', autor: 'Anna Recruiterin <anna@contoso.example>', notiz: 'Der vollständige Mailtext steht hier drin.' }),
    ])

    fireEvent.click(screen.getByText('Inhalt anzeigen'))

    expect(screen.getByText('Der vollständige Mailtext steht hier drin.')).toBeInTheDocument()
  })

  it('positiv: Kalendereintrag ist ebenfalls standardmäßig eingeklappt', async () => {
    await openTimeline([
      makeEvent({ source: 'gcal', typ: 'gespräch', autor: 'Anna Recruiterin <anna@contoso.example>', notiz: 'Beschreibung des Termins.' }),
    ])

    const details = screen.getByText('Inhalt anzeigen').closest('details')
    expect(details).not.toBeNull()
    expect((details as HTMLDetailsElement).open).toBe(false)
  })

  it('negativ: manuelle Notiz bleibt ohne Einklapp-Mechanik direkt sichtbar', async () => {
    await openTimeline([
      makeEvent({ source: undefined, typ: 'notiz', notiz: 'Kurze manuelle Notiz.' }),
    ])

    expect(screen.getByText('Kurze manuelle Notiz.')).toBeInTheDocument()
    expect(screen.queryByText('Inhalt anzeigen')).not.toBeInTheDocument()
  })

  it('positiv: gesendete Mail zeigt den "Gesendet"-Pfeil', async () => {
    await openTimeline([
      makeEvent({ source: 'gmail', autor: 'Anna Recruiterin <anna@contoso.example>', mail_direction: 'sent', notiz: 'x' }),
    ])

    expect(screen.getByLabelText('Gesendet')).toBeInTheDocument()
    expect(screen.queryByLabelText('Empfangen')).not.toBeInTheDocument()
  })

  it('positiv: empfangene Mail zeigt den "Empfangen"-Pfeil', async () => {
    await openTimeline([
      makeEvent({ source: 'gmail', autor: 'Anna Recruiterin <anna@contoso.example>', mail_direction: 'received', notiz: 'x' }),
    ])

    expect(screen.getByLabelText('Empfangen')).toBeInTheDocument()
    expect(screen.queryByLabelText('Gesendet')).not.toBeInTheDocument()
  })

  it('negativ: Kalendereintrag ohne mail_direction zeigt keinen Pfeil', async () => {
    await openTimeline([
      makeEvent({ source: 'gcal', typ: 'gespräch', autor: 'Anna Recruiterin <anna@contoso.example>', notiz: 'x' }),
    ])

    expect(screen.queryByLabelText('Gesendet')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Empfangen')).not.toBeInTheDocument()
  })
})
