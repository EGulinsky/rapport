import { describe, it, expect } from 'vitest'
import { mergeCuratedModels, formatTokenCount } from './SettingsModal'

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

  it('keeps model detail fields (context window, description) intact through the merge', () => {
    const live = [{
      model: 'gemini/gemini-2.0-flash', label: 'gemini-2.0-flash',
      description: 'Fast and versatile', context_window: 1048576, max_output_tokens: 8192,
    }]
    const curated = [{ model: 'gemini/gemini-2.0-flash', label: 'Gemini 2.0 Flash', badge: 'recommended' }]

    const result = mergeCuratedModels(live, curated)

    expect(result?.[0]).toMatchObject({
      label: 'Gemini 2.0 Flash',
      description: 'Fast and versatile',
      context_window: 1048576,
      max_output_tokens: 8192,
    })
  })
})

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
