import { useState, useEffect, useCallback } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, LineChart, Line, CartesianGrid, Legend,
} from 'recharts'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { AnalyticsSummary } from '../types'

const COLORS = ['#6366f1', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#3b82f6', '#ef4444']
const INDIGO = '#6366f1'
const VIOLET = '#8b5cf6'
const ROSE = '#f43f5e'
const AMBER = '#f59e0b'
const EMERALD = '#10b981'

function KpiCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-gray-50 rounded-xl p-4 border border-gray-100">
      <p className="text-xs text-gray-500 font-medium mb-1">{label}</p>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
    </div>
  )
}

function SuccessByGroupChart({
  title, subtitle, groups, labelFor, minTotal = 2,
}: {
  title: string
  subtitle: string
  groups: Array<{ label: string; total: number; gespräch_rate: number; offer_rate: number }>
  labelFor?: (raw: string) => string
  minTotal?: number
}) {
  const { t } = useTranslation('analytics')
  const filtered = groups.filter(g => g.total >= minTotal)
  if (filtered.length === 0) return null

  const chartData = filtered.map(g => ({
    name: labelFor ? labelFor(g.label) : g.label,
    n: g.total,
    interview_rate: g.gespräch_rate,
    offer_rate: g.offer_rate,
  }))

  return (
    <div className="bg-white rounded-xl border border-gray-100 p-5">
      <h2 className="text-sm font-semibold text-gray-700 mb-1">{title}</h2>
      <p className="text-xs text-gray-400 mb-4">{subtitle}</p>
      <ResponsiveContainer width="100%" height={Math.max(160, chartData.length * 40)}>
        <BarChart data={chartData} layout="vertical" margin={{ left: 140, right: 40 }}>
          <XAxis type="number" hide domain={[0, 1]} />
          <YAxis
            type="category"
            dataKey="name"
            width={130}
            tick={{ fontSize: 11 }}
            tickFormatter={(name: string) => {
              const row = chartData.find(d => d.name === name)
              return row ? `${name} (n=${row.n})` : name
            }}
          />
          <Tooltip formatter={(value: number) => pct(value)} />
          <Legend />
          <Bar dataKey="interview_rate" name={t('groupChart.interviewRate')} fill={VIOLET} radius={[0, 4, 4, 0]} />
          <Bar dataKey="offer_rate" name={t('groupChart.offerRate')} fill={EMERALD} radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
      <p className="text-[11px] text-gray-400 mt-2">{t('groupChart.minTotalNote', { count: minTotal })}</p>
    </div>
  )
}

function fmt(n: number | null | undefined, digits = 0, suffix = ''): string {
  if (n === null || n === undefined) return '–'
  return n.toFixed(digits) + suffix
}

function pct(n: number): string {
  return (n * 100).toFixed(0) + '%'
}

