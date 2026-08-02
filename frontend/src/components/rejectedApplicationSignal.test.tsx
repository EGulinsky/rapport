import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { ContactsView } from './ContactsView'
import { ContactModal } from './ContactModal'
import { api } from '../api/client'
import i18n from '../i18n'
import type { ContactWithApp, ContactEvents } from '../types'

vi.mock('../api/client', () => ({
  api: {
    contacts: {
      listAll: vi.fn(),
      getEvents: vi.fn(),
      bulkUnlinkApplications: vi.fn().mockResolvedValue({ unlinked: 0 }),
      patch: vi.fn(),
      syncICloud: vi.fn(),
    },
    companies: {
      list: vi.fn().mockResolvedValue([]),
    },
    linkedin: {
      getConfig: vi.fn().mockResolvedValue({ configured: false }),
    },
  },
}))

const emptyEvents: ContactEvents = { calls: [], mails: [], calendar: [], messages: [] }

function makeContact(overrides: Partial<ContactWithApp>): ContactWithApp {
  return {
    id: 1, name: 'Mustermann', vorname: 'Max', applications: [],
    ...overrides,
  }
}

describe('Verlinkte Bewerbungen zeigen ein Absage-Signal (Kontakte)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.changeLanguage('de')
    ;(api.companies.list as ReturnType<typeof vi.fn>).mockResolvedValue([])
    ;(api.contacts.getEvents as ReturnType<typeof vi.fn>).mockResolvedValue(emptyEvents)
  })

  it('positiv: ContactsView-Tabelle zeigt "Absage" nur bei der abgesagten Bewerbung', async () => {
    const contact = makeContact({
      applications: [
        { id: 10, firma: 'Contoso', rolle: 'Backend', main_status: 'rejected', company_name_display: null },
        { id: 20, firma: 'Fabrikam', rolle: 'Frontend', main_status: 'applied', company_name_display: null },
      ],
    })
    ;(api.contacts.listAll as ReturnType<typeof vi.fn>).mockResolvedValue([contact])

    render(<ContactsView onOpenApplication={vi.fn()} search="" onSearchChange={vi.fn()} />)

    await screen.findByText('Contoso')
    expect(screen.getByText('Absage')).toBeInTheDocument()
    expect(screen.getAllByText('Absage')).toHaveLength(1)
  })

  it('positiv: ContactModal-Bewerbungen-Tab zeigt den vollen Status-Badge inkl. Absage', async () => {
    const contact = makeContact({
      applications: [
        { id: 10, firma: 'Contoso', rolle: 'Backend', main_status: 'rejected', company_name_display: null },
      ],
    })
    ;(api.contacts.listAll as ReturnType<typeof vi.fn>).mockResolvedValue([contact])

    render(<ContactModal id={1} onClose={vi.fn()} />)

    await waitFor(() => expect(api.contacts.listAll).toHaveBeenCalled())
    fireEvent.click(await screen.findByText(/Bewerbungen/))

    await screen.findByText('Contoso')
    expect(screen.getByTestId('status-badge-rejected')).toBeInTheDocument()
  })
})
