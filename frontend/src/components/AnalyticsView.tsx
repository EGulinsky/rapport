import { useState, useEffect, useCallback } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, LineChart, Line, CartesianGrid, Legend,
} from 'recharts'
import { api } from '../api/client'
import type { AnalyticsSummary } from '../types'

const COLORS = ['#6366f1', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#3b82f6', '#ef4444']
const INDIGO = '#6366f1'
const VIOLET = '#8b5cf6'
const ROSE = '#f43f5e'
const AMBER = '#f59e0b'
const EMERALD = '#10b981'

const COMPANY_TYPE_LABELS: Record<string, string> = {
  startup:    'Startup',
  konzern:    'Konzern',
  kmu:        'KMU',
  beratung:   'Beratung',
  headhunter: 'Headhunter',
  nonprofit:  'Non-Profit',
  public:     'Öffentlich',
  other:      'Sonstiges',
}

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
  const filtered = groups.filter(g => g.total >= minTotal)
  if (filtered.length === 0) return null

  const chartData = filtered.map(g => ({
    name: labelFor ? labelFor(g.label) : g.label,
    n: g.total,
    'Gespräch-Rate': g.gespräch_rate,
    'Angebot-Rate': g.offer_rate,
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
          <Bar dataKey="Gespräch-Rate" fill={VIOLET} radius={[0, 4, 4, 0]} />
          <Bar dataKey="Angebot-Rate" fill={EMERALD} radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
      <p className="text-[11px] text-gray-400 mt-2">Gruppen mit weniger als {minTotal} Bewerbungen sind ausgeblendet (zu wenig Datenbasis).</p>
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
      setError(e instanceof Error ? e.message : 'Fehler beim Laden')
    } finally {
      setLoading(false)
    }
  }, [])

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
          <p className="font-medium">Fehler beim Laden der Auswertungen</p>
          <p className="text-sm mt-1">{error}</p>
          <button onClick={load} className="mt-4 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm hover:bg-indigo-700">
            Erneut versuchen
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
    { name: 'Headhunter', total: hh_vs_direct.hh.total, gespräch: hh_vs_direct.hh.gespräch, offer: hh_vs_direct.hh.offer },
    { name: 'Direkt', total: hh_vs_direct.direct.total, gespräch: hh_vs_direct.direct.gespräch, offer: hh_vs_direct.direct.offer },
  ]

  // Status donut data (by current active status)
  const statusData = funnel
    .map(f => ({ name: f.label, value: f.count }))
    .filter(d => d.value > 0)

  return (
    <div className="space-y-6">
      {/* KPI Row */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
        <KpiCard label="Bewerbungen gesamt" value={String(kpis.total)} sub={`${kpis.active} aktiv · ${kpis.rejected} Absagen`} />
        <KpiCard label="Aktiv" value={String(kpis.active)} sub={`${kpis.signed > 0 ? kpis.signed + ' Unterschrift' : 'Offen'}`} />
        <KpiCard
          label="Gespräch-Rate"
          value={pct(kpis.conversion_gespräch)}
          sub="Bewerb. → Gespräch"
        />
        <KpiCard
          label="Angebot-Rate"
          value={pct(kpis.conversion_offer)}
          sub="Bewerb. → Angebot"
        />
        <KpiCard
          label="Ø Tage bis Gespräch"
          value={fmt(kpis.avg_days_to_gespräch, 1)}
          sub="ab Bewerbungsdatum"
        />
        <KpiCard
          label="Ghosting-Quote"
          value={pct(kpis.ghosting_rate)}
          sub={`${kpis.ghosting_count} Bewerbungen`}
        />
      </div>

      {/* Conversion Funnel */}
      <div className="bg-white rounded-xl border border-gray-100 p-5">
        <h2 className="text-sm font-semibold text-gray-700 mb-4">Conversion-Funnel</h2>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={funnel} layout="vertical" margin={{ left: 120, right: 60 }}>
            <XAxis type="number" hide />
            <YAxis type="category" dataKey="label" width={110} tick={{ fontSize: 12 }} />
            <Tooltip
              formatter={(value: number, _name: string, props: { payload?: AnalyticsSummary['funnel'][number] }) =>
                [`${value} (${pct(props.payload?.pct ?? 0)})`, 'Bewerbungen']
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
              Größter Engpass: {bottleneck.from_label} → {bottleneck.to_label}
            </p>
            <p className="text-xs text-amber-700 mt-0.5">
              Nur {pct(bottleneck.rate)} kommen weiter — {bottleneck.drop_off} Bewerbungen bleiben in dieser Phase hängen. Das ist der größte absolute Verlust in der Pipeline.
            </p>
          </div>
        </div>
      )}

      {/* Stufe-zu-Stufe-Konversion */}
      {stage_conversions.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-100 p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-1">Konversion je Übergang</h2>
          <p className="text-xs text-gray-400 mb-4">Anteil, der von einer Stufe zur nächsten kommt (nicht kumulativ) — zeigt, wo genau die Pipeline stockt.</p>
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
                  [`${pct(value)} (${props.payload?.drop_off ?? 0} verloren)`, 'Konversion']
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
          <h2 className="text-sm font-semibold text-gray-700 mb-4">Pipeline-Verteilung</h2>
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
          <h2 className="text-sm font-semibold text-gray-700 mb-4">Quellen</h2>
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
        <h2 className="text-sm font-semibold text-gray-700 mb-1">Headhunter vs. Direkt</h2>
        <p className="text-xs text-gray-400 mb-4">
          HH: {kpis.hh_count} ({pct(kpis.hh_pct)}) · Direkt: {kpis.direct_count} ({pct(1 - kpis.hh_pct)})
        </p>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={hhDirectData} margin={{ left: 10, right: 20 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="name" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            <Legend />
            <Bar dataKey="total" name="Gesamt" fill={INDIGO} radius={[4, 4, 0, 0]} />
            <Bar dataKey="gespräch" name="Gespräch" fill={VIOLET} radius={[4, 4, 0, 0]} />
            <Bar dataKey="offer" name="Angebot" fill={EMERALD} radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Bewerbungen über Zeit */}
      {by_month.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-100 p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">Bewerbungen über Zeit (letzte 12 Monate)</h2>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={by_month} margin={{ left: 0, right: 20 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
              <Tooltip />
              <Line type="monotone" dataKey="count" name="Bewerbungen" stroke={INDIGO} strokeWidth={2} dot={{ r: 4 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Absagen nach Phase */}
      {rejection_by_status.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-100 p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">Absagen nach Phase</h2>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={rejection_by_status} margin={{ left: 10, right: 20 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="count" name="Absagen" fill={ROSE} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Erfolg nach Firmentyp / Firmengröße / Rollen-Kategorie */}
      <SuccessByGroupChart
        title="Erfolg nach Firmentyp"
        subtitle="Gespräch-/Angebotsquote je Firmenart (Startup/Konzern/KMU/…)"
        groups={by_company_type}
        labelFor={raw => COMPANY_TYPE_LABELS[raw] ?? raw}
      />
      <SuccessByGroupChart
        title="Erfolg nach Firmengröße"
        subtitle="Gespräch-/Angebotsquote je Mitarbeiterzahl-Bereich"
        groups={by_employee_range}
      />
      <SuccessByGroupChart
        title="Erfolg nach Rollen-Kategorie"
        subtitle='Grobe Einordnung aus dem Stellentitel (Keyword-Heuristik, kein strukturiertes Feld) — "Führung": Lead/Head/Director/Manager/Leitung; "Senior (Fachexperte)": Senior/Principal/Architekt; sonst "Sonstige"'
        groups={by_role_category}
        minTotal={1}
      />

      {/* Additional KPIs row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <KpiCard label="HH-Anteil" value={pct(kpis.hh_pct)} sub={`${kpis.hh_count} über Headhunter`} />
        <KpiCard label="Direkt-Anteil" value={pct(1 - kpis.hh_pct)} sub={`${kpis.direct_count} direkt`} />
        <KpiCard
          label="Ø Tage bis Absage"
          value={fmt(kpis.avg_days_applied_to_rejected, 1)}
          sub="ab Bewerbungsdatum"
        />
        <KpiCard label="Unterschriften" value={String(kpis.signed)} sub="Angebot angenommen" />
      </div>

      {/* Reload */}
      <div className="flex justify-end">
        <button
          onClick={load}
          className="text-xs text-gray-400 hover:text-indigo-600 transition-colors"
        >
          Aktualisieren
        </button>
      </div>
    </div>
  )
}
