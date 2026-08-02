import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
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
  },
}))

const emptyEvents: ContactEvents = { calls: [], mails: [], calendar: [], messages: [] }

function makeContact(overrides: Partial<ContactWithApp> = {}): ContactWithApp {
  return {
    id: 1, name: 'Mustermann', vorname: 'Max', applications: [], ...overrides,
  }
}

function makeApp(id: number, firma: string) {
  return { id, firma, rolle: 'Dev', main_status: 'applied' as const, company_name_display: null as string | null }
}

describe('ContactModal — batch unlink of applications (mirrors app-side bulk-remove-contacts)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.changeLanguage('de')
    ;(api.contacts.getEvents as ReturnType<typeof vi.fn>).mockResolvedValue(emptyEvents)
    vi.spyOn(window, 'confirm').mockReturnValue(true)
  })

  it('positiv: ausgewählte Bewerbungen werden per Sammel-Aktion entfernt, nur die Verknüpfung — keine Löschung', async () => {
    const contact = makeContact({
      applications: [makeApp(10, 'Contoso'), makeApp(20, 'Fabrikam'), makeApp(30, 'Adatum')],
    })
    ;(api.contacts.listAll as ReturnType<typeof vi.fn>).mockResolvedValue([contact])
    ;(api.contacts.bulkUnlinkApplications as ReturnType<typeof vi.fn>).mockResolvedValue({ unlinked: 2 })

    render(<ContactModal id={1} onClose={vi.fn()} />)

    await waitFor(() => expect(api.contacts.listAll).toHaveBeenCalled())
    // "Bewerbungen" tab — apps tab is the default? Check via applications count badge
    fireEvent.click(await screen.findByText(/Bewerbungen/))

    await screen.findByText('Contoso')
    const checkboxes = screen.getAllByRole('checkbox')
    // index 0 = "select all" header checkbox, 1..n = per-application rows
    fireEvent.click(checkboxes[1]) // Contoso
    fireEvent.click(checkboxes[2]) // Fabrikam

    fireEvent.click(screen.getByText(/entfernen/))

    await waitFor(() => expect(api.contacts.bulkUnlinkApplications).toHaveBeenCalled())
    expect(api.contacts.bulkUnlinkApplications).toHaveBeenCalledWith(1, [10, 20])
  })

  it('negativ: ohne Bestätigung im confirm() wird nichts gesendet', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    const contact = makeContact({ applications: [makeApp(10, 'Contoso')] })
    ;(api.contacts.listAll as ReturnType<typeof vi.fn>).mockResolvedValue([contact])

    render(<ContactModal id={1} onClose={vi.fn()} />)

    await waitFor(() => expect(api.contacts.listAll).toHaveBeenCalled())
    fireEvent.click(await screen.findByText(/Bewerbungen/))
    await screen.findByText('Contoso')

    const checkboxes = screen.getAllByRole('checkbox')
    fireEvent.click(checkboxes[1])
    fireEvent.click(screen.getByText(/entfernen/))

    expect(api.contacts.bulkUnlinkApplications).not.toHaveBeenCalled()
  })

  it('positiv: "Alle auswählen" markiert alle verlinkten Bewerbungen', async () => {
    const contact = makeContact({
      applications: [makeApp(10, 'Contoso'), makeApp(20, 'Fabrikam')],
    })
    ;(api.contacts.listAll as ReturnType<typeof vi.fn>).mockResolvedValue([contact])

    render(<ContactModal id={1} onClose={vi.fn()} />)

    await waitFor(() => expect(api.contacts.listAll).toHaveBeenCalled())
    fireEvent.click(await screen.findByText(/Bewerbungen/))
    await screen.findByText('Contoso')

    const checkboxes = screen.getAllByRole('checkbox')
    fireEvent.click(checkboxes[0]) // header "select all"
    fireEvent.click(screen.getByText(/entfernen/))

    await waitFor(() => expect(api.contacts.bulkUnlinkApplications).toHaveBeenCalledWith(1, [10, 20]))
  })
})
