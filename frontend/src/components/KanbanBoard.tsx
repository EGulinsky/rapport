import { useState } from 'react'
import {
  DndContext, DragEndEvent, DragOverlay, DragStartEvent,
  PointerSensor, useSensor, useSensors,
  useDroppable, useDraggable,
} from '@dnd-kit/core'
import { CSS } from '@dnd-kit/utilities'
import { useTranslation } from 'react-i18next'
import { MapPin, AlertTriangle, Wallet } from 'lucide-react'
import { StatusBadge } from './StatusBadge'
import { CompanyLogo } from './CompanyLogo'
import { MAIN_STATUS_COLORS, SUB_STATUS_SEQUENCE, type MainStatus } from '../types'
import { useStatusLabels } from '../i18n/statusLabels'
import { useLocale } from '../i18n/useLocale'
import { formatDate } from '../i18n/formatDate'
import { formatSalaryRange } from '../utils/salaryFormat'
import { formatDriveDistance } from '../utils/distanceFormat'

const SUB_ORDER = Object.fromEntries(SUB_STATUS_SEQUENCE.map((s, i) => [s, i]))
import type { Application } from '../types'
import { api } from '../api/client'
import clsx from 'clsx'

interface Props {
  columns: { status: MainStatus; items: Application[] }[]
  onSelect: (id: number) => void
  onChanged: () => void
  onOpenCompany?: (id: number) => void
  updatedIds?: Set<number>
}

