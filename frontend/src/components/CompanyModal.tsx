import { useState, useEffect, useCallback } from 'react'
import { X, ExternalLink, Clock, CheckCircle, XCircle } from 'lucide-react'
import { api } from '../api/client'
import type { CompanyProfile } from '../types'
import clsx from 'clsx'

interface Props {
  id: number
  onClose: () => void
  onOpenApplication?: (id: number) => void
}

const COMPANY_TYPE_COLORS: Record<string, string> = {
  startup:     'bg-blue-100 text-blue-700',
  konzern:     'bg-indigo-100 text-indigo-700',
  kmu:         'bg-teal-100 text-teal-700',
  beratung:    'bg-purple-100 text-purple-700',
  headhunter:  'bg-orange-100 text-orange-700',
  nonprofit:   'bg-green-100 text-green-700',
  public:      'bg-gray-100 text-gray-700',
  other:       'bg-gray-100 text-gray-600',
}

const COMPANY_TYPE_LABELS: Record<string, string> = {
  startup:     'Startup',
  konzern:     'Konzern',
  kmu:         'KMU',
  beratung:    'Beratung',
  headhunter:  'Headhunter',
  nonprofit:   'Non-Profit',
  public:      'Öffentlich',
  other:       'Sonstiges',
}

const SYNC_SOURCE_LABELS: Record<string, string> = {
  ai:       'KI',
  linkedin: 'LinkedIn',
  manual:   'Manuell',
}

export function CompanyModal({ id, onClose, onOpenApplication }: Props) {
  const [company, setCompany] = useState<CompanyProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.companies.get(id)
      setCompany(data)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { load() }, [load])

  function formatDate(s: string | null | undefined): string {
    if (!s) return '—'
    return new Date(s).toLocaleDateString('de-DE')
  }

  const location = [company?.hq_city, company?.hq_country].filter(Boolean).join(', ')

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="w-full max-w-lg rounded-2xl bg-white shadow-2xl flex flex-col max-h-[90vh]">
        <div className="flex items-start justify-between gap-3 p-5 border-b border-gray-100">
          <div className="flex-1 min-w-0">
            {loading ? (
              <div className="h-6 w-48 bg-gray-100 rounded animate-pulse" />
            ) : (
              <>
                <h2 className="text-lg font-semibold text-gray-900 truncate">
                  {company?.name_display || company?.name_norm}
                </h2>
                <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                  {company?.sync_source && (
                    <span className="text-xs text-gray-400 bg-gray-50 border border-gray-100 rounded px-1.5 py-0.5">
                      {SYNC_SOURCE_LABELS[company.sync_source] ?? company.sync_source}
                    </span>
                  )}
                  {company?.last_synced_at && (
                    <span className="text-xs text-gray-400">
                      Sync: {formatDate(company.last_synced_at)}
                    </span>
                  )}
                </div>
              </>
            )}
          </div>
          <button
            onClick={onClose}
            className="shrink-0 p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {error && (
            <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">{error}</div>
          )}

          {!loading && company && (
            <>
              <div className="flex items-center gap-2">
                {company.sync_status === 'pending' && (
                  <span className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium bg-yellow-100 text-yellow-700">
                    <Clock className="h-3 w-3" /> Ausstehend
                  </span>
                )}
                {company.sync_status === 'done' && (
                  <span className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium bg-green-100 text-green-700">
                    <CheckCircle className="h-3 w-3" /> Synchronisiert
                  </span>
                )}
                {company.sync_status === 'failed' && (
                  <span
                    className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium bg-red-100 text-red-700"
                    title={company.sync_error ?? undefined}
                  >
                    <XCircle className="h-3 w-3" /> Fehler
                  </span>
                )}
              </div>

              {company.sync_status === 'failed' && company.sync_error && (
                <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-xs text-red-700">
                  {company.sync_error}
                </div>
              )}

              <div className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
                <div>
                  <p className="text-xs text-gray-400 mb-0.5">Branche</p>
                  <p className="text-gray-900">{company.industry || '—'}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400 mb-0.5">Typ</p>
                  {company.company_type ? (
                    <span className={clsx(
                      'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
                      COMPANY_TYPE_COLORS[company.company_type] ?? 'bg-gray-100 text-gray-600'
                    )}>
                      {COMPANY_TYPE_LABELS[company.company_type] ?? company.company_type}
                    </span>
                  ) : <p className="text-gray-400">—</p>}
                </div>
                <div>
                  <p className="text-xs text-gray-400 mb-0.5">Mitarbeiter</p>
                  <p className="text-gray-900">{company.employee_range || (company.employee_count != null ? String(company.employee_count) : '—')}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400 mb-0.5">Gegründet</p>
                  <p className="text-gray-900">{company.founded_year ?? '—'}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400 mb-0.5">Standort</p>
                  <p className="text-gray-900">{location || '—'}</p>
                </div>
                {company.website && (
                  <div>
                    <p className="text-xs text-gray-400 mb-0.5">Website</p>
                    <a
                      href={company.website}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-indigo-600 hover:text-indigo-800 text-xs"
                    >
                      <ExternalLink className="h-3 w-3" />
                      {company.website.replace(/^https?:\/\//, '').replace(/\/$/, '')}
                    </a>
                  </div>
                )}
                {company.linkedin_company_url && (
                  <div>
                    <p className="text-xs text-gray-400 mb-0.5">LinkedIn</p>
                    <a
                      href={company.linkedin_company_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-indigo-600 hover:text-indigo-800 text-xs"
                    >
                      <ExternalLink className="h-3 w-3" />
                      LinkedIn
                    </a>
                  </div>
                )}
              </div>

              {company.description && (
                <div className="rounded-lg bg-gray-50 border border-gray-100 px-3 py-2.5 text-sm text-gray-700 whitespace-pre-wrap">
                  {company.description}
                </div>
              )}

              {company.applications && company.applications.length > 0 && (
                <div>
                  <h3 className="text-sm font-medium text-gray-900 mb-2">
                    Bewerbungen ({company.applications.length})
                  </h3>
                  <div className="space-y-1.5">
                    {company.applications.map(app => (
                      <button
                        key={app.id}
                        onClick={() => onOpenApplication?.(app.id)}
                        className="w-full text-left rounded-lg border border-gray-100 bg-gray-50 hover:bg-indigo-50 hover:border-indigo-200 px-3 py-2 transition-colors flex items-center justify-between gap-2"
                      >
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-gray-900 truncate">{app.rolle}</p>
                          {app.datum_bewerbung && (
                            <p className="text-xs text-gray-400">
                              {new Date(app.datum_bewerbung).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })}
                            </p>
                          )}
                        </div>
                        <span className="shrink-0 text-xs px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 font-medium">
                          {app.main_status}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}

          {loading && (
            <div className="space-y-3">
              <div className="h-4 w-32 bg-gray-100 rounded animate-pulse" />
              <div className="grid grid-cols-2 gap-3">
                {[...Array(6)].map((_, i) => (
                  <div key={i} className="h-10 bg-gray-100 rounded animate-pulse" />
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
