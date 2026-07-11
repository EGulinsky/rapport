import { useState } from 'react'
import { X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'

const EMPTY_NEW_CONTACT = { name: '', vorname: '', email: '', telefon: '', firma: '', rolle: '', linkedin_url: '' }

export function NewContactModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const { t } = useTranslation('contacts')
  const { t: tCommon } = useTranslation('common')
  const [draft, setDraft] = useState(EMPTY_NEW_CONTACT)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

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
        rolle: draft.rolle.trim() || undefined,
        linkedin_url: draft.linkedin_url.trim() || undefined,
      })
      onCreated()
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message.replace(/^\d+:\s*/, '') : String(e))
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
            <input placeholder={t('newContact.companyPlaceholder')} value={draft.firma}
              onChange={e => setDraft(d => ({ ...d, firma: e.target.value }))}
              className="rounded-lg border border-gray-200 px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
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
