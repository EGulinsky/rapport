import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { ContactsView } from './ContactsView'
import { CompaniesView } from './CompaniesView'
import { api } from '../api/client'
import i18n from '../i18n'
import type { ContactWithApp, CompanyProfile } from '../types'

vi.mock('../api/client', () => ({
  api: {
    contacts: {
      listAll: vi.fn(),
      patch: vi.fn(),
      syncICloud: vi.fn(),
    },
    companies: {
      list: vi.fn(),
    },
    linkedin: {
      getConfig: vi.fn().mockResolvedValue({ configured: false }),
    },
  },
}))

function makeContact(overrides: Partial<ContactWithApp>): ContactWithApp {
  return {
    id: 1, name: 'Mustermann', vorname: 'Max', applications: [],
    ...overrides,
  }
}

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
    hq_city: null,
    hq_country: null,
    website: null,
    linkedin_company_url: null,
    description: null,
    sync_source: null,
    sync_status: 'done',
    sync_error: null,
    last_synced_at: null,
    app_count: 0,
    ...overrides,
  }
}

describe('Applications-Filter "Aktiv" (Kontakte)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.changeLanguage('de')
    ;(api.companies.list as ReturnType<typeof vi.fn>).mockResolvedValue([])
  })

  it('positiv: "Aktiv" zeigt nur Kontakte mit mindestens einer nicht abgesagten Bewerbung', async () => {
    const contacts = [
      makeContact({ id: 1, name: 'NurAbsage', applications: [{ id: 10, firma: 'A', rolle: 'X', main_status: 'rejected', company_name_display: null }] }),
      makeContact({ id: 2, name: 'MitAktiver', applications: [{ id: 20, firma: 'B', rolle: 'Y', main_status: 'applied', company_name_display: null }] }),
      makeContact({ id: 3, name: 'OhneBewerbung', applications: [] }),
    ]
    ;(api.contacts.listAll as ReturnType<typeof vi.fn>).mockResolvedValue(contacts)

    render(<ContactsView onOpenApplication={vi.fn()} search="" onSearchChange={vi.fn()} />)

    await screen.findByText('NurAbsage')
    fireEvent.click(screen.getByText('Aktiv'))

    await waitFor(() => {
      expect(screen.queryByText('NurAbsage')).not.toBeInTheDocument()
      expect(screen.queryByText('OhneBewerbung')).not.toBeInTheDocument()
    })
    expect(screen.getByText('MitAktiver')).toBeInTheDocument()
  })
})

describe('Applications-Filter "Aktiv" (Firmen)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.changeLanguage('de')
  })

  it('positiv: "Aktiv" zeigt nur Firmen mit mindestens einer nicht abgesagten Bewerbung', async () => {
    ;(api.companies.list as ReturnType<typeof vi.fn>).mockResolvedValue([
      makeCompany({
        id: 1, name_display: 'NurAbsage GmbH', name_norm: 'nurabsage gmbh', app_count: 1,
        applications: [{ id: 10, firma: 'NurAbsage GmbH', rolle: 'X', main_status: 'rejected' }],
      }),
      makeCompany({
        id: 2, name_display: 'MitAktiver AG', name_norm: 'mitaktiver ag', app_count: 1,
        applications: [{ id: 20, firma: 'MitAktiver AG', rolle: 'Y', main_status: 'applied' }],
      }),
      makeCompany({ id: 3, name_display: 'OhneBewerbung KG', name_norm: 'ohnebewerbung kg', app_count: 0, applications: [] }),
    ])

    render(<CompaniesView onOpenApplication={vi.fn()} onOpenCompany={vi.fn()} />)

    await screen.findByText('NurAbsage GmbH')
    fireEvent.click(screen.getByText('Aktiv'))

    await waitFor(() => {
      expect(screen.queryByText('NurAbsage GmbH')).not.toBeInTheDocument()
      expect(screen.queryByText('OhneBewerbung KG')).not.toBeInTheDocument()
    })
    expect(screen.getByText('MitAktiver AG')).toBeInTheDocument()
  })
})
