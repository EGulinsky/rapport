import type { ReactNode } from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { AnalyticsView } from './AnalyticsView'
import { api } from '../api/client'
import i18n from '../i18n'
import type { AnalyticsSummary } from '../types'

vi.mock('../api/client', () => ({
  api: {
    analytics: {
      summary: vi.fn(),
    },
  },
}))

// jsdom has no ResizeObserver (recharts' ResponsiveContainer needs one) — stub the
// whole chart library with elements that just render each data point's "label" as
// plain text, which is all these tests need to assert on.
vi.mock('recharts', () => {
  const passthroughData = ({ data }: { data?: Array<{ label?: string }> }) => (
    <div>{(data ?? []).map((d, i) => <span key={i}>{d.label}</span>)}</div>
  )
  const passthroughChildren = ({ children }: { children?: ReactNode }) => <div>{children}</div>
  const nullComponent = () => null
  return {
    ResponsiveContainer: passthroughChildren,
    BarChart: passthroughData,
    LineChart: passthroughData,
    PieChart: passthroughChildren,
    Pie: passthroughData,
    Cell: nullComponent,
    Bar: nullComponent,
    Line: nullComponent,
    XAxis: nullComponent,
    YAxis: nullComponent,
    Tooltip: nullComponent,
    CartesianGrid: nullComponent,
    Legend: nullComponent,
  }
})

// analytics.py bakes a German-only "label" into funnel/rejection_by_status/by_month
// entries alongside a stable key (status/month) — the component must recompute the
// display label from that key via mainStatusLabel()/monthLabel(), not use the raw
// backend label directly, so these charts actually follow the UI language.
const SUMMARY: AnalyticsSummary = {
  kpis: {
    total: 10, active: 6, rejected: 4, signed: 1,
    ghosting_count: 0, ghosting_rate: 0,
    hh_count: 2, direct_count: 8, hh_pct: 0.2,
    conversion_gespräch: 0.5, conversion_offer: 0.1,
    avg_days_to_gespräch: null, avg_days_applied_to_rejected: null,
  },
  // The "label" values here are deliberately fake/distinctive placeholders —
  // proves the component recomputes the label from the stable "status" key
  // instead of ever rendering whatever the backend happened to send.
  funnel: [
    { status: 'applied', label: 'RAW_BACKEND_LABEL_APPLIED', count: 10, pct: 1 },
    { status: 'hr', label: 'RAW_BACKEND_LABEL_HR', count: 5, pct: 0.5 },
  ],
  by_month: [{ month: '2026-03', label: 'RAW_BACKEND_LABEL_MONTH', count: 3 }],
  by_source: [],
  hh_vs_direct: {
    hh: { total: 2, gespräch: 1, offer: 0 },
    direct: { total: 8, gespräch: 3, offer: 1 },
  },
  rejection_by_status: [{ status: 'hr', label: 'RAW_BACKEND_LABEL_HR', count: 2 }],
  company_sync: { total: 0, pending: 0, done: 0, failed: 0 },
  stage_conversions: [],
  bottleneck: null,
  by_company_type: [],
  by_employee_range: [],
  by_role_category: [],
}

describe('AnalyticsView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    ;(api.analytics.summary as ReturnType<typeof vi.fn>).mockResolvedValue(SUMMARY)
  })

  it('positiv: übersetzt Funnel- und Absage-Status-Labels statt des rohen Backend-Labels zu übernehmen', async () => {
    i18n.changeLanguage('de')
    render(<AnalyticsView />)

    await waitFor(() => expect(api.analytics.summary).toHaveBeenCalled())
    expect((await screen.findAllByText('Beworben')).length).toBeGreaterThan(0)
    expect((await screen.findAllByText('Gespräch HR/HH')).length).toBeGreaterThan(0)
    expect(screen.queryByText(/RAW_BACKEND_LABEL/)).not.toBeInTheDocument()
  })

  it('positiv: zeigt englische Status-Labels, wenn die Sprache umgeschaltet ist', async () => {
    i18n.changeLanguage('en')
    render(<AnalyticsView />)

    await waitFor(() => expect(api.analytics.summary).toHaveBeenCalled())
    expect((await screen.findAllByText('Applied')).length).toBeGreaterThan(0)
    expect((await screen.findAllByText('Interview (HR)')).length).toBeGreaterThan(0)
    expect(screen.queryByText(/RAW_BACKEND_LABEL/)).not.toBeInTheDocument()
  })
})
