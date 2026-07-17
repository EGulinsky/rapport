import { useEffect, useRef, useState } from 'react'
import { Building2, Plus, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { errorMessage } from '../i18n/errorMessage'
import type { CompanyProfile } from '../types'

const EMPTY_NEW_CONTACT = { name: '', vorname: '', email: '', telefon: '', firma: '', company_profile_id: null as number | null, rolle: '', linkedin_url: '' }

export function NewContactModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const { t } = useTranslation('contacts')
  const { t: tCommon } = useTranslation('common')
  const [draft, setDraft] = useState(EMPTY_NEW_CONTACT)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [firmaPicker, setFirmaPicker] = useState(false)
  const [firmaQuery, setFirmaQuery] = useState('')
  const [firmaResults, setFirmaResults] = useState<CompanyProfile[]>([])
  const [firmaLoading, setFirmaLoading] = useState(false)
  const [firmaCreating, setFirmaCreating] = useState(false)
  const firmaPickerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!firmaPicker) { setFirmaQuery(''); setFirmaResults([]); return }
    const timer = setTimeout(async () => {
      setFirmaLoading(true)
      try { setFirmaResults(await api.companies.list({ search: firmaQuery || undefined })) }
      finally { setFirmaLoading(false) }
    }, 200)
    return () => clearTimeout(timer)
  }, [firmaQuery, firmaPicker])

  useEffect(() => {
    if (!firmaPicker) return
    function onDown(e: MouseEvent) {
      if (firmaPickerRef.current && !firmaPickerRef.current.contains(e.target as Node)) setFirmaPicker(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [firmaPicker])

  function pickCompany(c: CompanyProfile) {
    setDraft(d => ({ ...d, firma: c.name_display ?? c.name_norm, company_profile_id: c.id }))
    setFirmaPicker(false)
  }

  async function createAndPickCompany(name: string) {
    setFirmaCreating(true)
    try {
      const c = await api.companies.create(name)
      setDraft(d => ({ ...d, firma: c.name_display ?? c.name_norm, company_profile_id: c.id }))
      setFirmaPicker(false)
    } finally {
      setFirmaCreating(false)
    }
  }

  async function save() {
    if (!draft.name.trim()) return
    setSaving(true)
    setError(null)
    try {
      await api.contacts.create({
        name: draft.name.trim(),
        vorname: draft.vorname.trim() || undefined,
        email: draft.email.trim() || undefined,
        telefon: draft.telefon.trim() || undefined,
        firma: draft.firma.trim() || undefined,
        company_profile_id: draft.company_profile_id ?? undefined,
        rolle: draft.rolle.trim() || undefined,
        linkedin_url: draft.linkedin_url.trim() || undefined,
      })
      onCreated()
      onClose()
    } catch (e) {
      setError(errorMessage(e, t))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <div className="w-full max-w-md rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <h2 className="text-base font-semibold text-gray-900">{t('newContact.title')}</h2>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="px-5 py-4 space-y-2.5">
          {error && <p className="text-xs text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2">{error}</p>}
          <div className="grid grid-cols-2 gap-2.5">
            <input autoFocus placeholder={t('newContact.firstNamePlaceholder')} value={draft.vorname}
              onChange={e => setDraft(d => ({ ...d, vorname: e.target.value }))}
              className="rounded-lg border border-gray-200 px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            <input placeholder={t('newContact.lastNamePlaceholder')} value={draft.name}
              onChange={e => setDraft(d => ({ ...d, name: e.target.value }))}
              className="rounded-lg border border-gray-200 px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
          </div>
          <input placeholder={t('newContact.emailPlaceholder')} value={draft.email}
            onChange={e => setDraft(d => ({ ...d, email: e.target.value }))}
            className="w-full rounded-lg border border-gray-200 px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
          <input placeholder={t('newContact.phonePlaceholder')} value={draft.telefon}
            onChange={e => setDraft(d => ({ ...d, telefon: e.target.value }))}
            className="w-full rounded-lg border border-gray-200 px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
          <div className="grid grid-cols-2 gap-2.5">
            <div className="relative" ref={firmaPickerRef}>
              <div
                className={`w-full flex items-center justify-between rounded-lg border px-2.5 py-1.5 text-sm cursor-pointer ${draft.firma ? 'border-gray-200 text-gray-900' : 'border-gray-200 text-gray-400'} hover:border-indigo-300`}
                onClick={() => setFirmaPicker(o => !o)}
              >
                <span className="truncate">{draft.firma || t('newContact.companyPlaceholder')}</span>
                <Building2 className="h-3.5 w-3.5 text-gray-400 shrink-0 ml-1" />
              </div>
              {firmaPicker && (
                <div className="absolute z-50 top-full left-0 mt-1 w-64 bg-white border border-gray-200 rounded-lg shadow-lg">
                  <div className="p-2 border-b border-gray-100">
                    <input
                      autoFocus
                      value={firmaQuery}
                      onChange={e => setFirmaQuery(e.target.value)}
                      placeholder={t('newContact.searchCompanyPlaceholder')}
                      className="w-full rounded border border-gray-200 px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                  </div>
                  <div className="max-h-48 overflow-y-auto py-1">
                    {firmaLoading && <p className="text-xs text-gray-400 px-3 py-1.5">{t('newContact.searching')}</p>}
                    {!firmaLoading && firmaResults.length === 0 && !firmaQuery && (
                      <p className="text-xs text-gray-400 px-3 py-1.5 italic">{t('newContact.enterSearchTerm')}</p>
                    )}
                    {firmaResults.slice(0, 8).map(c => (
                      <button key={c.id} type="button" onClick={() => pickCompany(c)}
                        className="w-full text-left px-3 py-1 text-xs hover:bg-indigo-50 hover:text-indigo-700 transition-colors">
                        {c.name_display ?? c.name_norm}
                      </button>
                    ))}
                    {firmaQuery.trim() && (
                      <button type="button" disabled={firmaCreating} onClick={() => createAndPickCompany(firmaQuery.trim())}
                        className="w-full text-left px-3 py-1 text-xs text-indigo-600 hover:bg-indigo-50 transition-colors flex items-center gap-1 border-t border-gray-100 mt-1">
                        <Plus className="h-3 w-3 shrink-0" />
                        {firmaCreating ? t('newContact.creating') : t('newContact.createNew', { name: firmaQuery.trim() })}
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
            <input placeholder={t('newContact.rolePlaceholder')} value={draft.rolle}
              onChange={e => setDraft(d => ({ ...d, rolle: e.target.value }))}
              className="rounded-lg border border-gray-200 px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
          </div>
          <input placeholder={t('newContact.linkedinPlaceholder')} value={draft.linkedin_url}
            onChange={e => setDraft(d => ({ ...d, linkedin_url: e.target.value }))}
            className="w-full rounded-lg border border-gray-200 px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
        </div>
        <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-gray-100">
          <button onClick={onClose} className="text-sm text-gray-500 hover:text-gray-700 px-3 py-1.5">{tCommon('cancel')}</button>
          <button
            onClick={save}
            disabled={!draft.name.trim() || saving}
            className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {saving ? tCommon('saving') : tCommon('save')}
          </button>
        </div>
      </div>
    </div>
  )
}
