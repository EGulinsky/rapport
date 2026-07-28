import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { ContactsView } from './ContactsView'
import { api } from '../api/client'
import i18n from '../i18n'

// The unscoped Sync/Re-Sync button now fires a background task and polls for
// live progress + the final result, instead of blocking on one long request
// — mirrors CompaniesView's "Sync status bar" behavior.
vi.mock('../api/client', () => ({
  api: {
    contacts: {
      listAll: vi.fn().mockResolvedValue([]),
      bulkDelete: vi.fn(),
      patch: vi.fn(),
      syncICloud: vi.fn(),
    },
    companies: {
      list: vi.fn().mockResolvedValue([]),
    },
    linkedin: {
      getConfig: vi.fn().mockResolvedValue({ configured: false }),
    },
    sync: {
      progress: vi.fn(),
      batchResults: vi.fn(),
    },
  },
}))

function renderView() {
  return render(
    <ContactsView
      onOpenApplication={vi.fn()}
      search=""
      onSearchChange={vi.fn()}
    />
  )
}

describe('ContactsView — unscoped Sync zeigt Live-Fortschritt statt zu blockieren', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.changeLanguage('de')
    ;(api.contacts.listAll as ReturnType<typeof vi.fn>).mockResolvedValue([])
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('positiv: started:true löst Polling aus, Statusleiste zeigt Live-Zahlen, verschwindet nach done', async () => {
    ;(api.contacts.syncICloud as ReturnType<typeof vi.fn>).mockResolvedValue({
      started: true, synced: [], not_found: [], errors: [],
    })
    ;(api.sync.batchResults as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ contacts_manual_sync: { done: false } })
      .mockResolvedValueOnce({ contacts_manual_sync: { done: true, synced: [1, 2], not_found: [], errors: [] } })
    ;(api.sync.progress as ReturnType<typeof vi.fn>).mockResolvedValue({
      icloud_contacts: { label: 'iCloud Kontakte', step: '3/5', current: 3, total: 5, percent: 60, done: false, created: 0, updated: 0, skipped: 0 },
    })

    renderView()
    await waitFor(() => expect(api.contacts.listAll).toHaveBeenCalled())

    // Fake timers must be active *before* the click, since startPolling()'s
    // setInterval has to be a fake timer from the moment it's created —
    // switching to fake timers after the fact leaves an uncontrolled real
    // interval running that vi.advanceTimersByTimeAsync can't reach.
    vi.useFakeTimers()

    fireEvent.click(screen.getByTestId('contacts-sync-toggle'))
    fireEvent.click(screen.getByTestId('contacts-sync-menu-sync'))

    // Flush the `await api.contacts.syncICloud(...)` microtask so its
    // continuation (checking r.started, calling startPolling()) has run.
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    expect(api.contacts.syncICloud).toHaveBeenCalledWith(false, undefined)

    // First poll tick: live progress bar shows the in-flight count.
    await act(async () => { await vi.advanceTimersByTimeAsync(1000) })
    expect(screen.getByTestId('contacts-sync-status-bar')).toBeTruthy()
    expect(screen.getByText('3/5')).toBeTruthy()

    // Second poll tick: batch result reports done — status bar clears, result message appears.
    await act(async () => { await vi.advanceTimersByTimeAsync(1000) })
    expect(screen.queryByTestId('contacts-sync-status-bar')).toBeNull()
    expect(api.contacts.listAll).toHaveBeenCalledTimes(2) // initial load + post-sync reload
  })

  it('negativ: gescopte Sync (Kontakte ausgewählt) läuft weiterhin synchron ohne Polling', async () => {
    ;(api.contacts.syncICloud as ReturnType<typeof vi.fn>).mockResolvedValue({
      synced: [1], not_found: [], errors: [],
    })
    ;(api.contacts.listAll as ReturnType<typeof vi.fn>).mockResolvedValue([
      { id: 1, name: 'Mustermann', vorname: 'Max', applications: [] },
    ])

    renderView()
    await screen.findByText('Mustermann')

    const checkboxes = screen.getAllByRole('checkbox')
    fireEvent.click(checkboxes[1]) // erste Datenzeile auswählen

    fireEvent.click(screen.getByTestId('contacts-sync-toggle'))
    fireEvent.click(screen.getByTestId('contacts-sync-menu-sync'))

    await waitFor(() => expect(api.contacts.syncICloud).toHaveBeenCalledWith(false, [1]))
    expect(api.sync.progress).not.toHaveBeenCalled()
    expect(api.sync.batchResults).not.toHaveBeenCalled()
  })
})