function KanbanCard({ app, isDragging, onOpenCompany, isUpdated }: { app: Application; isDragging?: boolean; onOpenCompany?: (id: number) => void; isUpdated?: boolean }) {
  const { subStatusLabel } = useStatusLabels()
  const locale = useLocale()
  const { t } = useTranslation('applications')
  return (
    <div className={clsx(
      'relative w-full text-left rounded-xl border bg-white p-3 shadow-sm',
      app.abgesagt
        ? 'border-l-4 border-l-red-300 border-gray-200 opacity-60 bg-rose-50/20'
        : 'border-gray-200',
      isDragging ? 'opacity-50 shadow-lg rotate-1' : (!app.abgesagt && 'hover:border-indigo-300 hover:shadow-md transition-all')
    )}>
      {isUpdated && (
        <span className="absolute top-2 right-2 h-2 w-2 rounded-full bg-indigo-500 ring-2 ring-white animate-pulse" />
      )}
      {app.abgesagt && (
        <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold bg-red-100 text-red-600 mb-1.5">
          Abgesagt
        </span>
      )}
      <div className="flex items-start gap-2">
        <div className="mt-0.5 shrink-0">
          {app.is_headhunter ? (
            <CompanyLogo name={(app.target_company_name_display ?? app.zielfirma_bei_hh) || (app.company_name_display ?? app.firma)} website={app.target_company_website ?? app.company_website} size="sm" />
          ) : (
            <CompanyLogo name={app.company_name_display ?? app.firma} website={app.company_website} size="sm" />
          )}
        </div>
        <div className="min-w-0">
          {app.is_headhunter ? (
            <>
              <div className="flex items-center gap-1 mb-0.5">
                <span className="inline-flex items-center rounded px-1 py-0.5 text-[10px] font-semibold bg-indigo-100 text-indigo-700 shrink-0">HH</span>
                {app.company_profile_id && onOpenCompany ? (
                  <button
                    onClick={e => { e.stopPropagation(); onOpenCompany(app.company_profile_id!) }}
                    className="text-xs text-indigo-700 truncate leading-tight cursor-pointer hover:text-indigo-600 hover:underline"
                  >{app.company_name_display ?? app.firma}</button>
                ) : (
                  <span className="text-xs text-indigo-700 truncate leading-tight">{app.company_name_display ?? app.firma}</span>
                )}
              </div>
              {app.zielfirma_bei_hh ? (
                app.target_company_profile_id && onOpenCompany ? (
                  <button
                    onClick={e => { e.stopPropagation(); onOpenCompany(app.target_company_profile_id!) }}
                    className="font-medium text-sm text-gray-900 leading-tight cursor-pointer hover:text-indigo-600 hover:underline"
                  >{app.target_company_name_display ?? app.zielfirma_bei_hh}</button>
                ) : (
                  <p className="font-medium text-sm text-gray-900 leading-tight">{app.target_company_name_display ?? app.zielfirma_bei_hh}</p>
                )
              ) : (
                <span className="text-gray-400 italic text-xs">Zielfirma unbekannt</span>
              )}
            </>
          ) : (
            app.company_profile_id && onOpenCompany ? (
              <button
                onClick={e => { e.stopPropagation(); onOpenCompany(app.company_profile_id!) }}
                className={clsx('font-medium text-sm leading-tight cursor-pointer hover:text-indigo-600 hover:underline', app.abgesagt ? 'text-gray-500 line-through decoration-red-300' : 'text-gray-900')}
              >{app.company_name_display ?? app.firma}</button>
            ) : (
              <p className={clsx('font-medium text-sm leading-tight', app.abgesagt ? 'text-gray-500 line-through decoration-red-300' : 'text-gray-900')}>
                {app.company_name_display ?? app.firma}
              </p>
            )
          )}
          <p className="text-xs text-gray-500 mt-0.5 leading-tight">{app.rolle}</p>
        </div>
      </div>
      <p className="text-[10px] text-gray-300 font-mono mt-0.5 select-all leading-tight">{app.id}</p>
      {app.sub_status && (
        <p className="text-xs text-gray-400 mt-1">{subStatusLabel(app.sub_status)}</p>
      )}
      {app.ghosting && <span className="text-xs">👻</span>}
      {app.salary_expectation_min != null && (
        <p className={clsx(
          'flex items-center gap-1 text-[10px] mt-1 leading-tight font-medium',
          app.salary_mismatch ? 'text-red-600' : 'text-gray-500'
        )}>
          <Wallet className="h-2.5 w-2.5 shrink-0" />
          <span className="truncate">
            {formatSalaryRange(app.salary_expectation_min, app.salary_expectation_max, app.salary_currency, locale)}
          </span>
          {app.salary_mismatch && (
            <span title={t('salary.mismatchWarning')} className="shrink-0">
              <AlertTriangle className="h-3 w-3 text-red-500" />
            </span>
          )}
        </p>
      )}
      {!app.abgesagt && app.ai_color && (
        <div className="mt-1.5 space-y-0.5">
          <div className="flex items-center gap-1.5">
            <span className={clsx(
              'shrink-0 h-2 w-2 rounded-full',
              app.ai_color === 'green' ? 'bg-green-500' :
              app.ai_color === 'red'   ? 'bg-red-500'   : 'bg-yellow-400'
            )} />
            <span className={clsx(
              'text-[10px] font-semibold',
              app.ai_color === 'green' ? 'text-green-700' :
              app.ai_color === 'red'   ? 'text-red-700'   : 'text-yellow-700'
            )}>
              {app.ai_color === 'green' ? 'Hoch' : app.ai_color === 'red' ? 'Niedrig' : 'Mittel'}
            </span>
          </div>
          {app.ai_next_step && (
            <p className="text-[10px] leading-tight text-gray-500">{app.ai_next_step}</p>
          )}
        </div>
      )}
      {!app.abgesagt && app.naechster_schritt && (
        <p className={`text-[10px] mt-1.5 leading-tight font-medium ${
          app.naechster_schritt.startsWith('Gespräch') ? 'text-indigo-600' :
          app.naechster_schritt.startsWith('Kein Feedback') || app.naechster_schritt.startsWith('Keine Reaktion') ? 'text-orange-600' :
          app.naechster_schritt.startsWith('Evtl.') || app.naechster_schritt.startsWith('Feedback aus') ? 'text-yellow-600' :
          'text-gray-500'
        }`}>
          → {app.naechster_schritt}
        </p>
      )}
      {(app.letztes_update || app.datum_bewerbung || app.ort) && (
        <div className="flex items-center justify-between gap-2 mt-2 pt-2 border-t border-gray-100">
          <p className="text-[10px] text-gray-400 shrink-0">
            {app.letztes_update
              ? formatDate(app.letztes_update, locale)
              : app.datum_bewerbung ? formatDate(app.datum_bewerbung, locale) : ''}
          </p>
          {app.ort && (
            <a
              href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(app.ort)}`}
              target="_blank"
              rel="noopener noreferrer"
              onClick={e => e.stopPropagation()}
              title={app.ort}
              className="inline-flex items-center gap-0.5 text-[10px] text-indigo-500 hover:text-indigo-700 hover:underline truncate min-w-0"
            >
              <MapPin className="h-2.5 w-2.5 shrink-0" />
              <span className="truncate">{app.ort}</span>
              {app.drive_distance_km != null && app.drive_duration_min != null && (
                <span className="shrink-0 text-indigo-400">
                  · {formatDriveDistance(app.drive_distance_km, app.drive_duration_min)}
                </span>
              )}
            </a>
          )}
        </div>
      )}
    </div>
  )
}

function DraggableCard({ app, onSelect, onOpenCompany, updatedIds }: { app: Application; onSelect: (id: number) => void; onOpenCompany?: (id: number) => void; updatedIds?: Set<number> }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: app.id })
  const style = transform ? { transform: CSS.Translate.toString(transform) } : undefined

  return (
    <div ref={setNodeRef} style={style} {...listeners} {...attributes}
      onClick={() => onSelect(app.id)}
      className="touch-none cursor-grab active:cursor-grabbing"
    >
      <KanbanCard app={app} isDragging={isDragging} onOpenCompany={onOpenCompany} isUpdated={updatedIds?.has(app.id)} />
    </div>
  )
}

function DroppableColumn({ status, items, onSelect, onOpenCompany, updatedIds }: {
  status: MainStatus
  items: Application[]
  onSelect: (id: number) => void
  onOpenCompany?: (id: number) => void
  updatedIds?: Set<number>
}) {
  const { setNodeRef, isOver } = useDroppable({ id: status })
  const { subStatusLabel } = useStatusLabels()

  // Group items by sub_status, ordered by SUB_ORDER; items without sub_status first
  const groups: { sub: string | undefined; apps: Application[] }[] = []
  const sorted = [...items].sort((a, b) => {
    const oa = a.sub_status ? (SUB_ORDER[a.sub_status] ?? 99) : -1
    const ob = b.sub_status ? (SUB_ORDER[b.sub_status] ?? 99) : -1
    return oa - ob
  })
  for (const app of sorted) {
    const last = groups[groups.length - 1]
    if (last && last.sub === app.sub_status) {
      last.apps.push(app)
    } else {
      groups.push({ sub: app.sub_status, apps: [app] })
    }
  }

  return (
    <div className="min-w-0">
      <div className="flex items-center justify-between mb-2">
        <StatusBadge status={status} size="sm" />
        <span className="text-xs text-gray-400">{items.length}</span>
      </div>
      <div
        ref={setNodeRef}
        className={clsx(
          'min-h-16 rounded-xl transition-colors',
          isOver && 'bg-indigo-50/60 ring-2 ring-indigo-200'
        )}
      >
        {groups.map(({ sub, apps }) => (
          <div key={sub ?? '__none__'} className="mb-3 last:mb-0">
            {sub && (
              <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide mb-1.5 px-0.5">
                {subStatusLabel(sub)}
              </p>
            )}
            <div className="space-y-2">
              {apps.map(app => (
                <DraggableCard key={app.id} app={app} onSelect={onSelect} onOpenCompany={onOpenCompany} updatedIds={updatedIds} />
              ))}
            </div>
          </div>
        ))}
        {items.length === 0 && (
          <div className={clsx(
            'rounded-xl border-2 border-dashed p-4 text-center text-xs',
            isOver ? 'border-indigo-300 text-indigo-400' : 'border-gray-100 text-gray-300'
          )}>
            {isOver ? 'Hier ablegen' : 'Leer'}
          </div>
        )}
      </div>
    </div>
  )
}

export function KanbanBoard({ columns, onSelect, onChanged, onOpenCompany, updatedIds }: Props) {
  const [draggingApp, setDraggingApp] = useState<Application | null>(null)

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } })
  )

  function handleDragStart(event: DragStartEvent) {
    const app = columns.flatMap(c => c.items).find(a => a.id === event.active.id)
    setDraggingApp(app ?? null)
  }

  async function handleDragEnd(event: DragEndEvent) {
    setDraggingApp(null)
    const { active, over } = event
    if (!over) return
    const newStatus = over.id as MainStatus
    const app = columns.flatMap(c => c.items).find(a => a.id === active.id)
    if (!app || app.main_status === newStatus) return
    await api.applications.update(app.id, { main_status: newStatus })
    onChanged()
  }

  return (
    <DndContext sensors={sensors} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
      <div className="overflow-x-auto w-full pb-8" style={{ scrollbarGutter: 'stable' }}>
        <div
          className="grid gap-4 px-4 sm:px-6 lg:px-8 pb-4"
          style={{ gridTemplateColumns: `repeat(${columns.length}, minmax(220px, 1fr))` }}
        >
          {columns.map(({ status, items }) => (
            <DroppableColumn key={status} status={status} items={items} onSelect={onSelect} onOpenCompany={onOpenCompany} updatedIds={updatedIds} />
          ))}
        </div>
      </div>
      <DragOverlay>
        {draggingApp && <KanbanCard app={draggingApp} />}
      </DragOverlay>
    </DndContext>
  )
}
