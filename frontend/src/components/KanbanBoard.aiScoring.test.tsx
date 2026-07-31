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

describe('KanbanBoard — AI match_score/success_probability badges', () => {
  it('positiv: beide Badges werden mit ihrem Wert angezeigt', () => {
    const app = makeApp({ match_score: 78, success_probability: 55 })
    render(
      <KanbanBoard columns={[{ status: 'applied', items: [app] }]} onSelect={vi.fn()} onChanged={vi.fn()} />
    )

    expect(screen.getByText('78')).toBeInTheDocument()
    expect(screen.getByText('55')).toBeInTheDocument()
  })

  it('positiv: hohe Werte werden grün eingefärbt', () => {
    const app = makeApp({ match_score: 85 })
    render(
      <KanbanBoard columns={[{ status: 'applied', items: [app] }]} onSelect={vi.fn()} onChanged={vi.fn()} />
    )

    expect(screen.getByText('85')).toHaveClass('text-green-600')
  })

  it('positiv: mittlere Werte werden gelb eingefärbt', () => {
    const app = makeApp({ match_score: 50 })
    render(
      <KanbanBoard columns={[{ status: 'applied', items: [app] }]} onSelect={vi.fn()} onChanged={vi.fn()} />
    )

    expect(screen.getByText('50')).toHaveClass('text-yellow-600')
  })

  it('positiv: niedrige Werte werden rot eingefärbt', () => {
    const app = makeApp({ match_score: 20 })
    render(
      <KanbanBoard columns={[{ status: 'applied', items: [app] }]} onSelect={vi.fn()} onChanged={vi.fn()} />
    )

    expect(screen.getByText('20')).toHaveClass('text-red-600')
  })

  it('positiv: Boundary-Wert 70 zählt noch als grün', () => {
    const app = makeApp({ match_score: 70 })
    render(
      <KanbanBoard columns={[{ status: 'applied', items: [app] }]} onSelect={vi.fn()} onChanged={vi.fn()} />
    )

    expect(screen.getByText('70')).toHaveClass('text-green-600')
  })

  it('positiv: Boundary-Wert 40 zählt noch als gelb', () => {
    const app = makeApp({ match_score: 40 })
    render(
      <KanbanBoard columns={[{ status: 'applied', items: [app] }]} onSelect={vi.fn()} onChanged={vi.fn()} />
    )

    expect(screen.getByText('40')).toHaveClass('text-yellow-600')
  })

  it('positiv: reasoning landet als title-Tooltip auf dem Badge', () => {
    const app = makeApp({ match_score: 78, match_score_reasoning: 'Guter Fit wegen Python-Erfahrung' })
    render(
      <KanbanBoard columns={[{ status: 'applied', items: [app] }]} onSelect={vi.fn()} onChanged={vi.fn()} />
    )

    expect(screen.getByText('78').closest('span')).toHaveAttribute('title', 'Guter Fit wegen Python-Erfahrung')
  })

  it('negativ: ohne match_score/success_probability wird nichts gerendert', () => {
    const app = makeApp({})
    render(
      <KanbanBoard columns={[{ status: 'applied', items: [app] }]} onSelect={vi.fn()} onChanged={vi.fn()} />
    )

    expect(screen.queryByText('78')).not.toBeInTheDocument()
  })
})
