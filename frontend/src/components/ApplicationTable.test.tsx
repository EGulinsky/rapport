import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ApplicationTable } from './ApplicationTable'
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

describe('ApplicationTable — match_score/success_probability columns', () => {
  it('positiv: Werte werden gerendert, fehlende Scores zeigen "—"', () => {
    const apps = [
      makeApp({ id: 1, match_score: 78, success_probability: 55 }),
      makeApp({ id: 2, firma: 'Globex Inc', match_score: null, success_probability: null }),
    ]
    render(<ApplicationTable applications={apps} onSelect={vi.fn()} onStatusChanged={vi.fn()} />)

    expect(screen.getByText('78')).toBeInTheDocument()
    expect(screen.getByText('55')).toBeInTheDocument()
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(2)
  })

  it('positiv: hoher Score wird grün, niedriger rot eingefärbt', () => {
    const apps = [
      makeApp({ id: 1, match_score: 85 }),
      makeApp({ id: 2, firma: 'Globex Inc', match_score: 15 }),
    ]
    render(<ApplicationTable applications={apps} onSelect={vi.fn()} onStatusChanged={vi.fn()} />)

    expect(screen.getByText('85')).toHaveClass('text-green-600')
    expect(screen.getByText('15')).toHaveClass('text-red-600')
  })

  it('positiv: reasoning landet als title-Tooltip auf der Zelle', () => {
    const apps = [makeApp({ id: 1, match_score: 78, match_score_reasoning: 'Guter Fit' })]
    render(<ApplicationTable applications={apps} onSelect={vi.fn()} onStatusChanged={vi.fn()} />)

    expect(screen.getByText('78').closest('td')).toHaveAttribute('title', 'Guter Fit')
  })

  it('positiv: Sortierung nach Match-Score funktioniert (auf-/absteigend)', () => {
    const apps = [
      makeApp({ id: 1, firma: 'A GmbH', match_score: 30 }),
      makeApp({ id: 2, firma: 'B GmbH', match_score: 90 }),
    ]
    const { container } = render(<ApplicationTable applications={apps} onSelect={vi.fn()} onStatusChanged={vi.fn()} />)

    const matchScoreHeader = screen.getByText('Match')
    fireEvent.click(matchScoreHeader.closest('th')!)

    const rows = container.querySelectorAll('tbody tr')
    // ascending: lowest score (30) first
    expect(rows[0].textContent).toContain('A GmbH')
  })

  it('regression: colSpan der Gruppen-Header-Zeile stimmt mit der Spaltenzahl überein', () => {
    const apps = [
      makeApp({ id: 1, main_status: 'applied' }),
      makeApp({ id: 2, firma: 'Globex Inc', main_status: 'hr' }),
    ]
    const { container } = render(
      <ApplicationTable applications={apps} onSelect={vi.fn()} onStatusChanged={vi.fn()} />
    )

    // Trigger main_status sort so group-break rows render.
    fireEvent.click(screen.getByText('Status').closest('th')!)

    const headerCellCount = container.querySelectorAll('thead th').length
    const groupRow = container.querySelector('tbody tr td[colspan]')
    expect(groupRow).not.toBeNull()
    expect(Number(groupRow!.getAttribute('colspan'))).toBe(headerCellCount)
  })

  it('regression: colSpan berücksichtigt die zusätzliche Checkbox-Spalte', () => {
    const apps = [
      makeApp({ id: 1, main_status: 'applied' }),
      makeApp({ id: 2, firma: 'Globex Inc', main_status: 'hr' }),
    ]
    const { container } = render(
      <ApplicationTable
        applications={apps}
        onSelect={vi.fn()}
        onStatusChanged={vi.fn()}
        selectedIds={new Set()}
        onToggleSelect={vi.fn()}
      />
    )

    fireEvent.click(screen.getByText('Status').closest('th')!)

    const headerCellCount = container.querySelectorAll('thead th').length
    const groupRow = container.querySelector('tbody tr td[colspan]')
    expect(Number(groupRow!.getAttribute('colspan'))).toBe(headerCellCount)
  })
})
