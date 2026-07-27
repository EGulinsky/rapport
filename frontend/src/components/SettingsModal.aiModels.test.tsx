import { describe, it, expect } from 'vitest'
import { mergeCuratedModels } from './SettingsModal'

describe('mergeCuratedModels', () => {
  it('falls back to the curated list when there are no live models', () => {
    const curated = [{ model: 'groq/llama-3.3-70b-versatile', label: 'Llama 3.3 70B' }]

    expect(mergeCuratedModels(null, curated)).toBe(curated)
    expect(mergeCuratedModels([], curated)).toBe(curated)
  })

  it('returns null when neither live nor curated models are available', () => {
    expect(mergeCuratedModels(null, null)).toBeNull()
  })

  it('overlays curated sublabel/badge onto a live model with a matching id', () => {
    const live = [{ model: 'groq/llama-3.3-70b-versatile', label: 'llama-3.3-70b-versatile' }]
    const curated = [{
      model: 'groq/llama-3.3-70b-versatile',
      label: 'Llama 3.3 70B',
      sublabel: 'Versatile',
      badge: 'recommended',
      badgeColor: 'bg-indigo-100 text-indigo-700',
    }]

    const result = mergeCuratedModels(live, curated)

    expect(result).toEqual([{
      model: 'groq/llama-3.3-70b-versatile',
      label: 'Llama 3.3 70B',
      sublabel: 'Versatile',
      badge: 'recommended',
      badgeColor: 'bg-indigo-100 text-indigo-700',
    }])
  })

  it('keeps a live-only model as-is when it has no curated match', () => {
    const live = [{ model: 'groq/some-new-model', label: 'some-new-model' }]
    const curated = [{ model: 'groq/llama-3.3-70b-versatile', label: 'Llama 3.3 70B' }]

    const result = mergeCuratedModels(live, curated)

    expect(result).toEqual([{ model: 'groq/some-new-model', label: 'some-new-model' }])
  })

  it('prefers the curated label over the raw live id when both are present', () => {
    // The curated label is a hand-polished name (e.g. "Llama 3.3 70B");
    // the live API only ever gives back the raw model id as its label
    // (e.g. "llama-3.3-70b-versatile"), so a matched entry should read
    // like the curated suggestion, not the raw id.
    const live = [{ model: 'groq/llama-3.3-70b-versatile', label: 'llama-3.3-70b-versatile' }]
    const curated = [{ model: 'groq/llama-3.3-70b-versatile', label: 'Llama 3.3 70B', badge: 'recommended' }]

    const result = mergeCuratedModels(live, curated)

    expect(result?.[0].label).toBe('Llama 3.3 70B')
    expect(result?.[0].badge).toBe('recommended')
  })
})
