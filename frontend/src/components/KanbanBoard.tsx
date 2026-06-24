import { useState } from 'react'
import {
  DndContext, DragEndEvent, DragOverlay, DragStartEvent,
  PointerSensor, useSensor, useSensors,
  useDroppable, useDraggable,
} from '@dnd-kit/core'
import { CSS } from '@dnd-kit/utilities'
import { StatusBadge } from './StatusBadge'
import { MAIN_STATUS_LABELS, MAIN_STATUS_COLORS, SUB_STATUS_LABELS, SUB_STATUS_SEQUENCE, type MainStatus } from '../types'

const SUB_ORDER = Object.fromEntries(SUB_STATUS_SEQUENCE.map((s, i) => [s, i]))
import type { Application } from '../types'
import { api } from '../api/client'
import clsx from 'clsx'

interface Props {
  columns: { status: MainStatus; items: Application[] }[]
  onSelect: (id: number) => void
  onChanged: () => void
}

function KanbanCard({ app, isDragging }: { app: Application; isDragging?: boolean }) {
  return (
    <div className={clsx(
      'w-full text-left rounded-xl border bg-white p-3 shadow-sm',
      app.abgesagt
        ? 'border-l-4 border-l-red-300 border-gray-200 opacity-60 bg-rose-50/20'
        : 'border-gray-200',
      isDragging ? 'opacity-50 shadow-lg rotate-1' : (!app.abgesagt && 'hover:border-indigo-300 hover:shadow-md transition-all')
    )}>
      {app.abgesagt && (
        <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold bg-red-100 text-red-600 mb-1.5">
          Abgesagt
        </span>
      )}
      {app.is_headhunter ? (
        <>
          <div className="flex items-center gap-1 mb-0.5">
            <span className="inline-flex items-center rounded px-1 py-0.5 text-[10px] font-semibold bg-indigo-100 text-indigo-700 shrink-0">HH</span>
            <span className="text-xs text-indigo-700 truncate leading-tight">{app.firma}</span>
          </div>
          <p className="font-medium text-sm text-gray-900 leading-tight">
            {app.zielfirma_bei_hh ?? <span className="text-gray-400 italic text-xs">Zielfirma unbekannt</span>}
          </p>
        </>
      ) : (
        <p className={clsx('font-medium text-sm leading-tight', app.abgesagt ? 'text-gray-500 line-through decoration-red-300' : 'text-gray-900')}>
          {app.firma}
        </p>
      )}
      <p className="text-xs text-gray-500 mt-0.5 leading-tight">{app.rolle}</p>
      <p className="text-[10px] text-gray-300 font-mono mt-0.5 select-all leading-tight">{app.id}</p>
      {app.sub_status && (
        <p className="text-xs text-gray-400 mt-1">{SUB_STATUS_LABELS[app.sub_status] ?? app.sub_status}</p>
      )}
      {app.ghosting && <span className="text-xs">👻</span>}
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
      {(app.letztes_update || app.datum_bewerbung) && (
        <p className="text-[10px] text-gray-400 mt-2 pt-2 border-t border-gray-100">
          {app.letztes_update
            ? new Date(app.letztes_update).toLocaleDateString('de-DE')
            : new Date(app.datum_bewerbung!).toLocaleDateString('de-DE')}
        </p>
      )}
    </div>
  )
}

function DraggableCard({ app, onSelect }: { app: Application; onSelect: (id: number) => void }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: app.id })
  const style = transform ? { transform: CSS.Translate.toString(transform) } : undefined

  return (
    <div ref={setNodeRef} style={style} {...listeners} {...attributes}
      onClick={() => onSelect(app.id)}
      className="touch-none cursor-grab active:cursor-grabbing"
    >
      <KanbanCard app={app} isDragging={isDragging} />
    </div>
  )
}

function DroppableColumn({ status, items, onSelect }: {
  status: MainStatus
  items: Application[]
  onSelect: (id: number) => void
}) {
  const { setNodeRef, isOver } = useDroppable({ id: status })

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
    <div className="flex-shrink-0 w-64">
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
                {SUB_STATUS_LABELS[sub] ?? sub}
              </p>
            )}
            <div className="space-y-2">
              {apps.map(app => (
                <DraggableCard key={app.id} app={app} onSelect={onSelect} />
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

export function KanbanBoard({ columns, onSelect, onChanged }: Props) {
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
      <div className="overflow-x-auto w-full">
        <div className="flex gap-4 pb-4 w-max min-w-full">
          {columns.map(({ status, items }) => (
            <DroppableColumn key={status} status={status} items={items} onSelect={onSelect} />
          ))}
        </div>
      </div>
      <DragOverlay>
        {draggingApp && <KanbanCard app={draggingApp} />}
      </DragOverlay>
    </DndContext>
  )
}
