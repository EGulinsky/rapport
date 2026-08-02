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

describe('Verlinkte Bewerbungen zeigen abgesagte Bewerbungen durchgestrichen (Kontakte)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.changeLanguage('de')
    ;(api.companies.list as ReturnType<typeof vi.fn>).mockResolvedValue([])
    ;(api.contacts.getEvents as ReturnType<typeof vi.fn>).mockResolvedValue(emptyEvents)
  })

  it('positiv: ContactsView-Tabelle streicht nur den Namen der abgesagten Bewerbung durch', async () => {
    const contact = makeContact({
      applications: [
        { id: 10, firma: 'Contoso', rolle: 'Backend', main_status: 'rejected', company_name_display: null },
        { id: 20, firma: 'Fabrikam', rolle: 'Frontend', main_status: 'applied', company_name_display: null },
      ],
    })
    ;(api.contacts.listAll as ReturnType<typeof vi.fn>).mockResolvedValue([contact])

    render(<ContactsView onOpenApplication={vi.fn()} search="" onSearchChange={vi.fn()} />)

    const rejectedName = await screen.findByText('Contoso')
    expect(rejectedName.className).toContain('line-through')
    const activeName = screen.getByText('Fabrikam')
    expect(activeName.className).not.toContain('line-through')
  })

  it('positiv: ContactModal-Bewerbungen-Tab streicht den Namen durch statt eines Status-Badges bei Absage', async () => {
    const contact = makeContact({
      applications: [
        { id: 10, firma: 'Contoso', rolle: 'Backend', main_status: 'rejected', company_name_display: null },
        { id: 20, firma: 'Fabrikam', rolle: 'Frontend', main_status: 'applied', company_name_display: null },
      ],
    })
    ;(api.contacts.listAll as ReturnType<typeof vi.fn>).mockResolvedValue([contact])

    render(<ContactModal id={1} onClose={vi.fn()} />)

    await waitFor(() => expect(api.contacts.listAll).toHaveBeenCalled())
    fireEvent.click(await screen.findByText(/Bewerbungen/))

    const rejectedName = await screen.findByText('Contoso')
    expect(rejectedName.className).toContain('line-through')
    expect(screen.queryByTestId('status-badge-rejected')).not.toBeInTheDocument()
    // the active application still gets its normal status badge
    expect(screen.getByTestId('status-badge-applied')).toBeInTheDocument()
  })
})
