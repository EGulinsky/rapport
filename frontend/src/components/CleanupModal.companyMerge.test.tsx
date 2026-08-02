import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { CleanupModal } from './CleanupModal'
import { api } from '../api/client'
import i18n from '../i18n'
import type { CleanupPreview } from '../types'

vi.mock('../api/client', () => ({
  api: {
    cleanup: {
      preview: vi.fn(),
      run: vi.fn(),
      progress: vi.fn(),
    },
    companies: {
      update: vi.fn().mockResolvedValue({}),
    },
    merge: {
      companies: vi.fn().mockResolvedValue({ success: true, winner_id: 1 }),
    },
  },
}))

function makePreview(): CleanupPreview {
  return {
    applications: [],
    contacts: [],
    companies: [
      {
        keep: { id: 1, name: 'Contoso AG', website: 'contoso.com', apps: 3, contacts: 2 },
        remove: [{ id: 2, name: 'Contoso GmbH', website: 'contoso.com', apps: 1, contacts: 0, apps_count: 1, contacts_count: 0 }],
        apps_merged: 1,
        contacts_merged: 0,
      },
    ],
    events: [],
    cross_app_events: [],
  }
}

describe('CleanupModal — company duplicate row offers Merge alongside Assign as subsidiary', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.changeLanguage('de')
    ;(api.cleanup.preview as ReturnType<typeof vi.fn>).mockResolvedValue(makePreview())
  })

  it('positiv: Klick auf "Zusammenführen" ruft api.merge.companies mit winner/loser auf', async () => {
    render(<CleanupModal onClose={vi.fn()} onDone={vi.fn()} />)

    await screen.findByText('Contoso GmbH')

    fireEvent.click(screen.getByText('Zusammenführen'))

    await waitFor(() => expect(api.merge.companies).toHaveBeenCalledWith({ winner_id: 1, loser_ids: [2] }))
  })

  it('positiv: nach erfolgreichem Merge wird die Zeile als "Zusammengeführt" markiert und die Vorschau neu geladen', async () => {
    render(<CleanupModal onClose={vi.fn()} onDone={vi.fn()} />)

    await screen.findByText('Contoso GmbH')
    const previewCallsBefore = (api.cleanup.preview as ReturnType<typeof vi.fn>).mock.calls.length

    fireEvent.click(screen.getByText('Zusammenführen'))

    await screen.findByText('Zusammengeführt')
    expect((api.cleanup.preview as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(previewCallsBefore)
  })

  it('positiv: "Als Tochterfirma zuordnen" bleibt weiterhin verfügbar und ruft api.companies.update auf', async () => {
    render(<CleanupModal onClose={vi.fn()} onDone={vi.fn()} />)

    await screen.findByText('Contoso GmbH')

    fireEvent.click(screen.getByText('Als Tochterfirma zuordnen'))

    await waitFor(() => expect(api.companies.update).toHaveBeenCalledWith(2, { parent_company_id: 1 }))
    expect(api.merge.companies).not.toHaveBeenCalled()
  })
})
