import { useRef, useState, useEffect } from 'react'
import { Upload, CheckCircle, AlertCircle, Loader2, X } from 'lucide-react'
import { api } from '../api/client'
import type { ImportResult } from '../types'

interface Props {
  onImported: () => void
}

export function ImportButton({ onImported }: Props) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [state, setState] = useState<'idle' | 'loading' | 'done' | 'error'>('idle')
  const [result, setResult] = useState<ImportResult | null>(null)
  const [showModal, setShowModal] = useState(false)

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setState('loading')
    setResult(null)
    try {
      const res = await api.import.excel(file)
      setState('done')
      setResult(res)
      setShowModal(true)
      onImported()
    } catch (err) {
      const res = { imported: 0, skipped: 0, errors: [String(err)], message: 'Import fehlgeschlagen' }
      setState('error')
      setResult(res)
      setShowModal(true)
    }
    if (fileRef.current) fileRef.current.value = ''
  }

  return (
    <>
      <input ref={fileRef} type="file" accept=".xlsx,.xls" className="hidden" onChange={handleFile} />

      <button
        onClick={() => fileRef.current?.click()}
        disabled={state === 'loading'}
        title="Excel-Tracking-Datei importieren (.xlsx)"
        className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-700 rounded-lg border border-gray-200 bg-white hover:bg-gray-50 disabled:opacity-50 transition-colors"
      >
        {state === 'loading'
          ? <Loader2 className="h-4 w-4 animate-spin text-indigo-500" />
          : <Upload className="h-4 w-4 text-indigo-500" />}
        Import
      </button>

      {showModal && result && (
        <ImportResultModal
          result={result}
          onClose={() => { setShowModal(false); setState('idle') }}
        />
      )}
    </>
  )
}

function ImportResultModal({ result, onClose }: { result: ImportResult; onClose: () => void }) {
  const hasErrors = result.errors.length > 0
  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/30 p-4"
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <div className="w-full max-w-sm rounded-2xl bg-white shadow-2xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <div className="flex items-center gap-2">
            {hasErrors
              ? <AlertCircle className="h-4 w-4 text-amber-500" />
              : <CheckCircle className="h-4 w-4 text-green-500" />}
            <h2 className="text-sm font-semibold text-gray-900">Excel-Import abgeschlossen</h2>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-gray-100 text-gray-400">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="px-5 py-4 space-y-3">
          <p className="text-sm text-gray-700">{result.message}</p>
          <div className="flex gap-3">
            {result.imported > 0 && (
              <div className="flex flex-col items-center px-3 py-1.5 rounded-lg bg-indigo-50 text-indigo-700">
                <span className="text-lg font-bold leading-tight">{result.imported}</span>
                <span className="text-[10px] font-medium">Importiert</span>
              </div>
            )}
            {result.skipped > 0 && (
              <div className="flex flex-col items-center px-3 py-1.5 rounded-lg bg-gray-50 text-gray-500">
                <span className="text-lg font-bold leading-tight">{result.skipped}</span>
                <span className="text-[10px] font-medium">Übersprungen</span>
              </div>
            )}
            {result.errors.length > 0 && (
              <div className="flex flex-col items-center px-3 py-1.5 rounded-lg bg-red-50 text-red-700">
                <span className="text-lg font-bold leading-tight">{result.errors.length}</span>
                <span className="text-[10px] font-medium">Fehler</span>
              </div>
            )}
          </div>
          {result.errors.length > 0 && (
            <details className="text-xs text-red-600">
              <summary className="cursor-pointer text-gray-500 hover:text-gray-700">Fehler anzeigen</summary>
              <ul className="mt-1 space-y-0.5 ml-2">
                {result.errors.map((e, i) => <li key={i}>{e}</li>)}
              </ul>
            </details>
          )}
        </div>

        <div className="flex justify-end px-5 py-3 border-t border-gray-100">
          <button
            onClick={onClose}
            className="text-xs font-medium px-3 py-1.5 rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50"
          >
            Schließen
          </button>
        </div>
      </div>
    </div>
  )
}
