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

describe('KanbanBoard — nächster Schritt', () => {
  it('positiv: wird angezeigt, wenn keine KI-Einschätzung vorliegt', () => {
    const app = makeApp({ naechster_schritt: 'Warte auf Feedback' })
    render(
      <KanbanBoard columns={[{ status: 'applied', items: [app] }]} onSelect={vi.fn()} onChanged={vi.fn()} />
    )

    expect(screen.getByText('→ Warte auf Feedback')).toBeInTheDocument()
  })

  it('positiv: wird auch neben einer vorhandenen KI-Einschätzung angezeigt', () => {
    const app = makeApp({ naechster_schritt: 'Warte auf Feedback', ai_color: 'green', ai_next_step: 'Nachfassen' })
    render(
      <KanbanBoard columns={[{ status: 'applied', items: [app] }]} onSelect={vi.fn()} onChanged={vi.fn()} />
    )

    expect(screen.getByText('→ Warte auf Feedback')).toBeInTheDocument()
    expect(screen.getByText('Nachfassen')).toBeInTheDocument()
  })

  it('negativ: bei abgesagten Bewerbungen wird nichts angezeigt', () => {
    const app = makeApp({ naechster_schritt: 'Warte auf Feedback', abgesagt: true })
    render(
      <KanbanBoard columns={[{ status: 'rejected', items: [app] }]} onSelect={vi.fn()} onChanged={vi.fn()} />
    )

    expect(screen.queryByText('→ Warte auf Feedback')).not.toBeInTheDocument()
  })
})
