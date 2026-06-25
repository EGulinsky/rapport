import { useState, useEffect, useCallback, useRef } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, LineChart, Line, CartesianGrid, Legend,
} from 'recharts'
import { api } from '../api/client'
import type { AnalyticsSummary, CompanySyncStatus } from '../types'

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
  const [syncing, setSyncing] = useState(false)
  const [syncMsg, setSyncMsg] = useState<string | null>(null)
  const [syncLive, setSyncLive] = useState<CompanySyncStatus | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

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

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  const startPolling = useCallback(() => {
    stopPolling()
    pollRef.current = setInterval(async () => {
      try {
        const s = await api.companySync.status()
        setSyncLive(s)
        if (!s.running) {
          if (s.pending > 0) {
            // Nächsten Batch starten
            await api.companySync.run()
          } else {
            stopPolling()
            setSyncing(false)
            load()
          }
        }
      } catch {
        stopPolling()
        setSyncing(false)
      }
    }, 1500)
  }, [stopPolling, load])

  useEffect(() => () => stopPolling(), [stopPolling])

  async function startSync() {
    setSyncing(true)
    setSyncMsg(null)
    setSyncLive(null)
    try {
      await api.companySync.resetLock()
      const r = await api.companySync.run()
      if (r.started) {
        setSyncMsg(`${r.count} Firmenprofil(e) werden synchronisiert…`)
        startPolling()
      } else {
        setSyncMsg(r.message || 'Kein Sync nötig.')
        setSyncing(false)
      }
    } catch (e) {
      setSyncMsg(e instanceof Error ? e.message : 'Fehler')
      setSyncing(false)
    }
  }

  async function resetFailed() {
    try {
      await api.companySync.resetFailed()
      await load()
      setSyncMsg('Fehlgeschlagene Profile zurückgesetzt.')
    } catch {
      setSyncMsg('Fehler beim Zurücksetzen.')
    }
  }

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

  const { kpis, funnel, by_month, by_source, hh_vs_direct, rejection_by_status, company_sync } = data
  const liveSync = syncLive ?? company_sync
  const liveTotal = (liveSync.done ?? 0) + (liveSync.pending ?? 0) + (liveSync.failed ?? 0)

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

      {/* Company Sync */}
      <div className="bg-white rounded-xl border border-gray-100 p-5">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <h2 className="text-sm font-semibold text-gray-700 mb-1">Firmendaten-Sync (KI)</h2>
            <p className="text-xs text-gray-400 mb-3">
              {liveTotal} Profile gesamt · {liveSync.done} synchronisiert · {liveSync.pending} ausstehend · {liveSync.failed} fehlgeschlagen
            </p>
            <div className="flex flex-wrap gap-2 text-sm">
              <span className="px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 text-xs font-medium">
                {liveSync.pending} ausstehend
              </span>
              <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-xs font-medium">
                {liveSync.done} fertig
              </span>
              {liveSync.failed > 0 && (
                <button
                  onClick={resetFailed}
                  className="px-2 py-0.5 rounded-full bg-red-50 text-red-700 text-xs font-medium hover:bg-red-100 transition-colors"
                >
                  {liveSync.failed} fehlgeschlagen — zurücksetzen
                </button>
              )}
            </div>
            {syncing && syncLive?.current_company && (
              <p className="text-xs text-indigo-500 mt-2 flex items-center gap-1.5">
                <span className="animate-spin inline-block h-3 w-3 border-b-2 border-indigo-400 rounded-full shrink-0" />
                <span className="truncate">{syncLive.current_company}</span>
              </p>
            )}
            {syncMsg && !syncing && (
              <p className="text-xs text-indigo-600 mt-2">{syncMsg}</p>
            )}
          </div>
          <button
            onClick={startSync}
            disabled={syncing || company_sync.pending === 0}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shrink-0"
          >
            {syncing ? (
              <span className="animate-spin inline-block h-3.5 w-3.5 border-b-2 border-white rounded-full" />
            ) : null}
            Firmendaten aktualisieren
          </button>
        </div>
        {/* Progress bar */}
        {liveTotal > 0 && (
          <div className="mt-4 space-y-1">
            <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
              <div
                className="h-full bg-emerald-500 rounded-full transition-all duration-500"
                style={{ width: `${(liveSync.done / liveTotal) * 100}%` }}
              />
            </div>
            {syncing && (
              <p className="text-xs text-gray-400 text-right">
                {liveSync.done} / {liveTotal}
              </p>
            )}
          </div>
        )}
      </div>

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
