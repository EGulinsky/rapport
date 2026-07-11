import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StatusBadge } from './StatusBadge'
import i18n from '../i18n'

describe('StatusBadge', () => {
  // Fixes the language so these assertions on exact label text stay meaningful
  // regardless of the app's current pre-login default (see i18n/index.ts).
  beforeEach(() => {
    i18n.changeLanguage('de')
  })

  it('positiv: zeigt das Label des Hauptstatus', () => {
    render(<StatusBadge status="applied" />)
    expect(screen.getByText('Beworben')).toBeInTheDocument()
  })

  it('positiv: bevorzugt das Sub-Status-Label, wenn gesetzt', () => {
    render(<StatusBadge status="hr" subStatus="1_scheduled" />)
    expect(screen.getByText('1. Gespräch terminiert')).toBeInTheDocument()
  })

  it('corner case: unbekannter Sub-Status fällt auf den rohen Wert zurück statt zu crashen', () => {
    render(<StatusBadge status="hr" subStatus="unbekannter_wert" />)
    expect(screen.getByText('unbekannter_wert')).toBeInTheDocument()
  })

  it('positiv: rejected zeigt das Absage-Label', () => {
    render(<StatusBadge status="rejected" />)
    expect(screen.getByText('Absage')).toBeInTheDocument()
  })

  describe('in English', () => {
    beforeEach(() => {
      i18n.changeLanguage('en')
    })

    it('shows the English main-status label', () => {
      render(<StatusBadge status="applied" />)
      expect(screen.getByText('Applied')).toBeInTheDocument()
    })

    it('shows the English sub-status label when set', () => {
      render(<StatusBadge status="hr" subStatus="1_scheduled" />)
      expect(screen.getByText('1st interview scheduled')).toBeInTheDocument()
    })

    it('shows the English rejected label', () => {
      render(<StatusBadge status="rejected" />)
      expect(screen.getByText('Rejected')).toBeInTheDocument()
    })
  })
})
