import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { ReviewModal } from './ReviewModal'
import { api } from '../api/client'
import i18n from '../i18n'
import type { PendingMatch, ContactWithApp } from '../types'

vi.mock('../api/client', () => ({
  api: {
    review: {
      list: vi.fn(),
      count: vi.fn().mockResolvedValue({ count: 0 }),
      approve: vi.fn().mockResolvedValue({ status: 'ok', event_id: 1 }),
      reject: vi.fn().mockResolvedValue({}),
    },
    applications: {
      list: vi.fn().mockResolvedValue([]),
    },
    contacts: {
      listAll: vi.fn().mockResolvedValue([]),
    },
    companies: {
      searchLinkedIn: vi.fn(),
    },
  },
}))

function companyCandidateItem(overrides: Partial<PendingMatch> = {}): PendingMatch {
  return {
    id: 1,
    source: 'linkedin',
    confidence: 0,
    event_type: 'company_candidate',
    titel: 'Contoso GmbH & Co. KG',
    raw_content: JSON.stringify({
      company_profile_id: 42,
      candidates: [
        { name: 'Contoso GmbH', url: 'https://linkedin.com/company/contoso-gmbh', snippet: 'Software company' },
        { name: 'Contoso Consulting', url: 'https://linkedin.com/company/contoso-consulting' },
      ],
    }),
    ...overrides,
  }
}

function makeContact(overrides: Partial<ContactWithApp> = {}): ContactWithApp {
  return { id: 5, name: 'Musterfrau', vorname: 'Erika', applications: [], ...overrides }
}

describe('ReviewModal — company candidate picker shows exact name, related contacts, and live LinkedIn search', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.changeLanguage('en')
    ;(api.applications.list as ReturnType<typeof vi.fn>).mockResolvedValue([])
    ;(api.contacts.listAll as ReturnType<typeof vi.fn>).mockResolvedValue([])
  })

  it('positiv: zeigt den exakten Firmennamen (item.titel) an', async () => {
    ;(api.review.list as ReturnType<typeof vi.fn>).mockResolvedValue([companyCandidateItem()])

    render(<ReviewModal onClose={vi.fn()} onApproved={vi.fn()} />)

    expect(await screen.findByText('Contoso GmbH & Co. KG')).toBeInTheDocument()
  })

  it('positiv: lädt und zeigt verknüpfte Kontakte über company_profile_id aus raw_content', async () => {
    ;(api.review.list as ReturnType<typeof vi.fn>).mockResolvedValue([companyCandidateItem()])
    ;(api.contacts.listAll as ReturnType<typeof vi.fn>).mockResolvedValue([makeContact()])

    render(<ReviewModal onClose={vi.fn()} onApproved={vi.fn()} />)

    await waitFor(() => expect(api.contacts.listAll).toHaveBeenCalledWith({ company_profile_id: 42 }))
    expect(await screen.findByText('Erika Musterfrau')).toBeInTheDocument()
  })

  it('positiv: Live-LinkedIn-Suche liefert ein Ergebnis, das wie ein Kandidat auswählbar ist', async () => {
    ;(api.review.list as ReturnType<typeof vi.fn>).mockResolvedValue([companyCandidateItem()])
    ;(api.companies.searchLinkedIn as ReturnType<typeof vi.fn>).mockResolvedValue([
      { name: 'Contoso International', url: 'https://linkedin.com/company/contoso-international', snippet: null },
    ])

    render(<ReviewModal onClose={vi.fn()} onApproved={vi.fn()} />)

    await screen.findByText('Contoso GmbH & Co. KG')

    const input = screen.getByPlaceholderText('Company name…')
    fireEvent.change(input, { target: { value: 'Contoso Intl' } })
    fireEvent.click(screen.getByText('Search'))

    await waitFor(() => expect(api.companies.searchLinkedIn).toHaveBeenCalledWith('Contoso Intl'))
    const liveResult = await screen.findByText('Contoso International')

    fireEvent.click(liveResult)
    fireEvent.click(screen.getByText('Approve'))

    await waitFor(() => expect(api.review.approve).toHaveBeenCalledWith(1, { linkedin_url: 'https://linkedin.com/company/contoso-international' }))
  })
})
