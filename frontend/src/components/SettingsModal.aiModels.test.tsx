import { describe, it, expect } from 'vitest'
import { formatTokenCount } from './SettingsModal'

describe('formatTokenCount', () => {
  it('formats sub-thousand counts as-is', () => {
    expect(formatTokenCount(900)).toBe('900')
  })

  it('formats thousands with a K suffix', () => {
    expect(formatTokenCount(8192)).toBe('8K')
    expect(formatTokenCount(131072)).toBe('131K')
  })

  it('formats millions with an M suffix, dropping a redundant .0', () => {
    expect(formatTokenCount(1_000_000)).toBe('1M')
    expect(formatTokenCount(1_048_576)).toBe('1.0M')
    expect(formatTokenCount(2_097_152)).toBe('2.1M')
  })
})
