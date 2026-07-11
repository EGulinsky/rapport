import { useEffect, useState } from 'react'
import { AlertTriangle, X, ChevronDown, ChevronUp, RefreshCw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api, type StartupCheck } from '../api/client'

export function StartupWarningBanner() {
  const { t } = useTranslation('app')
  const [errors, setErrors] = useState<StartupCheck[]>([])
  const [dismissed, setDismissed] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const [checking, setChecking] = useState(false)

  async function runCheck() {
    setChecking(true)
    try {
      const result = await api.startup.check()
      setErrors(result.errors)
      if (result.all_ok) setDismissed(true)
    } catch {
      // backend not ready yet — ignore
    } finally {
      setChecking(false)
    }
  }

  useEffect(() => {
    runCheck()
  }, [])

  if (dismissed || errors.length === 0) return null

  const bridges = errors.filter(e => e.group === 'bridges')
  const connections = errors.filter(e => e.group === 'connections')

  return (
    <div className="bg-amber-50 border-b border-amber-200 text-amber-900 text-xs">
      <div className="flex items-center gap-2 px-4 py-2">
        <AlertTriangle className="h-3.5 w-3.5 text-amber-500 shrink-0" />
        <span className="font-medium">
          {t('startupWarning.servicesUnreachable', { count: errors.length })}
          {' '}—{' '}
          <span className="font-normal text-amber-700">
            {errors.map(e => e.name).join(', ')}
          </span>
        </span>
        <div className="ml-auto flex items-center gap-1">
          <button
            onClick={runCheck}
            disabled={checking}
            className="p-1 rounded hover:bg-amber-100 text-amber-600 disabled:opacity-50"
            title={t('startupWarning.recheck')}
          >
            <RefreshCw className={`h-3 w-3 ${checking ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={() => setExpanded(e => !e)}
            className="p-1 rounded hover:bg-amber-100 text-amber-600"
            title={expanded ? t('startupWarning.collapse') : t('startupWarning.details')}
          >
            {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          </button>
          <button
            onClick={() => setDismissed(true)}
            className="p-1 rounded hover:bg-amber-100 text-amber-600"
            title={t('startupWarning.close')}
          >
            <X className="h-3 w-3" />
          </button>
        </div>
      </div>

      {expanded && (
        <div className="px-4 pb-3 grid grid-cols-1 sm:grid-cols-2 gap-1.5">
          {bridges.length > 0 && (
            <div>
              <p className="font-medium text-amber-800 mb-1">{t('startupWarning.localBridges')}</p>
              {bridges.map(e => (
                <div key={e.name} className="flex items-start gap-1.5 text-amber-700">
                  <span className="mt-0.5">•</span>
                  <span><span className="font-medium">{e.name}:</span> {e.message}</span>
                </div>
              ))}
            </div>
          )}
          {connections.length > 0 && (
            <div>
              <p className="font-medium text-amber-800 mb-1">{t('startupWarning.connections')}</p>
              {connections.map(e => (
                <div key={e.name} className="flex items-start gap-1.5 text-amber-700">
                  <span className="mt-0.5">•</span>
                  <span><span className="font-medium">{e.name}:</span> {e.message}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
