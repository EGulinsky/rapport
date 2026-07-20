import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { KanbanBoard } from './KanbanBoard'
import type { Application } from '../types'

function makeApp(overrides: Partial<Application>): Application {
  return {
    id: 1,
    firma: 'Contoso AG',
    rolle: 'Backend Engineer',
    main_status: 'applied',
    is_headhunter: false,
    abgesagt: false,
    ghosting: false,
    ...overrides,
  } as Application
}

describe('KanbanBoard — Ort mit Google-Maps-Link', () => {
  it('positiv: gesetzter Ort wird als Google-Maps-Link angezeigt', () => {
    const app = makeApp({ id: 1, ort: 'München, Deutschland' })
    render(
      <KanbanBoard
        columns={[{ status: 'applied', items: [app] }]}
        onSelect={vi.fn()}
        onChanged={vi.fn()}
      />
    )

    const link = screen.getByRole('link', { name: /München, Deutschland/ })
    expect(link).toHaveAttribute(
      'href',
      'https://www.google.com/maps/search/?api=1&query=M%C3%BCnchen%2C%20Deutschland'
    )
    expect(link).toHaveAttribute('target', '_blank')
  })

  it('negativ: ohne Ort wird kein Maps-Link gerendert', () => {
    const app = makeApp({ id: 2, ort: undefined })
    render(
      <KanbanBoard
        columns={[{ status: 'applied', items: [app] }]}
        onSelect={vi.fn()}
        onChanged={vi.fn()}
      />
    )

    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })

  it('positiv: cachte Fahrstrecke wird als km/h neben dem Ort angezeigt', () => {
    const app = makeApp({ id: 3, ort: 'München, Deutschland', drive_distance_km: 504.2, drive_duration_min: 312 })
    render(
      <KanbanBoard
        columns={[{ status: 'applied', items: [app] }]}
        onSelect={vi.fn()}
        onChanged={vi.fn()}
      />
    )

    expect(screen.getByText('· 504 km · 5.2 h')).toBeInTheDocument()
  })

  it('negativ: ohne Fahrstrecke wird keine Distanz gerendert', () => {
    const app = makeApp({ id: 4, ort: 'München, Deutschland' })
    render(
      <KanbanBoard
        columns={[{ status: 'applied', items: [app] }]}
        onSelect={vi.fn()}
        onChanged={vi.fn()}
      />
    )

    expect(screen.queryByText(/km ·/)).not.toBeInTheDocument()
  })
})