export function AnalyticsView() {
  const { t } = useTranslation('analytics')
  const { t: tCompanies } = useTranslation('companies')
  const [data, setData] = useState<AnalyticsSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await api.analytics.summary()
      setData(result)
    } catch (e) {
      setError(e instanceof Error ? e.message : t('loadErrorTitle'))
    } finally {
      setLoading(false)
    }
  }, [t])

  useEffect(() => { load() }, [load])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center text-red-500">
          <p className="font-medium">{t('loadErrorTitle')}</p>
          <p className="text-sm mt-1">{error}</p>
          <button onClick={load} className="mt-4 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm hover:bg-indigo-700">
            {t('retry')}
          </button>
        </div>
      </div>
    )
  }

  if (!data) return null

  const {
    kpis, funnel, by_month, by_source, hh_vs_direct, rejection_by_status,
    stage_conversions, bottleneck, by_company_type, by_employee_range, by_role_category,
  } = data

  // HH vs Direct chart data
  const hhDirectData = [
    { name: t('hhVsDirect.headhunter'), total: hh_vs_direct.hh.total, gespräch: hh_vs_direct.hh.gespräch, offer: hh_vs_direct.hh.offer },
    { name: t('hhVsDirect.direct'), total: hh_vs_direct.direct.total, gespräch: hh_vs_direct.direct.gespräch, offer: hh_vs_direct.direct.offer },
  ]

  // Status donut data (by current active status)
  const statusData = funnel
    .map(f => ({ name: f.label, value: f.count }))
    .filter(d => d.value > 0)

  return (
    <div className="space-y-6">
      {/* KPI Row */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
        <KpiCard label={t('kpi.totalApplications')} value={String(kpis.total)} sub={t('kpi.totalSub', { active: kpis.active, rejected: kpis.rejected })} />
        <KpiCard label={t('kpi.active')} value={String(kpis.active)} sub={kpis.signed > 0 ? t('kpi.activeSubSigned', { count: kpis.signed }) : t('kpi.activeSubOpen')} />
        <KpiCard
          label={t('kpi.interviewRate')}
          value={pct(kpis.conversion_gespräch)}
          sub={t('kpi.interviewRateSub')}
        />
        <KpiCard
          label={t('kpi.offerRate')}
          value={pct(kpis.conversion_offer)}
          sub={t('kpi.offerRateSub')}
        />
        <KpiCard
          label={t('kpi.avgDaysToInterview')}
          value={fmt(kpis.avg_days_to_gespräch, 1)}
          sub={t('kpi.avgDaysToInterviewSub')}
        />
        <KpiCard
          label={t('kpi.ghostingRate')}
          value={pct(kpis.ghosting_rate)}
          sub={t('kpi.ghostingRateSub', { count: kpis.ghosting_count })}
        />
      </div>

      {/* Conversion Funnel */}
      <div className="bg-white rounded-xl border border-gray-100 p-5">
        <h2 className="text-sm font-semibold text-gray-700 mb-4">{t('funnel.title')}</h2>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={funnel} layout="vertical" margin={{ left: 120, right: 60 }}>
            <XAxis type="number" hide />
            <YAxis type="category" dataKey="label" width={110} tick={{ fontSize: 12 }} />
            <Tooltip
              formatter={(value: number, _name: string, props: { payload?: AnalyticsSummary['funnel'][number] }) =>
                [`${value} (${pct(props.payload?.pct ?? 0)})`, t('funnel.tooltipLabel')]
              }
            />
            <Bar dataKey="count" fill={INDIGO} radius={[0, 4, 4, 0]}>
              {funnel.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Bottleneck-Hinweis */}
      {bottleneck && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-start gap-3">
          <span className="text-2xl leading-none">🎯</span>
          <div>
            <p className="text-sm font-semibold text-amber-900">
              {t('bottleneck.title', { from: bottleneck.from_label, to: bottleneck.to_label })}
            </p>
            <p className="text-xs text-amber-700 mt-0.5">
              {t('bottleneck.description', { rate: pct(bottleneck.rate), dropOff: bottleneck.drop_off })}
            </p>
          </div>
        </div>
      )}

      {/* Stufe-zu-Stufe-Konversion */}
      {stage_conversions.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-100 p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-1">{t('stageConversion.title')}</h2>
          <p className="text-xs text-gray-400 mb-4">{t('stageConversion.subtitle')}</p>
          <ResponsiveContainer width="100%" height={Math.max(160, stage_conversions.length * 40)}>
            <BarChart
              data={stage_conversions.map(s => ({ ...s, label: `${s.from_label} → ${s.to_label}` }))}
              layout="vertical"
              margin={{ left: 170, right: 60 }}
            >
              <XAxis type="number" hide domain={[0, 1]} />
              <YAxis type="category" dataKey="label" width={160} tick={{ fontSize: 11 }} />
              <Tooltip
                formatter={(value: number, _name: string, props: { payload?: AnalyticsSummary['stage_conversions'][number] }) =>
                  [`${pct(value)} (${t('stageConversion.tooltipLost', { count: props.payload?.drop_off ?? 0 })})`, t('stageConversion.tooltipLabel')]
                }
              />
              <Bar dataKey="rate" fill={AMBER} radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Status Donut + Quelle Bar */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-white rounded-xl border border-gray-100 p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">{t('pipelineDistribution')}</h2>
          <ResponsiveContainer width="100%" height={240}>
            <PieChart>
              <Pie
                data={statusData}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={90}
                paddingAngle={2}
                dataKey="value"
                label={({ name, value }) => `${name}: ${value}`}
                labelLine={false}
              >
                {statusData.map((_entry, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-white rounded-xl border border-gray-100 p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">{t('sources')}</h2>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={by_source.slice(0, 10)} layout="vertical" margin={{ left: 80, right: 30 }}>
              <XAxis type="number" hide />
              <YAxis type="category" dataKey="source" width={75} tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="count" fill={VIOLET} radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* HH vs Direkt */}
      <div className="bg-white rounded-xl border border-gray-100 p-5">
        <h2 className="text-sm font-semibold text-gray-700 mb-1">{t('hhVsDirect.title')}</h2>
        <p className="text-xs text-gray-400 mb-4">
          {t('hhVsDirect.subtitle', { hhCount: kpis.hh_count, hhPct: pct(kpis.hh_pct), directCount: kpis.direct_count, directPct: pct(1 - kpis.hh_pct) })}
        </p>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={hhDirectData} margin={{ left: 10, right: 20 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="name" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            <Legend />
            <Bar dataKey="total" name={t('hhVsDirect.total')} fill={INDIGO} radius={[4, 4, 0, 0]} />
            <Bar dataKey="gespräch" name={t('hhVsDirect.interview')} fill={VIOLET} radius={[4, 4, 0, 0]} />
            <Bar dataKey="offer" name={t('hhVsDirect.offer')} fill={EMERALD} radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Bewerbungen über Zeit */}
      {by_month.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-100 p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">{t('overTime.title')}</h2>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={by_month} margin={{ left: 0, right: 20 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
              <Tooltip />
              <Line type="monotone" dataKey="count" name={t('overTime.name')} stroke={INDIGO} strokeWidth={2} dot={{ r: 4 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Absagen nach Phase */}
      {rejection_by_status.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-100 p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">{t('rejectionByPhase.title')}</h2>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={rejection_by_status} margin={{ left: 10, right: 20 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="count" name={t('rejectionByPhase.name')} fill={ROSE} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Erfolg nach Firmentyp / Firmengröße / Rollen-Kategorie */}
      <SuccessByGroupChart
        title={t('successByCompanyType.title')}
        subtitle={t('successByCompanyType.subtitle')}
        groups={by_company_type}
        labelFor={raw => tCompanies(`companyType.${raw}`, { defaultValue: raw })}
      />
      <SuccessByGroupChart
        title={t('successByCompanySize.title')}
        subtitle={t('successByCompanySize.subtitle')}
        groups={by_employee_range}
      />
      <SuccessByGroupChart
        title={t('successByRoleCategory.title')}
        subtitle={t('successByRoleCategory.subtitle')}
        groups={by_role_category}
        minTotal={1}
      />

      {/* Additional KPIs row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <KpiCard label={t('kpi.hhShare')} value={pct(kpis.hh_pct)} sub={t('kpi.hhShareSub', { count: kpis.hh_count })} />
        <KpiCard label={t('kpi.directShare')} value={pct(1 - kpis.hh_pct)} sub={t('kpi.directShareSub', { count: kpis.direct_count })} />
        <KpiCard
          label={t('kpi.avgDaysToRejection')}
          value={fmt(kpis.avg_days_applied_to_rejected, 1)}
          sub={t('kpi.avgDaysToRejectionSub')}
        />
        <KpiCard label={t('kpi.signed')} value={String(kpis.signed)} sub={t('kpi.signedSub')} />
      </div>

      {/* Reload */}
      <div className="flex justify-end">
        <button
          onClick={load}
          className="text-xs text-gray-400 hover:text-indigo-600 transition-colors"
        >
          {t('refresh')}
        </button>
      </div>
    </div>
  )
}
