import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StatsBar } from './StatsBar'
import i18n from '../i18n'

const STATS = { total: 12, active: 7, rejected: 5, by_status: {} }

describe('StatsBar', () => {
  // Fixes the language so these assertions on exact tile-label text stay meaningful
  // regardless of the app's current pre-login default (see i18n/index.ts).
  beforeEach(() => {
    i18n.changeLanguage('de')
  })

  it('positiv: zeigt deutsche Kachel-Labels und -Werte', () => {
    render(<StatsBar stats={STATS} />)
    expect(screen.getByText('Gesamt')).toBeInTheDocument()
    expect(screen.getByText('Aktiv')).toBeInTheDocument()
    expect(screen.getByText('Abgesagt')).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()
  })

  describe('in English', () => {
    beforeEach(() => {
      i18n.changeLanguage('en')
    })

    it('shows English tile labels', () => {
      render(<StatsBar stats={STATS} />)
      expect(screen.getByText('Total')).toBeInTheDocument()
      expect(screen.getByText('Active')).toBeInTheDocument()
      expect(screen.getByText('Rejected')).toBeInTheDocument()
    })
  })
})
