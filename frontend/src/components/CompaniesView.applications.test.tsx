import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { CompaniesView } from './CompaniesView'
import { api } from '../api/client'
import i18n from '../i18n'
import type { CompanyProfile } from '../types'

vi.mock('../api/client', () => ({
  api: {
    companies: {
      list: vi.fn(),
    },
  },
}))

function makeCompany(overrides: Partial<CompanyProfile>): CompanyProfile {
  return {
    id: 1,
    name_display: 'Contoso AG',
    name_norm: 'contoso ag',
    industry: null,
    company_type: null,
    employee_range: null,
    employee_count: null,
    founded_year: null,
    hq_city: 'Berlin',
    hq_country: 'Deutschland',
    website: null,
    linkedin_company_url: null,
    description: null,
    sync_source: null,
    sync_status: 'done',
    sync_error: null,
    last_synced_at: null,
    ...overrides,
  }
}

describe('CompaniesView — zeigt angehängte Bewerbungen statt Standort-Spalte', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.changeLanguage('de')
  })

  it('positiv: angehängte Bewerbungen werden pro Firmenzeile aufgelistet, Klick öffnet die Bewerbung', async () => {
    ;(api.companies.list as ReturnType<typeof vi.fn>).mockResolvedValue([
      makeCompany({
        applications: [
          { id: 42, firma: 'Contoso AG', rolle: 'Backend Engineer', main_status: 'applied' },
        ],
      }),
    ])
    const onOpenApplication = vi.fn()

    render(<CompaniesView onOpenApplication={onOpenApplication} onOpenCompany={vi.fn()} />)

    await screen.findByText('Backend Engineer')

    fireEvent.click(screen.getByText('Backend Engineer'))
    expect(onOpenApplication).toHaveBeenCalledWith(42)
  })

  it('positiv: Bewerbungsdatum wird als zweite Zeile angezeigt (gleiche Zweizeilen-Optik wie in der Kontakte-Ansicht)', async () => {
    ;(api.companies.list as ReturnType<typeof vi.fn>).mockResolvedValue([
      makeCompany({
        applications: [
          { id: 42, firma: 'Contoso AG', rolle: 'Backend Engineer', main_status: 'applied', datum_bewerbung: '2026-03-15' },
        ],
      }),
    ])

    render(<CompaniesView onOpenApplication={vi.fn()} onOpenCompany={vi.fn()} />)

    await screen.findByText('Backend Engineer')
    expect(screen.getByText('15.3.2026')).toBeInTheDocument()
  })

  it('negativ: ohne Bewerbungen wird ein Platzhalter angezeigt, kein Standort mehr', async () => {
    ;(api.companies.list as ReturnType<typeof vi.fn>).mockResolvedValue([
      makeCompany({ applications: [] }),
    ])

    render(<CompaniesView onOpenApplication={vi.fn()} onOpenCompany={vi.fn()} />)

    await screen.findByText('Keine Bewerbung')
    expect(screen.queryByText('Berlin, Deutschland')).not.toBeInTheDocument()
  })

  it('corner_case: die Standort-Spaltenüberschrift wurde durch Bewerbungen ersetzt', async () => {
    ;(api.companies.list as ReturnType<typeof vi.fn>).mockResolvedValue([])

    render(<CompaniesView onOpenApplication={vi.fn()} onOpenCompany={vi.fn()} />)

    await waitFor(() => expect(api.companies.list).toHaveBeenCalled())
    expect(screen.getByText('Bewerbungen')).toBeInTheDocument()
    expect(screen.queryByText('Standort')).not.toBeInTheDocument()
  })

  it('positiv: abgesagte Bewerbungen zeigen ein "Absage"-Signal, aktive nicht', async () => {
    ;(api.companies.list as ReturnType<typeof vi.fn>).mockResolvedValue([
      makeCompany({
        applications: [
          { id: 42, firma: 'Contoso AG', rolle: 'Backend Engineer', main_status: 'rejected' },
          { id: 43, firma: 'Contoso AG', rolle: 'Frontend Engineer', main_status: 'applied' },
        ],
      }),
    ])

    render(<CompaniesView onOpenApplication={vi.fn()} onOpenCompany={vi.fn()} />)

    await screen.findByText('Backend Engineer')
    expect(screen.getByText('Absage')).toBeInTheDocument()
    // only one rejected application among the two -> exactly one signal
    expect(screen.getAllByText('Absage')).toHaveLength(1)
  })
})

describe('CompaniesView — Standardsortierung', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.changeLanguage('de')
  })

  it('positiv: Firmen werden standardmäßig alphabetisch nach Name aufsteigend sortiert, nicht nach Bewerbungsanzahl', async () => {
    ;(api.companies.list as ReturnType<typeof vi.fn>).mockResolvedValue([
      makeCompany({ id: 1, name_display: 'Zeta GmbH', name_norm: 'zeta gmbh', app_count: 5, applications: [] }),
      makeCompany({ id: 2, name_display: 'Adatum AG', name_norm: 'adatum ag', app_count: 0, applications: [] }),
      makeCompany({ id: 3, name_display: 'Munddus Inc', name_norm: 'munddus inc', app_count: 2, applications: [] }),
    ])

    render(<CompaniesView onOpenApplication={vi.fn()} onOpenCompany={vi.fn()} />)

    await screen.findByText('Zeta GmbH')
    const names = screen.getAllByText(/GmbH|AG|Inc/).map(el => el.textContent)
    expect(names).toEqual(['Adatum AG', 'Munddus Inc', 'Zeta GmbH'])
  })
})
