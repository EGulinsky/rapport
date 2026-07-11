import { useState, useEffect, useCallback } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { api } from '../api/client'
import { MAIN_STATUS_COLORS } from '../types'
import type { CalendarEvent, MainStatus } from '../types'
import { useStatusLabels } from '../i18n/statusLabels'
import { useLocale } from '../i18n/useLocale'
import clsx from 'clsx'

type CalView = 'day' | 'workweek' | 'week' | 'month'

const VIEW_LABELS: Record<CalView, string> = {
  day: 'Tag',
  workweek: 'Arbeitswoche',
  week: 'Woche',
  month: 'Monat',
}

const SOURCE_ICON: Record<string, string> = {
  gcal: '📅', icloud_cal: '📅',
  gmail: '✉️', icloud_mail: '✉️',
  call: '📞', linkedin: '🔗', notes: '📝',
}
const TYP_ICON: Record<string, string> = {
  interview: '🎤', phone: '📞', mail: '✉️', note: '📝', status: '⚡',
}
function icon(e: CalendarEvent) {
  return SOURCE_ICON[e.source ?? ''] ?? TYP_ICON[e.typ] ?? '📌'
}

// ── Date helpers ────────────────────────────────────────────────────────────

function dateStr(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function addDays(d: Date, n: number) {
  const r = new Date(d)
  r.setDate(r.getDate() + n)
  return r
}

function mondayOf(d: Date): Date {
  const day = d.getDay()
  const r = new Date(d)
  r.setDate(d.getDate() - (day === 0 ? 6 : day - 1))
  r.setHours(0, 0, 0, 0)
  return r
}

function getDays(view: CalView, anchor: Date): Date[] {
  if (view === 'day') return [anchor]
  const mon = mondayOf(anchor)
  return Array.from({ length: view === 'workweek' ? 5 : 7 }, (_, i) => addDays(mon, i))
}

function monthGrid(d: Date): Date[] {
  const first = new Date(d.getFullYear(), d.getMonth(), 1)
  const start = mondayOf(first)
  return Array.from({ length: 42 }, (_, i) => addDays(start, i))
}

function rangeFor(view: CalView, anchor: Date): { from: Date; to: Date } {
  if (view === 'month') {
    const first = new Date(anchor.getFullYear(), anchor.getMonth(), 1)
    const from = mondayOf(first)
    return { from, to: addDays(from, 41) }
  }
  const days = getDays(view, anchor)
  return { from: days[0], to: days[days.length - 1] }
}

function navTitle(view: CalView, anchor: Date, locale: string): string {
  const fmt = (d: Date, opts: Intl.DateTimeFormatOptions) => d.toLocaleDateString(locale, opts)
  if (view === 'day') return fmt(anchor, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
  if (view === 'month') return fmt(anchor, { month: 'long', year: 'numeric' })
  const days = getDays(view, anchor)
  const first = days[0]
  const last = days[days.length - 1]
  if (first.getMonth() === last.getMonth())
    return `${fmt(first, { day: 'numeric' })}. – ${fmt(last, { day: 'numeric', month: 'long', year: 'numeric' })}`
  return `${fmt(first, { day: 'numeric', month: 'short' })} – ${fmt(last, { day: 'numeric', month: 'short', year: 'numeric' })}`
}

function nav(view: CalView, anchor: Date, dir: -1 | 1): Date {
  const d = new Date(anchor)
  if (view === 'day') { d.setDate(d.getDate() + dir); return d }
  if (view === 'month') { d.setMonth(d.getMonth() + dir); return d }
  d.setDate(d.getDate() + dir * 7)
  return d
}

// ── Event chip ──────────────────────────────────────────────────────────────

function EventChip({ e, compact, onClick }: {
  e: CalendarEvent
  compact?: boolean
  onClick: (ev: CalendarEvent) => void
}) {
  const { mainStatusLabel } = useStatusLabels()
  const color = MAIN_STATUS_COLORS[e.main_status as MainStatus] ?? 'bg-gray-100 text-gray-700'
  const label = e.titel ?? `${e.firma} – ${e.rolle}`
  return (
    <button
      onClick={() => onClick(e)}
      title={`${e.firma} · ${e.rolle}\n${mainStatusLabel(e.main_status)}${e.notiz ? '\n' + e.notiz : ''}`}
      className={clsx(
        'w-full text-left rounded px-1.5 leading-tight font-medium truncate transition-opacity hover:opacity-80',
        compact ? 'py-px text-[10px]' : 'py-0.5 text-[11px]',
        color,
      )}
    >
      <span className="mr-0.5">{icon(e)}</span>{label}
    </button>
  )
}

// ── Month view ──────────────────────────────────────────────────────────────

const WD_SHORT = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']

function MonthView({ anchor, today, byDate, onSelect }: {
  anchor: Date
  today: string
  byDate: Record<string, CalendarEvent[]>
  onSelect: (e: CalendarEvent) => void
}) {
  const locale = useLocale()
  const grid = monthGrid(anchor)
  const curMonth = anchor.getMonth()

  return (
    <div className="flex flex-col">
      <div className="grid grid-cols-7 border-b border-gray-200">
        {WD_SHORT.map(d => (
          <div key={d} className="py-2 text-center text-xs font-semibold text-gray-500 uppercase tracking-wide">{d}</div>
        ))}
      </div>
      <div className="grid grid-cols-7" style={{ minHeight: 500 }}>
        {grid.map((day, i) => {
          const iso = dateStr(day)
          const isToday = iso === today
          const thisMon = day.getMonth() === curMonth
          const evs = byDate[iso] ?? []
          const visible = evs.slice(0, 3)
          const overflow = evs.length - 3
          return (
            <div
              key={iso}
              className={clsx(
                'border-b border-r border-gray-100 p-1 min-h-[90px]',
                !thisMon && 'bg-gray-50/60',
                i % 7 === 6 && 'border-r-0',
              )}
            >
              <div className="flex justify-end mb-1">
                <span className={clsx(
                  'text-xs font-medium w-6 h-6 flex items-center justify-center rounded-full',
                  isToday ? 'bg-indigo-600 text-white' : thisMon ? 'text-gray-700' : 'text-gray-400',
                )}>
                  {day.getDate()}
                </span>
              </div>
              <div className="space-y-0.5">
                {visible.map(e => <EventChip key={e.id} e={e} compact onClick={onSelect} />)}
                {overflow > 0 && <p className="text-[10px] text-gray-400 pl-1">+{overflow} weitere</p>}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Week / Workweek / Day view ──────────────────────────────────────────────

function WeekView({ days, today, byDate, onSelect }: {
  days: Date[]
  today: string
  byDate: Record<string, CalendarEvent[]>
  onSelect: (e: CalendarEvent) => void
}) {
  const locale = useLocale()
  const cols = days.length
  return (
    <div className="flex flex-col">
      {/* Day headers */}
      <div className="grid border-b border-gray-200" style={{ gridTemplateColumns: `repeat(${cols}, 1fr)` }}>
        {days.map(day => {
          const iso = dateStr(day)
          const isToday = iso === today
          const wd = WD_SHORT[(day.getDay() + 6) % 7]
          return (
            <div key={iso} className={clsx('py-3 text-center border-r border-gray-100 last:border-r-0', isToday && 'bg-indigo-50/40')}>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">{wd}</p>
              <p className={clsx('mx-auto mt-1 w-8 h-8 flex items-center justify-center rounded-full text-sm font-semibold',
                isToday ? 'bg-indigo-600 text-white' : 'text-gray-800')}>
                {day.getDate()}
              </p>
              <p className="text-[10px] text-gray-400 mt-0.5">
                {day.toLocaleDateString(locale, { month: 'short' })}
              </p>
            </div>
          )
        })}
      </div>
      {/* Event columns — fixed height, each column scrolls independently */}
      <div className="grid divide-x divide-gray-100" style={{ gridTemplateColumns: `repeat(${cols}, 1fr)`, height: cols === 1 ? 'auto' : 360 }}>
        {days.map(day => {
          const iso = dateStr(day)
          const isToday = iso === today
          const evs = byDate[iso] ?? []
          return (
            <div key={iso} className={clsx('p-2 space-y-1.5 overflow-y-auto h-full', isToday && 'bg-indigo-50/20')}>
              {evs.length === 0 && <p className="text-[11px] text-gray-300 text-center mt-6">–</p>}
              {evs.map(e => (
                <div key={e.id} className="space-y-0.5">
                  <EventChip e={e} onClick={onSelect} />
                  {cols === 1 && e.notiz && (
                    <p className="text-[11px] text-gray-500 px-1.5 line-clamp-3">{e.notiz}</p>
                  )}
                </div>
              ))}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Detail modal ─────────────────────────────────────────────────────────────

function DetailModal({ e, onClose, onOpenApp }: {
  e: CalendarEvent
  onClose: () => void
  onOpenApp: (id: number) => void
}) {
  const { mainStatusLabel } = useStatusLabels()
  const color = MAIN_STATUS_COLORS[e.main_status as MainStatus] ?? 'bg-gray-100 text-gray-700'
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/20" />
      <div
        className="relative bg-white rounded-xl shadow-2xl w-full max-w-sm p-5 space-y-3"
        onClick={ev => ev.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="font-semibold text-gray-900">{e.firma}</p>
            <p className="text-sm text-gray-500">{e.rolle}</p>
          </div>
          <span className={clsx('text-xs font-medium rounded px-2 py-0.5 shrink-0', color)}>
            {mainStatusLabel(e.main_status)}
          </span>
        </div>

        {e.titel && (
          <p className="text-sm font-medium text-gray-800">{icon(e)} {e.titel}</p>
        )}

        <div className="flex flex-wrap gap-3 text-xs text-gray-500">
          <span>📅 {e.datum}</span>
          {e.source && <span className="capitalize">{e.source}</span>}
          {e.typ && e.typ !== 'gcal' && <span>{e.typ}</span>}
          {e.autor && <span>von {e.autor}</span>}
        </div>

        {e.notiz && (
          <p className="text-sm text-gray-600 bg-gray-50 rounded-lg p-3 whitespace-pre-wrap max-h-48 overflow-y-auto">
            {e.notiz}
          </p>
        )}

        <button
          onClick={() => onOpenApp(e.application_id)}
          className="w-full rounded-lg bg-indigo-600 text-white text-sm font-medium py-2 hover:bg-indigo-700 transition-colors"
        >
          Bewerbung öffnen →
        </button>
      </div>
    </div>
  )
}

// ── Main export ──────────────────────────────────────────────────────────────

interface Props {
  onOpenApplication: (id: number) => void
}

export function CalendarView({ onOpenApplication }: Props) {
  const { mainStatusLabel } = useStatusLabels()
  const locale = useLocale()
  const [view, setView] = useState<CalView>('month')
  const [anchor, setAnchor] = useState<Date>(() => {
    const d = new Date()
    d.setHours(0, 0, 0, 0)
    return d
  })
  const [events, setEvents] = useState<CalendarEvent[]>([])
  const [loading, setLoading] = useState(false)
  const [detail, setDetail] = useState<CalendarEvent | null>(null)

  const { from, to } = rangeFor(view, anchor)
  const fromStr = dateStr(from)
  const toStr = dateStr(to)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setEvents(await api.calendar.events(fromStr, toStr))
    } finally {
      setLoading(false)
    }
  }, [fromStr, toStr])

  useEffect(() => { load() }, [load])

  const today = dateStr(new Date())

  const byDate = events.reduce<Record<string, CalendarEvent[]>>((acc, e) => {
    if (e.datum) (acc[e.datum] ??= []).push(e)
    return acc
  }, {})

  function openDetail(e: CalendarEvent) { setDetail(e) }

  function openApp(id: number) {
    setDetail(null)
    onOpenApplication(id)
  }

  const days = view !== 'month' ? getDays(view, anchor) : []

  return (
    <>
      <div className="flex flex-col gap-4">
        {/* Toolbar */}
        <div className="flex items-center justify-between bg-white rounded-xl border border-gray-200 px-4 py-2.5">
          <div className="flex items-center gap-2">
            <button
              onClick={() => { const d = new Date(); d.setHours(0,0,0,0); setAnchor(d) }}
              className="px-2.5 py-1 text-xs rounded border border-gray-200 hover:bg-gray-50 text-gray-600 font-medium"
            >
              Heute
            </button>
            <button onClick={() => setAnchor(nav(view, anchor, -1))} className="p-1 rounded hover:bg-gray-100 text-gray-500">
              <ChevronLeft className="h-4 w-4" />
            </button>
            <button onClick={() => setAnchor(nav(view, anchor, 1))} className="p-1 rounded hover:bg-gray-100 text-gray-500">
              <ChevronRight className="h-4 w-4" />
            </button>
            <span className="text-sm font-semibold text-gray-900 ml-1">{navTitle(view, anchor, locale)}</span>
            {loading && <span className="text-xs text-gray-400 ml-2 animate-pulse">Lädt…</span>}
          </div>

          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-400">{events.length} Termine</span>
            <div className="flex rounded-lg border border-gray-200 overflow-hidden">
              {(['day', 'workweek', 'week', 'month'] as CalView[]).map(v => (
                <button
                  key={v}
                  onClick={() => setView(v)}
                  className={clsx(
                    'px-3 py-1.5 text-xs font-medium transition-colors',
                    view === v ? 'bg-indigo-600 text-white' : 'text-gray-600 hover:bg-gray-50',
                  )}
                >
                  {VIEW_LABELS[v]}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Calendar */}
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          {view === 'month' ? (
            <MonthView anchor={anchor} today={today} byDate={byDate} onSelect={openDetail} />
          ) : (
            <WeekView days={days} today={today} byDate={byDate} onSelect={openDetail} />
          )}
        </div>

        {/* Status legend */}
        <div className="flex flex-wrap gap-2 px-1">
          {(['applied', 'hr', 'fb', 'waiting', 'negotiating', 'signed', 'rejected'] as MainStatus[]).map(s => (
            <span key={s} className={clsx('text-[10px] rounded-full px-2 py-0.5 font-medium', MAIN_STATUS_COLORS[s])}>
              {mainStatusLabel(s)}
            </span>
          ))}
        </div>
      </div>

      {detail && (
        <DetailModal e={detail} onClose={() => setDetail(null)} onOpenApp={openApp} />
      )}
    </>
  )
}
