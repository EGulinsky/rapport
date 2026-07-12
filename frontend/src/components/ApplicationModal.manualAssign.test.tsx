import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { ApplicationModal } from './ApplicationModal'
import { api } from '../api/client'
import i18n from '../i18n'
import type { Application, ManualCandidate } from '../types'

vi.mock('../api/client', () => ({
  api: {
    applications: {
      get: vi.fn(),
      addEvent: vi.fn(),
    },
    targeted: {
      candidates: vi.fn(),
      assign: vi.fn(),
    },
    linkedin: {
      getConfig: vi.fn().mockResolvedValue({ configured: false }),
    },
    sync: {
      progress: vi.fn().mockResolvedValue({}),
    },
  },
}))

const BASE_APP: Application = {
  id: 42,
  firma: 'Acme GmbH',
  status: 'applied',
  events: [],
  contacts: [],
} as unknown as Application

function makeCandidate(overrides: Partial<ManualCandidate>): ManualCandidate {
  return {
    id: 1,
    source: 'gmail',
    external_id: 'ext-1',
    confidence: 80,
    ...overrides,
  }
}

async function openManualDialog() {
  render(<ApplicationModal appId={42} onClose={vi.fn()} onSaved={vi.fn()} />)
  await waitFor(() => expect(api.applications.get).toHaveBeenCalled())
  const syncMenuToggle = screen.getByTitle(/Gezielter Sync/i).nextElementSibling as HTMLElement
  fireEvent.click(syncMenuToggle)
  const trigger = await screen.findByText('Manuell zuordnen')
  fireEvent.click(trigger)
  await waitFor(() => expect(api.targeted.candidates).toHaveBeenCalled())
}

describe('ApplicationModal — manuelles Mehrfach-Zuordnen', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Pin to German regardless of the app's current pre-login default (see i18n/index.ts).
    i18n.changeLanguage('de')
    ;(api.applications.get as ReturnType<typeof vi.fn>).mockResolvedValue(BASE_APP)
  })

  it('positiv: zwei ausgewählte Kandidaten werden per Sammel-Import beide zugeordnet', async () => {
    const candidates = [
      makeCandidate({ id: 1, external_id: 'a', source: 'gmail', titel: 'Mail von Frau Steffen' }),
      makeCandidate({ id: 2, external_id: 'b', source: 'gcal', titel: 'Interview-Termin' }),
    ]
    ;(api.targeted.candidates as ReturnType<typeof vi.fn>).mockResolvedValue(candidates)
    ;(api.targeted.assign as ReturnType<typeof vi.fn>).mockResolvedValue({ conflict: false, event_id: 99 })

    await openManualDialog()

    const checkboxes = await screen.findAllByRole('checkbox')
    expect(checkboxes).toHaveLength(2)
    fireEvent.click(checkboxes[0])
    fireEvent.click(checkboxes[1])

    const importButton = await screen.findByRole('button', { name: /2 importieren/i })
    fireEvent.click(importButton)

    await waitFor(() => expect(api.targeted.assign).toHaveBeenCalledTimes(2))
    expect(api.targeted.assign).toHaveBeenCalledWith(42, expect.objectContaining({ match_id: 1, external_id: 'a' }))
    expect(api.targeted.assign).toHaveBeenCalledWith(42, expect.objectContaining({ match_id: 2, external_id: 'b' }))
  })

  it('negativ: ein Konflikt bei einem Kandidaten überspringt nur diesen und meldet ihn', async () => {
    const candidates = [
      makeCandidate({ id: 1, external_id: 'a', source: 'gmail', titel: 'Konflikt-Mail' }),
      makeCandidate({ id: 2, external_id: 'b', source: 'gcal', titel: 'Freier Termin' }),
    ]
    ;(api.targeted.candidates as ReturnType<typeof vi.fn>).mockResolvedValue(candidates)
    ;(api.targeted.assign as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ conflict: true, conflict_app_firma: 'Andere Firma GmbH' })
      .mockResolvedValueOnce({ conflict: false, event_id: 100 })

    await openManualDialog()

    const checkboxes = await screen.findAllByRole('checkbox')
    fireEvent.click(checkboxes[0])
    fireEvent.click(checkboxes[1])
    fireEvent.click(await screen.findByRole('button', { name: /2 importieren/i }))

    await waitFor(() => expect(api.targeted.assign).toHaveBeenCalledTimes(2))
    expect(await screen.findByText(/Andere Firma GmbH/)).toBeInTheDocument()
    // Der konfliktfreie Kandidat verschwindet aus der Liste, der Konflikt-Kandidat bleibt sichtbar.
    expect(screen.queryByText('Freier Termin')).not.toBeInTheDocument()
    expect(screen.getByText('Konflikt-Mail')).toBeInTheDocument()
  })

  it('corner case: ohne Auswahl wird keine Sammel-Aktion angezeigt', async () => {
    ;(api.targeted.candidates as ReturnType<typeof vi.fn>).mockResolvedValue([
      makeCandidate({ id: 1, external_id: 'a', titel: 'Einzelner Treffer' }),
    ])

    await openManualDialog()
    await screen.findByText('Einzelner Treffer')

    expect(screen.queryByRole('button', { name: /importieren/i })).not.toBeInTheDocument()
  })
})
