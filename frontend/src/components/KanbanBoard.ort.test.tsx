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
})
