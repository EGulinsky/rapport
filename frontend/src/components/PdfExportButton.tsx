import { useState } from 'react'
import { FileText, Loader2 } from 'lucide-react'
import { api } from '../api/client'

const DEFAULT_SINCE = '2026-02-01'

export function PdfExportButton() {
  const [loading, setLoading] = useState(false)

  async function handleExport() {
    setLoading(true)
    try {
      await api.export.pdf(DEFAULT_SINCE)
    } catch (err) {
      alert(`PDF-Export fehlgeschlagen: ${err}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <button
      onClick={handleExport}
      disabled={loading}
      title="Nachweis der Eigenbemühungen (ab 01.02.2026)"
      className="flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50 disabled:opacity-60 transition-colors"
    >
      {loading
        ? <Loader2 className="h-4 w-4 animate-spin" />
        : <FileText className="h-4 w-4" />}
      PDF exportieren
    </button>
  )
}
