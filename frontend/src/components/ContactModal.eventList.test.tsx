import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { EventList } from './ContactModal'
import i18n from '../i18n'
import type { ContactEventItem } from '../types'

function item(overrides: Partial<ContactEventItem> = {}): ContactEventItem {
  return {
    id: 1, application_id: 42, typ: 'gespräch',
    titel: 'Interview', ...overrides,
  }
}

const originalOpen = window.open

beforeEach(() => {
  i18n.changeLanguage('en')
  window.open = vi.fn()
})

afterEach(() => {
  window.open = originalOpen
})

describe('ContactModal EventList click behavior', () => {
  it('opens the deep link directly for a gcal entry, matching the application timeline', () => {
    const onOpenApplication = vi.fn()
    render(
      <EventList
        items={[item({ source: 'gcal', external_id: 'evt-1', external_url: 'https://www.google.com/calendar/event?eid=abc123' })]}
        emptyLabel="none"
        icon={<span />}
        locale="en"
        onOpenApplication={onOpenApplication}
      />
    )

    fireEvent.click(screen.getByText('Interview'))

    expect(window.open).toHaveBeenCalledWith('https://www.google.com/calendar/event?eid=abc123', '_blank', 'noreferrer')
    expect(onOpenApplication).not.toHaveBeenCalled()
  })

  it('opens the gmail deep link built from external_id, no external_url needed', () => {
    render(
      <EventList
        items={[item({ source: 'gmail', external_id: '19f4afd3fdcdeadb' })]}
        emptyLabel="none"
        icon={<span />}
        locale="en"
      />
    )

    fireEvent.click(screen.getByText('Interview'))

    expect(window.open).toHaveBeenCalledWith('https://mail.google.com/mail/u/0/#all/19f4afd3fdcdeadb', '_blank', 'noreferrer')
  })

  it('falls back to opening the application when the source has no deep link (e.g. a call)', () => {
    const onOpenApplication = vi.fn()
    render(
      <EventList
        items={[item({ source: 'icloud_calls', titel: 'Anruf von Natalia Kühne' })]}
        emptyLabel="none"
        icon={<span />}
        locale="en"
        onOpenApplication={onOpenApplication}
      />
    )

    fireEvent.click(screen.getByText('Anruf von Natalia Kühne'))

    expect(window.open).not.toHaveBeenCalled()
    expect(onOpenApplication).toHaveBeenCalledWith(42)
  })

  it('shows the empty-state label when there are no items', () => {
    render(<EventList items={[]} emptyLabel="Nothing here" icon={<span />} locale="en" />)

    expect(screen.getByText('Nothing here')).toBeInTheDocument()
  })
})
