import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StatusBadge } from './StatusBadge'

describe('StatusBadge', () => {
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
})
