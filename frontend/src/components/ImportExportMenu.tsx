import { useState, useRef, useEffect } from 'react'
import { Download, Upload, FileText, ChevronDown, Loader2, CheckCircle, AlertCircle, X } from 'lucide-react'
import { api } from '../api/client'
import type { ImportResult } from '../types'
import clsx from 'clsx'

interface Props { onImported: () => void }

export function ImportExportMenu({ onImported }: Props) {
  const [open, setOpen] = useState(false)
  const [loadingExcel, setLoadingExcel] = useState(false)
  const [loadingPdf, setLoadingPdf] = useState(false)
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState<ImportResult | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const dropRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (dropRef.current && !dropRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  async function exportExcel() {
    setOpen(false)
    setLoadingExcel(true)
    try { await api.export.excel(true) } catch (e) { alert(`Export fehlgeschlagen: ${e}`) } finally { setLoadingExcel(false) }
  }

  async function exportPdf() {
    setOpen(false)
    setLoadingPdf(true)
    try { await api.export.pdf('2026-02-01') } catch (e) { alert(`PDF-Export fehlgeschlagen: ${e}`) } finally { setLoadingPdf(false) }
  }

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setImporting(true)
    try {
      const res = await api.import.excel(file)
      setImportResult(res)
      onImported()
    } catch (err) {
      setImportResult({ imported: 0, skipped: 0, errors: [String(err)], message: 'Import fehlgeschlagen' })
    } finally {
      setImporting(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const busy = loadingExcel || loadingPdf || importing

  return (
    <>
      <div className="relative" ref={dropRef}>
        <button
          onClick={() => setOpen(o => !o)}
          disabled={busy}
          className="flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 transition-colors"
        >
          {busy
            ? <Loader2 className="h-4 w-4 animate-spin text-indigo-500" />
            : <Download className="h-4 w-4 text-indigo-500" />}
          Im/Export
          <ChevronDown className={clsx('h-3.5 w-3.5 text-gray-400 transition-transform', open && 'rotate-180')} />
        </button>

        {open && (
          <div className="absolute right-0 top-full mt-1 z-40 w-52 rounded-lg border border-gray-200 bg-white shadow-lg py-1">
            <button
              onClick={exportExcel}
              className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-2"
            >
              <Download className="h-3.5 w-3.5 text-emerald-500" />
              Excel exportieren
            </button>
            <button
              onClick={exportPdf}
              className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-2"
              title="Nachweis der Eigenbemühungen (ab 01.02.2026)"
            >
              <FileText className="h-3.5 w-3.5 text-rose-500" />
              <span>
                PDF exportieren
                <span className="block text-xs text-gray-400">Eigenbemühungen ab 02.26</span>
              </span>
            </button>
            <div className="my-1 border-t border-gray-100" />
            <button
              onClick={() => { setOpen(false); fileRef.current?.click() }}
              className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-2"
            >
              <Upload className="h-3.5 w-3.5 text-indigo-500" />
              Excel importieren
            </button>
          </div>
        )}
      </div>

      <input ref={fileRef} type="file" accept=".xlsx,.xls" className="hidden" onChange={handleFile} />

      {importResult && (
        <ImportResultModal result={importResult} onClose={() => setImportResult(null)} />
      )}
    </>
  )
}

function ImportResultModal({ result, onClose }: { result: ImportResult; onClose: () => void }) {
  const hasErrors = result.errors.length > 0
  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/30 p-4" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="w-full max-w-sm rounded-2xl bg-white shadow-2xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <div className="flex items-center gap-2">
            {hasErrors ? <AlertCircle className="h-4 w-4 text-amber-500" /> : <CheckCircle className="h-4 w-4 text-green-500" />}
            <h2 className="text-sm font-semibold text-gray-900">Excel-Import abgeschlossen</h2>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-gray-100 text-gray-400"><X className="h-4 w-4" /></button>
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
              <ul className="mt-1 space-y-0.5 ml-2">{result.errors.map((e, i) => <li key={i}>{e}</li>)}</ul>
            </details>
          )}
        </div>
        <div className="flex justify-end px-5 py-3 border-t border-gray-100">
          <button onClick={onClose} className="text-xs font-medium px-3 py-1.5 rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50">Schließen</button>
        </div>
      </div>
    </div>
  )
}
