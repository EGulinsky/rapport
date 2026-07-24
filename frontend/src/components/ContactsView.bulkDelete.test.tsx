import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { ContactsView } from './ContactsView'
import { api } from '../api/client'
import i18n from '../i18n'
import type { ContactWithApp } from '../types'

vi.mock('../api/client', () => ({
  api: {
    contacts: {
      listAll: vi.fn(),
      bulkDelete: vi.fn().mockResolvedValue({ deleted: 0 }),
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

function makeContact(overrides: Partial<ContactWithApp>): ContactWithApp {
  return {
    id: 1, name: 'Mustermann', vorname: 'Max', applications: [],
    ...overrides,
  }
}

function renderView(companyFilter?: { id: number; name: string } | null) {
  return render(
    <ContactsView
      onOpenApplication={vi.fn()}
      search=""
      onSearchChange={vi.fn()}
      companyFilter={companyFilter}
    />
  )
}

describe('ContactsView — Sammel-Löschen sendet nie ein unscoped "all"', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.changeLanguage('de')
    ;(api.companies.list as ReturnType<typeof vi.fn>).mockResolvedValue([])
    vi.spyOn(window, 'confirm').mockReturnValue(true)
  })

  it('positiv: "Alle auswählen" innerhalb eines Firmenfilters löscht nur die explizit gezeigten IDs', async () => {
    // Regression: a client-supplied "all=true" bypassed any filter (company,
    // search, applications-filter) entirely and deleted every contact on the
    // account — caused real production data loss (2026-07-10, 2026-07-21).
    // "Select all" while viewing one company's contacts must only ever send
    // that company's contact IDs, never a blanket "delete everything" flag.
    const contacts = [
      makeContact({ id: 1, name: 'Erster' }),
      makeContact({ id: 2, name: 'Zweiter' }),
    ]
    ;(api.contacts.listAll as ReturnType<typeof vi.fn>).mockResolvedValue(contacts)

    renderView({ id: 42, name: 'Contoso AG' })

    await waitFor(() => expect(api.contacts.listAll).toHaveBeenCalled())
    await screen.findByText('Erster')

    const checkboxes = screen.getAllByRole('checkbox')
    fireEvent.click(checkboxes[0]) // Kopfzeilen-Checkbox = "Alle auswählen"

    fireEvent.click(screen.getByText('2 löschen'))

    await waitFor(() => expect(api.contacts.bulkDelete).toHaveBeenCalled())

    const callArgs = (api.contacts.bulkDelete as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(callArgs).toEqual([[1, 2]])
  })

  it('positiv: einzelne Auswahl sendet nur die ausgewählten IDs', async () => {
    const contacts = [
      makeContact({ id: 1, name: 'Aachen' }),
      makeContact({ id: 2, name: 'Berger' }),
      makeContact({ id: 3, name: 'Cremer' }),
    ]
    ;(api.contacts.listAll as ReturnType<typeof vi.fn>).mockResolvedValue(contacts)

    renderView(null)

    await waitFor(() => expect(api.contacts.listAll).toHaveBeenCalled())
    await screen.findByText('Aachen')

    const checkboxes = screen.getAllByRole('checkbox')
    fireEvent.click(checkboxes[1]) // erste Datenzeile (Index 0 ist "Alle auswählen"), sortiert nach Nachname = "Aachen" (id 1)

    fireEvent.click(screen.getByText('1 löschen'))

    await waitFor(() => expect(api.contacts.bulkDelete).toHaveBeenCalled())

    expect(api.contacts.bulkDelete).toHaveBeenCalledWith([1])
  })
})
