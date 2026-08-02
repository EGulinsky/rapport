import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { ApplicationModal } from './ApplicationModal'
import { api } from '../api/client'
import i18n from '../i18n'
import type { Application } from '../types'

vi.mock('../api/client', () => ({
  api: {
    applications: {
      get: vi.fn(),
      update: vi.fn(),
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

function makeApp(overrides: Partial<Application> = {}): Application {
  return {
    id: 42,
    firma: 'Headhunter XY',
    rolle: 'Engineer',
    main_status: 'applied',
    abgesagt: false,
    ghosting: false,
    salary_mismatch: false,
    is_headhunter: true,
    zielfirma_bei_hh: 'Contoso Corp',
    zielfirma_bekannt: true,
    events: [],
    contacts: [],
    ...overrides,
  } as Application
}

describe('ApplicationModal — Zielfirma-bekannt-Flag bei Headhuntern', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.changeLanguage('de')
  })

  it('positiv: Checkbox "Zielfirma bekannt" nur sichtbar wenn Headhunter aktiv, und PATCH sendet den Wert', async () => {
    const app = makeApp({ zielfirma_bekannt: true })
    ;(api.applications.get as ReturnType<typeof vi.fn>).mockResolvedValue(app)
    ;(api.applications.update as ReturnType<typeof vi.fn>).mockResolvedValue({ ...app, zielfirma_bekannt: false })

    render(<ApplicationModal appId={42} onClose={vi.fn()} onSaved={vi.fn()} />)
    await waitFor(() => expect(api.applications.get).toHaveBeenCalled())

    fireEvent.click(await screen.findByTestId('edit-application-button'))

    const knownLabel = await screen.findByText('Zielfirma bekannt')
    const checkboxInput = knownLabel.querySelector('input') as HTMLInputElement
    expect(checkboxInput.checked).toBe(true)

    fireEvent.click(checkboxInput)
    expect(checkboxInput.checked).toBe(false)

    fireEvent.click(screen.getByText('Speichern'))

    await waitFor(() => expect(api.applications.update).toHaveBeenCalled())
    expect(api.applications.update).toHaveBeenCalledWith(42, expect.objectContaining({ zielfirma_bekannt: false }))
  })

  it('negativ: Checkbox erscheint nicht, solange Headhunter nicht aktiv ist', async () => {
    const app = makeApp({ is_headhunter: false })
    ;(api.applications.get as ReturnType<typeof vi.fn>).mockResolvedValue(app)

    render(<ApplicationModal appId={42} onClose={vi.fn()} onSaved={vi.fn()} />)
    await waitFor(() => expect(api.applications.get).toHaveBeenCalled())

    fireEvent.click(await screen.findByTestId('edit-application-button'))

    expect(screen.queryByText('Zielfirma bekannt')).not.toBeInTheDocument()
  })

  it('positiv: nicht-bekannte generische Zielfirma zeigt im Lesemodus einen Hinweis statt eines Firmennamens', async () => {
    const app = makeApp({
      zielfirma_bekannt: false,
      zielfirma_bei_hh: 'internationaler Automobilzulieferer, vertraulich',
    })
    ;(api.applications.get as ReturnType<typeof vi.fn>).mockResolvedValue(app)

    render(<ApplicationModal appId={42} onClose={vi.fn()} onSaved={vi.fn()} />)

    await screen.findByText(/internationaler Automobilzulieferer, vertraulich \(allgemeine Beschreibung\)/)
  })
})
