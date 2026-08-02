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
})
