import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { EnvironmentBanner } from './EnvironmentBanner'

describe('EnvironmentBanner', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('negativ: ohne VITE_ENV_LABEL wird nichts gerendert', () => {
    vi.stubEnv('VITE_ENV_LABEL', '')
    const { container } = render(<EnvironmentBanner />)

    expect(container).toBeEmptyDOMElement()
  })

  it('positiv: mit gesetztem VITE_ENV_LABEL wird der Text angezeigt', () => {
    vi.stubEnv('VITE_ENV_LABEL', 'TESTUMGEBUNG')
    render(<EnvironmentBanner />)

    expect(screen.getByText('TESTUMGEBUNG')).toBeInTheDocument()
  })
})
