import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { X, Plus, Trash2, Pencil, Check, Clock, Mail, Calendar, FileText, Phone, PenLine, Crosshair, ChevronDown, RefreshCw, Send, TrendingUp, MessageCircle, ExternalLink, Search, Paperclip, Download, Folder, FolderOpen, ChevronRight, File, Users, Building2, Sparkles, Wallet, AlertTriangle, Car, Linkedin } from 'lucide-react'
import { api } from '../api/client'
import { StatusBadge } from './StatusBadge'
import { CompanyLogo } from './CompanyLogo'
import { LocationSearchInput } from './LocationSearchInput'
import { displayName } from './ContactModal'
import { CURRENCIES } from '../constants/currencies'
import { formatCurrencyAmount, formatSalaryRange } from '../utils/salaryFormat'
import type { CompanyProfile, LinkedInSyncStatus } from '../types'
import {
  MAIN_PIPELINE, MAIN_STATUS_COLORS,
  SUB_STATUS_SEQUENCE,
  type Application, type MainStatus, type Contact, type Event, type ManualCandidate, type FileBrowseItem,
} from '../types'
import { useStatusLabels } from '../i18n/statusLabels'
import { useLocale } from '../i18n/useLocale'
import { formatDate } from '../i18n/formatDate'
import { errorMessage } from '../i18n/errorMessage'

function parentPath(p: string): string {
  const parts = p.replace(/\/$/, '').split('/')
  if (parts.length <= 1) return '/'
  return parts.slice(0, -1).join('/') || '/'
}

interface Props {
  appId: number | null
  onClose: () => void
  onSaved: () => void
  onOpenCompany?: (id: number) => void
  onOpenContact?: (id: number) => void
  updatedFields?: Set<string>
  onReviewOpen?: () => void
}

const CONTACT_TYPES = ['HR', 'Headhunter', 'FB', 'CEO', 'Netzwerk']
const EMPTY_CONTACT = { name: '', email: '', telefon: '', typ: '', rolle: '' }

// Quick-entry draft for the inline add/edit-contact panels: a single phone
// input (telefon) instead of the full multi-phone editor used in the
// dedicated Contact modals — kept simple since these panels are already dense.
type ContactDraft = Partial<Omit<Contact, 'phones'>> & { telefon?: string }

export function ApplicationModal({ appId, onClose, onSaved, onOpenCompany, onOpenContact, updatedFields, onReviewOpen }: Props) {
  const { t } = useTranslation('applications')
  const { mainStatusLabel, subStatusLabel } = useStatusLabels()
  const locale = useLocale()
  const [app, setApp] = useState<Application | null>(null)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<Partial<Application>>({})
  const [saving, setSaving] = useState(false)
  const [addingContact, setAddingContact] = useState(false)
  const [addMode, setAddMode] = useState<'new' | 'link'>('new')
  const [contactDraft, setContactDraft] = useState<ContactDraft>(EMPTY_CONTACT)
  const [savingContact, setSavingContact] = useState(false)
  const [editingContactId, setEditingContactId] = useState<number | null>(null)
  const [editContactDraft, setEditContactDraft] = useState<ContactDraft>({})
  const [linkSearch, setLinkSearch] = useState('')
  const [linkResults, setLinkResults] = useState<Contact[]>([])
  const [linkLoading, setLinkLoading] = useState(false)
  const [addingNote, setAddingNote] = useState(false)
  const [noteDraft, setNoteDraft] = useState({ notiz: '', datum: '' })
  const [savingNote, setSavingNote] = useState(false)
  const [addingBewerbung, setAddingBewerbung] = useState(false)
  const [bewerbungDraft, setBewerbungDraft] = useState({ datum: '', titel: 'Bewerbung eingereicht' })
  const [savingBewerbung, setSavingBewerbung] = useState(false)
  const [addingOther, setAddingOther] = useState(false)
  const [otherDraft, setOtherDraft] = useState({ typ: 'status', datum: '', titel: '', notiz: '' })
  const [savingOther, setSavingOther] = useState(false)
  const [addingFile, setAddingFile] = useState(false)
  const [fileDraft, setFileDraft] = useState<{ datum: string; titel: string; file: File | null }>({ datum: '', titel: '', file: null })
  const [savingFile, setSavingFile] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [manualOpen, setManualOpen] = useState(false)
  const [manualQuery, setManualQuery] = useState('')
  const [manualCandidates, setManualCandidates] = useState<ManualCandidate[]>([])
  const [manualLoading, setManualLoading] = useState(false)
  const [manualConflict, setManualConflict] = useState<{ candidate: ManualCandidate; conflict_app_firma: string } | null>(null)
  const [manualSelected, setManualSelected] = useState<Set<string>>(new Set())
  const [manualBulkBusy, setManualBulkBusy] = useState(false)
  const [manualBulkErrors, setManualBulkErrors] = useState<string[]>([])
  const [docBrowseOpen, setDocBrowseOpen] = useState(false)
  const [docBrowsePath, setDocBrowsePath] = useState('')
  const [docBrowseRoot, setDocBrowseRoot] = useState('')
  const [docBrowseItems, setDocBrowseItems] = useState<FileBrowseItem[]>([])
  const [docBrowseLoading, setDocBrowseLoading] = useState(false)
  const [docBrowseError, setDocBrowseError] = useState<string | null>(null)
  const [firmaPicker, setFirmaPicker] = useState(false)
  const [firmaQuery, setFirmaQuery] = useState('')
  const [firmaResults, setFirmaResults] = useState<CompanyProfile[]>([])
  const [firmaLoading, setFirmaLoading] = useState(false)
  const [firmaCreating, setFirmaCreating] = useState(false)
  const firmaPickerRef = useRef<HTMLDivElement>(null)
  // Contact "new" firma picker
  const [cFirmaPicker, setCFirmaPicker] = useState(false)
  const [cFirmaQuery, setCFirmaQuery] = useState('')
  const [cFirmaResults, setCFirmaResults] = useState<CompanyProfile[]>([])
  const [cFirmaLoading, setCFirmaLoading] = useState(false)
  const [cFirmaCreating, setCFirmaCreating] = useState(false)
  const cFirmaRef = useRef<HTMLDivElement>(null)
  // Contact "edit" firma picker
  const [ecFirmaPicker, setEcFirmaPicker] = useState(false)
  const [ecFirmaQuery, setEcFirmaQuery] = useState('')
  const [ecFirmaResults, setEcFirmaResults] = useState<CompanyProfile[]>([])
  const [ecFirmaLoading, setEcFirmaLoading] = useState(false)
  const [ecFirmaCreating, setEcFirmaCreating] = useState(false)
  const ecFirmaRef = useRef<HTMLDivElement>(null)
  const [docAttaching, setDocAttaching] = useState<string | null>(null)
  const [aiAssessing, setAiAssessing] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [syncMenuOpen, setSyncMenuOpen] = useState(false)
  const [syncProgress, setSyncProgress] = useState<Record<string, { label: string; step: string; current: number; total: number; percent: number; done: boolean }>>({})
  const [syncResult, setSyncResult] = useState<{ created: number; errors: string[] } | null>(null)
  const [liStatus, setLiStatus] = useState<LinkedInSyncStatus | null>(null)
  const syncMenuRef = useRef<HTMLDivElement>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [activeTab, setActiveTab] = useState<'overview' | 'timeline' | 'attachments' | 'contacts' | 'salary'>('overview')
  const [timeFilter, setTimeFilter] = useState<'all' | '1m' | '3m' | '6m' | '1y'>('all')
  const [typeFilter, setTypeFilter] = useState('all')
  const [selectedEventIds, setSelectedEventIds] = useState<Set<number>>(new Set())
  const [selectedContactIds, setSelectedContactIds] = useState<Set<number>>(new Set())
  const [bulkDeleting, setBulkDeleting] = useState(false)

  const stopPolling = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
  }, [])

  const startPolling = useCallback(() => {
    stopPolling()
    pollRef.current = setInterval(async () => {
      try {
        const data = await api.sync.progress()
        // Only show: the main key for this app (targeted_{appId}) and generic sub-task keys.
        // Exclude targeted_{otherId} keys from previous/other app syncs.
        const isSubTask = (k: string) => k.startsWith('targeted_') && !/^targeted_\d+$/.test(k)
        const targeted = Object.fromEntries(
          Object.entries(data).filter(([k]) => k === `targeted_${appId}` || isSubTask(k))
        )
        setSyncProgress(targeted)
      } catch { /* ignore */ }
    }, 1000)
  }, [stopPolling])

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (syncMenuRef.current && !syncMenuRef.current.contains(e.target as Node)) setSyncMenuOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  async function clearSyncEvents() {
    if (!appId) return
    setSyncMenuOpen(false)
    try {
      const result = await api.targeted.resetForApp(appId)
      setSyncResult({ created: -(result.deleted_events ?? 0), errors: [] })
      onSaved()
    } catch (e: unknown) {
      setSyncResult({ created: 0, errors: [errorMessage(e, t)] })
    }
  }

  const [aiAssessError, setAiAssessError] = useState<string | null>(null)

  async function runAiAssess() {
    if (!appId) return
    setAiAssessing(true)
    setAiAssessError(null)
    try {
      const result = await api.applications.aiAssess(appId)
      setApp(prev => prev ? {
        ...prev,
        ai_color: result.color as 'green' | 'yellow' | 'red',
        ai_next_step: result.next_step,
        ai_reasoning: result.reasoning,
        ai_assessed_at: new Date().toISOString(),
      } : prev)
      onSaved()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      if (msg.includes('429') || msg.toLowerCase().includes('rate')) {
        setAiAssessError(t('overview.rateLimitError'))
      } else {
        setAiAssessError(t('overview.aiFailedError'))
      }
    } finally {
      setAiAssessing(false)
    }
  }

  async function runSync(reset: boolean) {
    if (!appId) return
    setSyncing(true)
    setSyncMenuOpen(false)
    setSyncResult(null)
    setSyncProgress({})
    setLiStatus(null)
    startPolling()
    try {
      if (reset) await api.targeted.resetForApp(appId)
      await api.targeted.syncForApp(appId)  // returns immediately — sync runs in background

      // Start LinkedIn sync in parallel if configured
      const liCfg = await api.linkedin.getConfig().catch(() => null) as { configured: boolean } | null
      let liRunning = false
      if (liCfg?.configured) {
        try {
          await api.linkedin.run(appId)
          liRunning = true
        } catch (e: unknown) {
          const msg = e instanceof Error ? e.message : String(e)
          if (msg.includes('409') || msg.includes('already running')) liRunning = true
        }
      }

      // Poll for both targeted and LinkedIn results
      for (let i = 0; i < 600; i++) {   // max 10 min
        await new Promise(r => setTimeout(r, 2000))

        const result = await api.targeted.getResult(appId)
        if (result.done && !liRunning) {
          setSyncResult({ created: result.created ?? 0, errors: result.errors ?? [] })
          await refreshContacts()
          onSaved()
          onReviewOpen?.()
          break
        }

        if (liRunning) {
          const ls = await api.linkedin.status().catch(() => null) as LinkedInSyncStatus | null
          if (ls) {
            setLiStatus(ls)
            if (['done', 'error', 'needs_login'].includes(ls.status)) liRunning = false
          }
        }

        if (result.done && !liRunning) {
          setSyncResult({ created: result.created ?? 0, errors: result.errors ?? [] })
          await refreshContacts()
          onSaved()
          onReviewOpen?.()
          break
        }
      }
    } catch (e: unknown) {
      setSyncResult({ created: 0, errors: [errorMessage(e, t)] })
    } finally {
      stopPolling()
      setSyncing(false)
      setSyncProgress({})
    }
  }

  useEffect(() => {
    if (!appId) return
    api.applications.get(appId).then(data => {
      setApp(data)
      setDraft(data)
    })
  }, [appId])

  if (!appId) return null

  async function save() {
    if (!appId || !app) return
    setSaving(true)
    try {
      // Only send fields that changed from the loaded app state.
      // This prevents the modal from accidentally overwriting concurrent changes
      // (e.g. a status change via Kanban) with stale draft data.
      const payload: Partial<Application> = {}
      for (const key of Object.keys(draft) as (keyof Application)[]) {
        if (draft[key] !== app[key]) {
          (payload as Record<string, unknown>)[key] = draft[key]
        }
      }
      if (Object.keys(payload).length === 0) {
        setEditing(false)
        return
      }
      const updated = await api.applications.update(appId, payload)
      setApp(updated)
      setDraft(updated)
      setEditing(false)
      onSaved()
    } finally {
      setSaving(false)
    }
  }

  async function deleteApp() {
    if (!appId || !confirm(t('footer.confirmDelete', { firma: app?.firma }))) return
    await api.applications.delete(appId)
    onClose()
    onSaved()
  }

  async function refreshContacts() {
    if (!appId) return
    const updated = await api.applications.get(appId)
    setApp(updated)
    setDraft(updated)
  }

  async function saveNote() {
    if (!appId || !noteDraft.notiz.trim()) return
    setSavingNote(true)
    try {
      await api.applications.addEvent(appId, {
        typ: 'notiz',
        datum: noteDraft.datum || new Date().toISOString().slice(0, 10),
        notiz: noteDraft.notiz.trim(),
      })
      await refreshContacts()
      setNoteDraft({ notiz: '', datum: '' })
      setAddingNote(false)
    } finally {
      setSavingNote(false)
    }
  }

  function candidateKey(c: ManualCandidate): string {
    return `${c.source}:${c.external_id ?? c.id}`
  }

  async function openManual() {
    if (!appId) return
    setManualOpen(true)
    setSyncMenuOpen(false)
    setManualLoading(true)
    setManualSelected(new Set())
    setManualBulkErrors([])
    try {
      const results = await api.targeted.candidates(appId, '')
      setManualCandidates(results)
    } finally {
      setManualLoading(false)
    }
  }

  async function searchManual() {
    if (!appId) return
    setManualLoading(true)
    setManualSelected(new Set())
    setManualBulkErrors([])
    try {
      const results = await api.targeted.candidates(appId, manualQuery)
      setManualCandidates(results)
    } finally {
      setManualLoading(false)
    }
  }

  function toggleManualSelected(candidate: ManualCandidate) {
    const key = candidateKey(candidate)
    setManualSelected(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  async function assignCandidate(candidate: ManualCandidate, removeFromOther = false) {
    if (!appId) return
    const res = await api.targeted.assign(appId, {
      match_id: candidate.id,
      external_id: candidate.external_id,
      source: candidate.source,
      datum: candidate.datum ?? undefined,
      titel: candidate.titel ?? undefined,
      remove_from_other: removeFromOther,
    })
    if (res.conflict && !removeFromOther) {
      setManualConflict({ candidate, conflict_app_firma: res.conflict_app_firma ?? t('manualAssign.otherApplicationFallback') })
      return
    }
    setManualConflict(null)
    setManualOpen(false)
    await refreshContacts()
  }

  async function assignSelectedCandidates() {
    if (!appId || manualSelected.size === 0) return
    setManualBulkBusy(true)
    setManualBulkErrors([])
    const toAssign = manualCandidates.filter(c => manualSelected.has(candidateKey(c)))
    const errors: string[] = []
    const assignedKeys = new Set<string>()
    try {
      for (const candidate of toAssign) {
        try {
          const res = await api.targeted.assign(appId, {
            match_id: candidate.id,
            external_id: candidate.external_id,
            source: candidate.source,
            datum: candidate.datum ?? undefined,
            titel: candidate.titel ?? undefined,
            remove_from_other: false,
          })
          if (res.conflict) {
            errors.push(t('manualAssign.bulkConflictSkipped', { title: candidate.titel || candidate.source, firma: res.conflict_app_firma ?? t('manualAssign.anotherApplicationFallback') }))
            continue
          }
          assignedKeys.add(candidateKey(candidate))
        } catch (e: unknown) {
          errors.push(`"${candidate.titel || candidate.source}": ${errorMessage(e, t)}`)
        }
      }
      setManualCandidates(prev => prev.filter(c => !assignedKeys.has(candidateKey(c))))
      setManualSelected(new Set())
      setManualBulkErrors(errors)
      if (assignedKeys.size > 0) await refreshContacts()
    } finally {
      setManualBulkBusy(false)
    }
  }

  async function openDocBrowse() {
    setSyncMenuOpen(false)
    setDocBrowseItems([])
    setDocBrowseError(null)
    setDocBrowseOpen(true)
    setDocBrowseLoading(true)
    try {
      const result = await api.files.browse()
      setDocBrowsePath(result.path)
      setDocBrowseRoot(result.default_root)
      setDocBrowseItems(result.items)
    } catch (e: unknown) {
      setDocBrowseError(errorMessage(e, t))
    } finally {
      setDocBrowseLoading(false)
    }
  }

  async function browseInto(path: string) {
    setDocBrowseLoading(true)
    setDocBrowseError(null)
    try {
      const result = await api.files.browse(path)
      setDocBrowsePath(result.path)
      setDocBrowseItems(result.items)
    } catch (e: unknown) {
      setDocBrowseError(errorMessage(e, t))
    } finally {
      setDocBrowseLoading(false)
    }
  }

  async function attachDoc(item: FileBrowseItem) {
    if (!appId) return
    setDocAttaching(item.path)
    try {
      await api.files.attach(appId, item.path, item.name, item.type === 'folder')
      setDocBrowseOpen(false)
      await refreshContacts()
    } catch (e: unknown) {
      setDocBrowseError(errorMessage(e, t))
    } finally {
      setDocAttaching(null)
    }
  }

  async function saveBewerbung() {
    if (!appId || !bewerbungDraft.datum) return
    setSavingBewerbung(true)
    try {
      await api.applications.addEvent(appId, {
        typ: 'bewerbung',
        datum: bewerbungDraft.datum,
        titel: bewerbungDraft.titel.trim() || 'Bewerbung eingereicht',
      })
      await refreshContacts()
      setBewerbungDraft({ datum: '', titel: 'Bewerbung eingereicht' })
      setAddingBewerbung(false)
    } finally {
      setSavingBewerbung(false)
    }
  }

  async function saveOther() {
    if (!appId) return
    setSavingOther(true)
    try {
      await api.applications.addEvent(appId, {
        typ: otherDraft.typ,
        datum: otherDraft.datum || new Date().toISOString().slice(0, 10),
        titel: otherDraft.titel.trim() || undefined,
        notiz: otherDraft.notiz.trim() || undefined,
      })
      await refreshContacts()
      setOtherDraft({ typ: 'status', datum: '', titel: '', notiz: '' })
      setAddingOther(false)
    } finally {
      setSavingOther(false)
    }
  }

  async function saveFile() {
    if (!appId || !fileDraft.file) return
    setSavingFile(true)
    try {
      const event = await api.applications.addEvent(appId, {
        typ: 'file',
        datum: fileDraft.datum || new Date().toISOString().slice(0, 10),
        titel: fileDraft.titel.trim() || fileDraft.file.name,
      })
      await api.attachments.upload(event.id, fileDraft.file)
      await refreshContacts()
      setFileDraft({ datum: '', titel: '', file: null })
      if (fileInputRef.current) fileInputRef.current.value = ''
      setAddingFile(false)
    } finally {
      setSavingFile(false)
    }
  }

  async function saveContact() {
    if (!appId || !contactDraft.name || !contactDraft.email) return
    setSavingContact(true)
    try {
      const { telefon, ...rest } = contactDraft
      await api.contacts.add(appId, { ...rest, phones: telefon?.trim() ? [{ number: telefon.trim(), type: 'other' }] : [] })
      await refreshContacts()
      setContactDraft(EMPTY_CONTACT)
      setAddingContact(false)
    } finally {
      setSavingContact(false)
    }
  }

  async function linkContact(contactId: number) {
    if (!appId) return
    setSavingContact(true)
    try {
      await api.contacts.link(appId, contactId)
      await refreshContacts()
      setAddingContact(false)
      setLinkSearch('')
      setLinkResults([])
    } finally {
      setSavingContact(false)
    }
  }

  useEffect(() => {
    if (!firmaPicker) { setFirmaQuery(''); setFirmaResults([]); return }
    const t = setTimeout(async () => {
      setFirmaLoading(true)
      try { setFirmaResults(await api.companies.list({ search: firmaQuery || undefined })) }
      finally { setFirmaLoading(false) }
    }, 200)
    return () => clearTimeout(t)
  }, [firmaQuery, firmaPicker])

  useEffect(() => {
    if (!firmaPicker) return
    function handler(e: MouseEvent) {
      if (firmaPickerRef.current && !firmaPickerRef.current.contains(e.target as Node)) setFirmaPicker(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [firmaPicker])

  async function pickCompany(company: CompanyProfile) {
    setDraft(d => ({ ...d, firma: company.name_display ?? company.name_norm, company_profile_id: company.id }))
    setFirmaPicker(false)
  }

  async function createAndPickCompany(name: string) {
    setFirmaCreating(true)
    try {
      const company = await api.companies.create(name)
      setDraft(d => ({ ...d, firma: company.name_display ?? company.name_norm, company_profile_id: company.id }))
      setFirmaPicker(false)
    } finally {
      setFirmaCreating(false)
    }
  }

  useEffect(() => {
    if (!cFirmaPicker) { setCFirmaQuery(''); setCFirmaResults([]); return }
    const t = setTimeout(async () => {
      setCFirmaLoading(true)
      try { setCFirmaResults(await api.companies.list({ search: cFirmaQuery || undefined })) }
      finally { setCFirmaLoading(false) }
    }, 200)
    return () => clearTimeout(t)
  }, [cFirmaQuery, cFirmaPicker])

  useEffect(() => {
    if (!cFirmaPicker) return
    function handler(e: MouseEvent) {
      if (cFirmaRef.current && !cFirmaRef.current.contains(e.target as Node)) setCFirmaPicker(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [cFirmaPicker])

  useEffect(() => {
    if (!ecFirmaPicker) { setEcFirmaQuery(''); setEcFirmaResults([]); return }
    const t = setTimeout(async () => {
      setEcFirmaLoading(true)
      try { setEcFirmaResults(await api.companies.list({ search: ecFirmaQuery || undefined })) }
      finally { setEcFirmaLoading(false) }
    }, 200)
    return () => clearTimeout(t)
  }, [ecFirmaQuery, ecFirmaPicker])

  useEffect(() => {
    if (!ecFirmaPicker) return
    function handler(e: MouseEvent) {
      if (ecFirmaRef.current && !ecFirmaRef.current.contains(e.target as Node)) setEcFirmaPicker(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [ecFirmaPicker])

  async function pickContactCompany(c: CompanyProfile) {
    setContactDraft(d => ({ ...d, firma: c.name_display ?? c.name_norm, company_profile_id: c.id }))
    setCFirmaPicker(false)
  }

  async function createAndPickContactCompany(name: string) {
    setCFirmaCreating(true)
    try {
      const c = await api.companies.create(name)
      setContactDraft(d => ({ ...d, firma: c.name_display ?? c.name_norm, company_profile_id: c.id }))
      setCFirmaPicker(false)
    } finally {
      setCFirmaCreating(false)
    }
  }

  async function pickEditContactCompany(c: CompanyProfile) {
    setEditContactDraft(d => ({ ...d, firma: c.name_display ?? c.name_norm, company_profile_id: c.id }))
    setEcFirmaPicker(false)
  }

  async function createAndPickEditContactCompany(name: string) {
    setEcFirmaCreating(true)
    try {
      const c = await api.companies.create(name)
      setEditContactDraft(d => ({ ...d, firma: c.name_display ?? c.name_norm, company_profile_id: c.id }))
      setEcFirmaPicker(false)
    } finally {
      setEcFirmaCreating(false)
    }
  }

  useEffect(() => {
    if (addMode !== 'link') return
    if (!linkSearch.trim()) { setLinkResults([]); return }
    const timer = setTimeout(async () => {
      setLinkLoading(true)
      try {
        const res = await api.contacts.listAll({ search: linkSearch })
        const existing = new Set((app?.contacts ?? []).map(c => c.id))
        setLinkResults(res.filter(c => !existing.has(c.id)))
      } finally {
        setLinkLoading(false)
      }
    }, 250)
    return () => clearTimeout(timer)
  }, [linkSearch, addMode, app?.contacts])

  useEffect(() => {
    setSelectedEventIds(new Set())
    setSelectedContactIds(new Set())
  }, [activeTab])

  async function updateContact(contactId: number) {
    if (!appId) return
    setSavingContact(true)
    try {
      const { telefon, ...rest } = editContactDraft
      await api.contacts.update(appId, contactId, { ...rest, phones: telefon?.trim() ? [{ number: telefon.trim(), type: 'other' }] : [] })
      await refreshContacts()
      setEditingContactId(null)
    } finally {
      setSavingContact(false)
    }
  }

  async function deleteContact(contactId: number, name: string) {
    if (!appId || !confirm(t('contacts.confirmDelete', { name }))) return
    await api.contacts.delete(appId, contactId)
    await refreshContacts()
  }

  function toggleEventSelect(id: number) {
    setSelectedEventIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }

  function toggleContactSelect(id: number) {
    setSelectedContactIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }

  async function bulkDeleteSelectedEvents() {
    if (!appId || selectedEventIds.size === 0) return
    if (!confirm(t('timeline.confirmDeleteEntries', { count: selectedEventIds.size }))) return
    setBulkDeleting(true)
    try {
      await api.applications.bulkDeleteEvents(appId, [...selectedEventIds])
      setSelectedEventIds(new Set())
      await refreshContacts()
    } finally {
      setBulkDeleting(false)
    }
  }

  async function bulkDeleteSelectedContacts() {
    if (!appId || selectedContactIds.size === 0) return
    if (!confirm(t('contacts.confirmDeleteContacts', { count: selectedContactIds.size }))) return
    setBulkDeleting(true)
    try {
      await api.applications.bulkDeleteContacts(appId, [...selectedContactIds])
      setSelectedContactIds(new Set())
      await refreshContacts()
    } finally {
      setBulkDeleting(false)
    }
  }

  const updDot = (fieldKey?: string) =>
    fieldKey && updatedFields?.has(fieldKey)
      ? <span className="inline-block h-1.5 w-1.5 rounded-full bg-amber-400 shrink-0 ml-1 align-middle" />
      : null

  const field = (label: string, value?: string | null, fieldKey?: string) => {
    if (!value) return null
    const updated = !!fieldKey && !!updatedFields?.has(fieldKey)
    return (
      <div className={updated ? 'rounded px-2 py-0.5 -mx-2 bg-amber-50 ring-1 ring-inset ring-amber-200' : ''}>
        <dt className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}{updDot(fieldKey)}</dt>
        <dd className="mt-0.5 text-sm text-gray-900">{value}</dd>
      </div>
    )
  }

  const STEP_LABELS: Record<string, string> = {
    prospecting: t('pipeline.prospecting'),
    applied:     t('pipeline.applied'),
    hr:          t('pipeline.hr'),
    fb:          t('pipeline.fb'),
    waiting:     t('pipeline.waiting'),
    negotiating: t('pipeline.negotiating'),
    signed:      t('pipeline.signed'),
  }

  const reachedIdx = (() => {
    if (!app) return -1
    const idx = MAIN_PIPELINE.indexOf(app.main_status)
    if (idx >= 0) return idx
    // Rejected: infer last reached stage from timeline events
    if (!app.abgesagt || !app.events?.length) return -1
    const events = app.events
    const text = (e: { titel?: string; notiz?: string }) =>
      `${e.titel ?? ''} ${e.notiz ?? ''}`.toLowerCase()
    const gesprächCount = events.filter(e => e.typ === 'gespräch').length
    const hasBewerbung  = events.some(e => e.typ === 'bewerbung')
    const hasAngebot    = events.some(e =>
      /(angebot|salary|gehalts|verhandlung|offer letter)/i.test(text(e)))
    const hasFB         = events.some(e =>
      /(fachbereich|fach.?interview|technical|panel|2\. gespr|zweites gespr|3\. gespr)/i.test(text(e)))
    const hasWaiting    = events.some(e =>
      /(finale entscheidung|waiting|final decision|warten)/i.test(text(e)))
    let best = hasBewerbung ? MAIN_PIPELINE.indexOf('applied') : 0
    if (gesprächCount >= 1) best = Math.max(best, MAIN_PIPELINE.indexOf('hr'))
    if (gesprächCount >= 2 || hasFB) best = Math.max(best, MAIN_PIPELINE.indexOf('fb'))
    if (hasWaiting) best = Math.max(best, MAIN_PIPELINE.indexOf('waiting'))
    if (hasAngebot) best = Math.max(best, MAIN_PIPELINE.indexOf('negotiating'))
    return best
  })()

  const allEvents = app?.events ?? []
  const timelineEvents = useMemo(() => {
    const evs = allEvents.filter(ev => ev.typ !== 'file')
    const now = new Date()
    const cutoff: Date | null = (() => {
      if (timeFilter === 'all') return null
      const d = new Date(now)
      if (timeFilter === '1m') d.setMonth(d.getMonth() - 1)
      else if (timeFilter === '3m') d.setMonth(d.getMonth() - 3)
      else if (timeFilter === '6m') d.setMonth(d.getMonth() - 6)
      else if (timeFilter === '1y') d.setFullYear(d.getFullYear() - 1)
      return d
    })()
    return evs.filter(ev => {
      if (cutoff && ev.datum && new Date(ev.datum) < cutoff) return false
      if (typeFilter === 'all') return true
      if (typeFilter === 'mail') return ev.source === 'gmail' || ev.source === 'icloud_mail' || ev.typ === 'mail'
      if (typeFilter === 'calendar') return ev.source === 'gcal' || ev.source === 'icloud_cal'
      return ev.typ === typeFilter
    })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [app?.events, timeFilter, typeFilter])
  const fileEvents = allEvents.filter(ev => ev.typ === 'file')
  const rawTimelineEvents = allEvents.filter(ev => ev.typ !== 'file')

  // Unique event types present in this application's timeline (for type filter)
  const availableTypes = useMemo(() => {
    const types = new Set<string>()
    rawTimelineEvents.forEach(ev => {
      if (ev.source === 'gmail' || ev.source === 'icloud_mail') types.add('mail')
      else if (ev.source === 'gcal' || ev.source === 'icloud_cal') types.add('calendar')
      else if (ev.typ) types.add(ev.typ)
    })
    return Array.from(types)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [app?.events])

  return (
    <>
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="w-full max-w-3xl rounded-2xl bg-white shadow-2xl flex flex-col max-h-[90vh]">

        {/* Header */}
        <div className="flex items-start justify-between p-6 border-b border-gray-100">
          <div className="flex-1 min-w-0">
            {editing ? (
              <div className="space-y-2">
                {/* Company picker */}
                <div className="relative" ref={firmaPickerRef}>
                  <div className="flex items-center gap-2">
                    <CompanyLogo
                      name={draft.firma ?? app?.firma ?? ''}
                      website={app?.company_website}
                      size="sm"
                    />
                    <span className="text-base font-semibold text-gray-900 truncate flex-1 min-w-0">
                      {draft.firma || app?.firma || <span className="text-gray-400 font-normal">{t('pickCompanyPlaceholder')}</span>}
                    </span>
                    <button
                      type="button"
                      onClick={() => setFirmaPicker(o => !o)}
                      className="shrink-0 flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-800 px-2 py-1 rounded hover:bg-indigo-50"
                    >
                      <Building2 className="h-3.5 w-3.5" />
                      {t('changeCompany')}
                    </button>
                  </div>
                  {firmaPicker && (
                    <div className="absolute z-50 top-full left-0 mt-1 w-80 bg-white border border-gray-200 rounded-lg shadow-lg">
                      <div className="p-2 border-b border-gray-100">
                        <input
                          autoFocus
                          value={firmaQuery}
                          onChange={e => setFirmaQuery(e.target.value)}
                          placeholder={t('searchCompanyPlaceholder')}
                          className="w-full rounded border border-gray-200 px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500"
                        />
                      </div>
                      <div className="max-h-52 overflow-y-auto py-1">
                        {firmaLoading && <p className="text-xs text-gray-400 px-3 py-2">{t('searching')}</p>}
                        {!firmaLoading && firmaResults.length === 0 && !firmaQuery && (
                          <p className="text-xs text-gray-400 px-3 py-2 italic">{t('enterSearchTerm')}</p>
                        )}
                        {firmaResults.slice(0, 12).map(c => (
                          <button
                            key={c.id}
                            type="button"
                            onClick={() => pickCompany(c)}
                            className="w-full text-left px-3 py-1.5 text-sm hover:bg-indigo-50 hover:text-indigo-700 transition-colors flex items-center gap-2"
                          >
                            <CompanyLogo name={c.name_display ?? c.name_norm} website={c.website ?? undefined} size="sm" />
                            {c.name_display ?? c.name_norm}
                          </button>
                        ))}
                        {firmaQuery.trim() && (
                          <button
                            type="button"
                            disabled={firmaCreating}
                            onClick={() => createAndPickCompany(firmaQuery.trim())}
                            className="w-full text-left px-3 py-1.5 text-sm text-indigo-600 hover:bg-indigo-50 transition-colors flex items-center gap-2 border-t border-gray-100 mt-1"
                          >
                            <Plus className="h-3.5 w-3.5 shrink-0" />
                            {firmaCreating ? t('creating') : t('createNew', { name: firmaQuery.trim() })}
                          </button>
                        )}
                      </div>
                    </div>
                  )}
                </div>
                <input
                  className="w-full text-sm rounded-lg border border-gray-200 px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  value={draft.rolle ?? ''}
                  onChange={e => setDraft(d => ({ ...d, rolle: e.target.value }))}
                  placeholder={t('rolePlaceholder')}
                />
              </div>
            ) : (
              <>
                <div className="flex items-center gap-2.5">
                  <CompanyLogo
                    name={app?.is_headhunter ? ((app?.target_company_name_display ?? app?.zielfirma_bei_hh) || (app?.company_name_display ?? app?.firma) || '') : ((app?.company_name_display ?? app?.firma) || '')}
                    website={app?.is_headhunter ? (app?.target_company_website ?? app?.company_website) : app?.company_website}
                  />
                  <div className="flex items-baseline gap-2 min-w-0">
                    {app?.company_profile_id && onOpenCompany ? (
                      <button
                        onClick={() => onOpenCompany(app.company_profile_id!)}
                        className="text-lg font-semibold text-gray-900 truncate cursor-pointer hover:text-indigo-600 hover:underline"
                      >{app?.company_name_display ?? app?.firma}{updDot('firma')}</button>
                    ) : (
                      <h2 className="text-lg font-semibold text-gray-900 truncate">{app?.company_name_display ?? app?.firma}{updDot('firma')}</h2>
                    )}
                    <span className="text-xs text-gray-300 shrink-0 select-all">#{app?.id}</span>
                  </div>
                </div>
                <p className="text-sm text-gray-500 truncate">{app?.rolle}{updDot('rolle')}</p>
              </>
            )}
          </div>
          <div className="ml-4 flex items-center gap-1.5">
            {/* Split sync button */}
            <div className="relative flex rounded-lg border border-indigo-200" ref={syncMenuRef}>
              <button
                onClick={() => runSync(false)}
                disabled={syncing}
                title={t('sync.targetedTitle')}
                data-testid="sync-button"
                className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-indigo-600 bg-indigo-50 hover:bg-indigo-100 disabled:opacity-50 transition-colors rounded-l-lg"
              >
                <Crosshair className={`h-3.5 w-3.5 ${syncing ? 'animate-spin' : ''}`} />
                {syncing ? t('sync.syncing') : t('sync.sync')}
              </button>
              <button
                onClick={() => setSyncMenuOpen(o => !o)}
                disabled={syncing}
                data-testid="sync-menu-toggle"
                className="px-1.5 border-l border-indigo-200 text-indigo-400 bg-indigo-50 hover:bg-indigo-100 disabled:opacity-50 transition-colors rounded-r-lg"
              >
                <ChevronDown className={`h-3 w-3 transition-transform ${syncMenuOpen ? 'rotate-180' : ''}`} />
              </button>
              {syncMenuOpen && (
                <div className="absolute right-0 top-full mt-1 z-50 w-44 rounded-lg border border-gray-200 bg-white shadow-lg py-1">
                  <button
                    onClick={() => runSync(false)}
                    className="w-full text-left px-3 py-2 text-xs text-gray-700 hover:bg-gray-50 flex items-center gap-2"
                  >
                    <Crosshair className="h-3.5 w-3.5 text-indigo-400" />
                    {t('sync.sync')}
                  </button>
                  <button
                    onClick={() => runSync(true)}
                    className="w-full text-left px-3 py-2 text-xs text-gray-700 hover:bg-gray-50 flex items-center gap-2"
                  >
                    <RefreshCw className="h-3.5 w-3.5 text-amber-400" />
                    <span>
                      {t('sync.resync')}
                      <span className="block text-[10px] text-gray-400">{t('sync.resyncHint')}</span>
                    </span>
                  </button>
                  <button
                    onClick={clearSyncEvents}
                    className="w-full text-left px-3 py-2 text-xs text-gray-700 hover:bg-gray-50 flex items-center gap-2"
                  >
                    <Trash2 className="h-3.5 w-3.5 text-red-400" />
                    <span>
                      {t('sync.clearEvents')}
                      <span className="block text-[10px] text-gray-400">{t('sync.clearEventsHint')}</span>
                    </span>
                  </button>
                  <hr className="my-1 border-gray-100" />
                  <button
                    onClick={openManual}
                    data-testid="sync-menu-manual-assign"
                    className="w-full text-left px-3 py-2 text-xs text-gray-700 hover:bg-gray-50 flex items-center gap-2"
                  >
                    <Search className="h-3.5 w-3.5 text-green-500" />
                    <span>
                      {t('sync.manualAssign')}
                      <span className="block text-[10px] text-gray-400">{t('sync.manualAssignHint')}</span>
                    </span>
                  </button>
                  <button
                    onClick={() => { setSyncMenuOpen(false); setActiveTab('attachments') }}
                    className="w-full text-left px-3 py-2 text-xs text-gray-700 hover:bg-gray-50 flex items-center gap-2"
                  >
                    <FolderOpen className="h-3.5 w-3.5 text-amber-500" />
                    <span>
                      {t('sync.addDocument')}
                      <span className="block text-[10px] text-gray-400">{t('sync.addDocumentHint')}</span>
                    </span>
                  </button>
                </div>
              )}
            </div>
            <button onClick={onClose} className="p-1 rounded-lg hover:bg-gray-100 text-gray-400">
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        {/* Lifecycle bar */}
        {app && (
          <div className="px-6 py-3 border-b border-gray-100 bg-gray-50/60">
            <div className="flex items-start">
              {MAIN_PIPELINE.map((step, idx) => {
                const isPast    = idx < reachedIdx
                const isCurrent = idx === reachedIdx && !app.abgesagt
                // Short sub-status hint for hr/fb when that step is current
                const subHint = isCurrent && app.sub_status ? (() => {
                  const m = app.sub_status!.match(/^(\d+)_(scheduled|done)$/)
                  if (!m) return null
                  const n = m[1]; const kind = m[2]
                  const kindLabel = kind === 'scheduled' ? t('pipeline.scheduled') : t('pipeline.done')
                  return n === '1' ? kindLabel : `${n}. ${kindLabel}`
                })() : null
                return (
                  <div key={step} className="flex items-start flex-1 min-w-0">
                    {/* node */}
                    <div className="flex flex-col items-center w-full min-w-0">
                      {isCurrent ? (
                        // Active step: prominent ring + filled center
                        <div className="w-5 h-5 rounded-full shrink-0 border-2 border-indigo-600 bg-indigo-600 ring-2 ring-indigo-200 ring-offset-1 flex items-center justify-center">
                          <span className="w-1.5 h-1.5 rounded-full bg-white block" />
                        </div>
                      ) : isPast ? (
                        // Completed: muted filled with checkmark
                        <div className="w-4 h-4 rounded-full shrink-0 bg-indigo-300 flex items-center justify-center mt-0.5">
                          <span className="text-[7px] font-bold text-white leading-none">✓</span>
                        </div>
                      ) : (
                        // Future: empty
                        <div className="w-4 h-4 rounded-full shrink-0 border-2 border-gray-200 bg-white mt-0.5" />
                      )}
                      <span className={`mt-1 text-center text-[9px] leading-tight w-full px-0.5 ${
                        isCurrent ? 'text-indigo-700 font-semibold'
                        : isPast  ? 'text-indigo-300'
                        : 'text-gray-300'
                      }`}>
                        {STEP_LABELS[step]}
                      </span>
                      {subHint && (
                        <span className="text-[8px] text-indigo-400 text-center leading-tight mt-0.5 w-full px-0.5">
                          {subHint}
                        </span>
                      )}
                    </div>
                    {/* connector to next */}
                    {idx < MAIN_PIPELINE.length - 1 && (
                      <div className={`h-px shrink-0 mt-[9px] w-3 ${
                        idx < reachedIdx ? 'bg-indigo-200' : 'bg-gray-200'
                      }`} />
                    )}
                  </div>
                )
              })}
              {/* Connector to rejection node */}
              <div className={`h-px shrink-0 mt-[9px] w-3 ${
                app.abgesagt ? 'bg-red-200' : 'bg-gray-200'
              }`} />
              {/* Absage node */}
              <div className="flex flex-col items-center shrink-0">
                {app.abgesagt ? (
                  <div className="w-5 h-5 rounded-full border-2 border-red-400 bg-red-400 ring-2 ring-red-100 ring-offset-1 flex items-center justify-center">
                    <span className="text-[8px] font-bold text-white leading-none">✕</span>
                  </div>
                ) : (
                  <div className="w-4 h-4 rounded-full border-2 border-gray-200 bg-white mt-0.5" />
                )}
                <span className={`mt-1 text-center text-[9px] leading-tight ${
                  app.abgesagt ? 'text-red-500 font-semibold' : 'text-gray-300'
                }`}>{t('pipeline.rejected')}</span>
              </div>
            </div>
          </div>
        )}

        {/* Progress panel */}
        {syncing && (Object.keys(syncProgress).length > 0 || liStatus?.status === 'running') && (
          <div className="border-b border-indigo-100 bg-indigo-50 px-5 py-3 space-y-2">
            <p className="text-[10px] font-semibold text-indigo-500 uppercase tracking-wide flex items-center gap-1.5">
              <Crosshair className="h-3 w-3 animate-spin" /> {t('sync.running')}
            </p>
            {Object.values(syncProgress).map(p => (
              <div key={p.label} className="space-y-0.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-gray-700">{p.label}</span>
                  <span className="text-[10px] text-gray-400 tabular-nums">
                    {p.done ? '✓' : p.total > 0 ? `${p.current}/${p.total}` : '…'}
                  </span>
                </div>
                <div className="h-1 rounded-full bg-indigo-100 overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-300 ${p.done ? 'bg-green-400' : 'bg-indigo-500'}`}
                    style={{ width: `${p.done ? 100 : p.total > 0 ? Math.round(p.current / p.total * 100) : 10}%` }}
                  />
                </div>
                <p className="text-[10px] text-gray-400 truncate">{p.step}</p>
              </div>
            ))}
            {liStatus?.status === 'running' && (
              <div className="space-y-0.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-gray-700">LinkedIn</span>
                  <span className="text-[10px] text-gray-400 tabular-nums">
                    {liStatus.total > 0 ? `${liStatus.processed}/${liStatus.total}` : '…'}
                  </span>
                </div>
                <div className="h-1 rounded-full bg-indigo-100 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-[#0a66c2] transition-all duration-300"
                    style={{ width: `${liStatus.total > 0 ? Math.round(liStatus.processed / liStatus.total * 100) : 10}%` }}
                  />
                </div>
                <p className="text-[10px] text-gray-400 truncate">{liStatus.step}</p>
              </div>
            )}
          </div>
        )}

        {/* Sync result banner */}
        {syncResult && (
          <div data-testid="sync-result-banner" className={`px-5 py-2 text-xs flex items-center justify-between border-b ${syncResult.errors.length > 0 ? 'bg-red-50 border-red-100 text-red-700' : 'bg-green-50 border-green-100 text-green-700'}`}>
            <span>
              {syncResult.errors.length > 0
                ? t('sync.resultError', { message: syncResult.errors[0] })
                : syncResult.created < 0
                  ? t('sync.resultDeleted', { count: Math.abs(syncResult.created) })
                  : `${t('sync.resultDone', { count: syncResult.created })}${liStatus && liStatus.status === 'done' ? t('sync.resultLinkedinSuggestions', { count: liStatus.updated }) : ''}`}
            </span>
            <button onClick={() => { setSyncResult(null); setLiStatus(null) }} className="ml-2 opacity-60 hover:opacity-100">✕</button>
          </div>
        )}

        {/* Tab bar */}
        <div className="flex border-b border-gray-100 px-6 shrink-0 gap-1">
          {([
            { id: 'overview',     label: t('tabs.overview'),  icon: null },
            { id: 'timeline',     label: t('tabs.timeline'),    count: rawTimelineEvents.length },
            { id: 'attachments',  label: t('tabs.attachments'),    count: fileEvents.length },
            { id: 'contacts',     label: t('tabs.contacts'),   count: app?.contacts?.length ?? 0, icon: <Users className="h-3 w-3" /> },
            { id: 'salary',       label: t('tabs.salary'),     icon: <Wallet className="h-3 w-3" />, alert: !!app?.salary_mismatch },
          ] as const).map(tab => (
            <button
              key={tab.id}
              data-testid={`modal-tab-${tab.id}`}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-1.5 px-3 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px ${
                activeTab === tab.id ? 'border-indigo-600 text-indigo-600' : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {tab.label}
              {'count' in tab && (tab.count ?? 0) > 0 && (
                <span className="rounded-full bg-gray-100 px-1.5 py-0.5 text-[10px] font-medium text-gray-500 leading-none">{tab.count}</span>
              )}
              {'alert' in tab && tab.alert && (
                <span className="h-1.5 w-1.5 rounded-full bg-red-500 shrink-0" />
              )}
            </button>
          ))}
        </div>

        {/* Tab: Übersicht */}
        {activeTab === 'overview' && (
        <div className="overflow-y-auto flex-1 p-6 space-y-5">

          {/* Status */}
          <div>
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
              {t('overview.status')}{updDot('main_status')}{updDot('sub_status')}{updDot('abgesagt')}
            </p>
            {editing ? (
              <div className="space-y-2">
                <div className="flex flex-wrap gap-1.5">
                  {([...MAIN_PIPELINE, 'rejected'] as MainStatus[]).map(s => (
                    <button key={s} type="button"
                      data-testid={`status-btn-${s}`}
                      onClick={() => setDraft(d => ({ ...d, main_status: s, sub_status: (s === 'hr' || s === 'fb') ? (d.sub_status ?? '1_scheduled') : undefined }))}
                      className={`text-xs px-2.5 py-1 rounded-full border transition-all ${draft.main_status === s ? `${MAIN_STATUS_COLORS[s]} border-transparent ring-2 ring-offset-1 ring-indigo-400` : 'border-gray-200 text-gray-600 hover:border-gray-300'}`}
                    >{mainStatusLabel(s)}</button>
                  ))}
                </div>
                {(draft.main_status === 'hr' || draft.main_status === 'fb') && (
                  <div className="flex flex-wrap gap-1.5 pl-1 border-l-2 border-indigo-200">
                    {SUB_STATUS_SEQUENCE.map(sub => (
                      <button key={sub} type="button" onClick={() => setDraft(d => ({ ...d, sub_status: sub }))}
                        className={`text-xs px-2.5 py-1 rounded-full border transition-all ${draft.sub_status === sub ? 'bg-indigo-100 text-indigo-800 border-indigo-300 font-medium' : 'border-gray-200 text-gray-500 hover:border-gray-300'}`}
                      >{subStatusLabel(sub)}</button>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <StatusBadge status={app?.main_status ?? 'applied'} subStatus={app?.sub_status} />
            )}
          </div>

          {/* Flags */}
          {editing && (
            <div className="flex gap-4">
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input type="checkbox" checked={!!draft.is_headhunter}
                  onChange={e => setDraft(d => ({ ...d, is_headhunter: e.target.checked }))}
                  className="rounded border-gray-300 text-indigo-600" />
                {t('headhunter')}
              </label>
            </div>
          )}

          {/* Meta fields */}
          {editing ? (
            <div className="grid grid-cols-2 gap-3">
              {([['quelle', t('overview.sourcePlaceholder')], ['zielfirma_bei_hh', t('overview.targetCompanyPlaceholder')], ['wurde_besetzt_von', t('overview.filledByPlaceholder')]] as const).map(([key, placeholder]) => (
                <input key={key}
                  className="rounded-lg border border-gray-200 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder={placeholder}
                  value={(draft as Record<string, string>)[key] ?? ''}
                  onChange={e => setDraft(d => ({ ...d, [key]: e.target.value }))}
                />
              ))}
              <LocationSearchInput
                value={draft.ort ?? ''}
                onChange={v => setDraft(d => ({ ...d, ort: v }))}
                placeholder={t('overview.locationPlaceholder')}
              />
              <div className="col-span-2 rounded-lg border border-gray-100 bg-gray-50 px-3 py-1.5 text-sm text-gray-500">
                <span className="text-xs text-gray-400 mr-1">{t('overview.appliedDate')}</span>
                {app?.datum_bewerbung ? formatDate(app.datum_bewerbung, locale) : <span className="italic">{t('overview.appliedDateHint')}</span>}
              </div>
            </div>
          ) : (
            <dl className="grid grid-cols-2 gap-3">
              {field(t('overview.fieldSource'), app?.quelle, 'quelle')}
              {field(
                t('overview.fieldLocation'),
                app?.ort && app.distance_km != null
                  ? `${app.ort} · ${t('overview.distanceKm', { km: Math.round(app.distance_km) })}`
                  : app?.ort,
                'ort',
              )}
              {field(t('overview.fieldAppliedDate'), app?.datum_bewerbung)}
              {field(t('overview.fieldLastUpdate'), app?.letztes_update)}
              {field(t('overview.fieldTargetCompany'), app?.zielfirma_bei_hh, 'zielfirma_bei_hh')}
              {field(t('overview.fieldFilledBy'), app?.wurde_besetzt_von, 'wurde_besetzt_von')}
              {app?.is_headhunter && (
                <div className={updatedFields?.has('is_headhunter') ? 'rounded px-2 py-0.5 -mx-2 bg-amber-50 ring-1 ring-inset ring-amber-200' : ''}>
                  <dt className="text-xs font-medium text-gray-500 uppercase tracking-wide">{t('headhunter')}{updDot('is_headhunter')}</dt>
                  <dd className="mt-0.5 text-sm text-indigo-700 font-medium">{t('overview.yes')}</dd>
                </div>
              )}
              {app?.ghosting && (
                <div className={updatedFields?.has('ghosting') ? 'rounded px-2 py-0.5 -mx-2 bg-amber-50 ring-1 ring-inset ring-amber-200' : ''}>
                  <dt className="text-xs font-medium text-gray-500 uppercase tracking-wide">{t('overview.ghosting')}{updDot('ghosting')}</dt>
                  <dd className="mt-0.5 text-sm text-red-600 font-medium">{t('overview.yes')}</dd>
                </div>
              )}
            </dl>
          )}

          {/* Stellenanzeige */}
          <div className={!editing && updatedFields?.has('stellenanzeige_url') ? 'rounded px-2 py-1 -mx-2 bg-amber-50 ring-1 ring-inset ring-amber-200' : ''}>
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">
              {t('overview.jobPosting')}{updDot('stellenanzeige_url')}
            </p>
            {editing ? (
              <input type="url"
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                value={draft.stellenanzeige_url ?? ''} placeholder={t('overview.jobPostingPlaceholder')}
                onChange={e => setDraft(d => ({ ...d, stellenanzeige_url: e.target.value || undefined }))}
              />
            ) : app?.stellenanzeige_url ? (
              <a href={app.stellenanzeige_url} target="_blank" rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-sm text-indigo-600 hover:text-indigo-800 hover:underline break-all">
                <ExternalLink className="h-3.5 w-3.5 shrink-0" />{app.stellenanzeige_url}
              </a>
            ) : <span className="text-gray-400 italic text-sm">{t('overview.noLink')}</span>}
          </div>

          {/* Kommentar */}
          <div className={!editing && updatedFields?.has('kommentar') ? 'rounded px-2 py-1 -mx-2 bg-amber-50 ring-1 ring-inset ring-amber-200' : ''}>
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">
              {t('overview.comment')}{updDot('kommentar')}
            </p>
            {editing ? (
              <textarea rows={4}
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                value={draft.kommentar ?? ''} placeholder={t('overview.commentPlaceholder')}
                onChange={e => setDraft(d => ({ ...d, kommentar: e.target.value }))}
              />
            ) : (
              <p className="text-sm text-gray-700 whitespace-pre-wrap">{app?.kommentar || <span className="text-gray-400 italic">{t('overview.noComment')}</span>}</p>
            )}
          </div>

          {/* Gesprächsnotizen (view only) */}
          {!editing && [app?.gespraech_1, app?.gespraech_2, app?.gespraech_3, app?.gespraech_4, app?.gespraech_5].some(Boolean) && (
            <div>
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">{t('overview.interviewNotes')}</p>
              <div className="space-y-2">
                {[app?.gespraech_1, app?.gespraech_2, app?.gespraech_3, app?.gespraech_4, app?.gespraech_5].map((g, i) => {
                  if (!g) return null
                  const gKey = `gespraech_${i + 1}` as keyof Application
                  const gUpdated = updatedFields?.has(gKey as string)
                  return (
                    <div key={i} className={`rounded-lg border px-3 py-2 ${gUpdated ? 'border-amber-200 bg-amber-50' : 'border-gray-100 bg-gray-50'}`}>
                      <p className="text-[10px] text-gray-400 font-medium uppercase mb-0.5">
                        {t('overview.interviewNote', { n: i + 1 })}{gUpdated && <span className="inline-block h-1.5 w-1.5 rounded-full bg-amber-400 ml-1 align-middle" />}
                      </p>
                      <p className="text-sm text-gray-700 whitespace-pre-wrap">{g}</p>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* KI-Einschätzung */}
          {!editing && (
            <div>
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                  {app?.abgesagt ? t('overview.aiRejectionAnalysis') : t('overview.aiAssessment')}
                </p>
                <button
                  onClick={runAiAssess}
                  disabled={aiAssessing}
                  data-testid="ai-reassess-button"
                  className="flex items-center gap-1 text-[10px] text-purple-600 hover:text-purple-800 disabled:opacity-50"
                >
                  <Sparkles className={`h-3 w-3 ${aiAssessing ? 'animate-pulse' : ''}`} />
                  {aiAssessing ? t('overview.analyzing') : t('overview.reassess')}
                </button>
              </div>
              {app?.ai_color ? (
                <div className={`rounded-lg border px-3 py-2.5 ${
                  app.ai_color === 'green' ? 'border-green-200 bg-green-50' :
                  app.ai_color === 'red'   ? 'border-red-200 bg-red-50'     : 'border-yellow-200 bg-yellow-50'
                }`}>
                  {!app.abgesagt && (
                    <div className="flex items-center gap-2 mb-1.5">
                      <span className={`shrink-0 h-2.5 w-2.5 rounded-full ${
                        app.ai_color === 'green' ? 'bg-green-500' :
                        app.ai_color === 'red'   ? 'bg-red-500'   : 'bg-yellow-400'
                      }`} />
                      <span className={`text-xs font-semibold ${
                        app.ai_color === 'green' ? 'text-green-700' :
                        app.ai_color === 'red'   ? 'text-red-700'   : 'text-yellow-700'
                      }`}>
                        {app.ai_color === 'green' ? t('overview.chanceHigh') :
                         app.ai_color === 'red'   ? t('overview.chanceLow') : t('overview.chanceMedium')}
                      </span>
                    </div>
                  )}
                  {app.ai_reasoning && (
                    <p className="text-xs text-gray-500 leading-snug mb-2 italic">{app.ai_reasoning}</p>
                  )}
                  <p className="text-sm text-gray-700 leading-snug font-medium">{app.ai_next_step}</p>
                  {app.ai_assessed_at && (
                    <p className="text-[10px] text-gray-400 mt-1.5">
                      {t('overview.assessedAt', { date: formatDate(app.ai_assessed_at, locale) })}
                    </p>
                  )}
                </div>
              ) : (
                <div className="rounded-lg border border-gray-100 bg-gray-50 px-3 py-2.5 flex items-center justify-between">
                  <span className="text-sm text-gray-400 italic">{t('overview.noAssessmentYet')}</span>
                  <button
                    onClick={runAiAssess}
                    disabled={aiAssessing}
                    data-testid="ai-assess-now-button"
                    className="text-xs text-purple-600 hover:text-purple-800 flex items-center gap-1 disabled:opacity-50"
                  >
                    <Sparkles className="h-3 w-3" />
                    {t('overview.assessNow')}
                  </button>
                </div>
              )}
              {aiAssessError && (
                <p className="mt-2 text-xs text-red-600">{aiAssessError}</p>
              )}
            </div>
          )}
        </div>
        )}

        {/* Tab: Verlauf */}
        {activeTab === 'timeline' && (
        <div className="overflow-y-auto flex-1 flex flex-col">
          {/* Filter row */}
          <div className="px-6 pt-4 pb-3 border-b border-gray-100 space-y-2 shrink-0">
            {/* Time filter */}
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-xs text-gray-400 shrink-0 mr-0.5">{t('timeline.period')}</span>
              {([['all', t('timeline.periodAll')], ['1m', t('timeline.period1m')], ['3m', t('timeline.period3m')], ['6m', t('timeline.period6m')], ['1y', t('timeline.period1y')]] as const).map(([v, l]) => (
                <button key={v} onClick={() => setTimeFilter(v)}
                  className={`px-2.5 py-1 rounded-full text-xs border transition-colors ${timeFilter === v ? 'bg-indigo-600 text-white border-indigo-600' : 'border-gray-200 text-gray-500 hover:border-indigo-300 hover:text-indigo-600'}`}
                >{l}</button>
              ))}
            </div>
            {/* Type filter */}
            {availableTypes.length > 0 && (
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="text-xs text-gray-400 shrink-0 mr-0.5">{t('timeline.type')}</span>
                <button onClick={() => setTypeFilter('all')}
                  className={`px-2.5 py-1 rounded-full text-xs border transition-colors ${typeFilter === 'all' ? 'bg-indigo-600 text-white border-indigo-600' : 'border-gray-200 text-gray-500 hover:border-indigo-300 hover:text-indigo-600'}`}
                >{t('timeline.typeAll')}</button>
                {availableTypes.map(typ => (
                  <button key={typ} onClick={() => setTypeFilter(typ)}
                    className={`px-2.5 py-1 rounded-full text-xs border transition-colors ${typeFilter === typ ? 'bg-indigo-600 text-white border-indigo-600' : 'border-gray-200 text-gray-500 hover:border-indigo-300 hover:text-indigo-600'}`}
                  >{t(`eventType.${typ}`, { defaultValue: typ })}</button>
                ))}
              </div>
            )}
            {timelineEvents.length > 0 && (
              <div className="flex items-center gap-2">
                <input type="checkbox"
                  checked={timelineEvents.length > 0 && timelineEvents.every(ev => selectedEventIds.has(ev.id))}
                  ref={el => { if (el) el.indeterminate = selectedEventIds.size > 0 && !timelineEvents.every(ev => selectedEventIds.has(ev.id)) }}
                  onChange={() => {
                    setSelectedEventIds(prev => {
                      const allSelected = timelineEvents.every(ev => prev.has(ev.id))
                      if (allSelected) return new Set()
                      return new Set(timelineEvents.map(ev => ev.id))
                    })
                  }}
                  className="rounded border-gray-300 text-indigo-600 cursor-pointer"
                />
                <span className="text-xs text-gray-400">{t('timeline.selectAll')}</span>
                {selectedEventIds.size > 0 && (
                  <button onClick={bulkDeleteSelectedEvents} disabled={bulkDeleting}
                    className="flex items-center gap-1 text-xs text-red-600 hover:text-red-700 disabled:opacity-50 ml-2">
                    <Trash2 className="h-3 w-3" /> {t('timeline.deleteEntries', { count: selectedEventIds.size })}
                  </button>
                )}
              </div>
            )}
          </div>

          <div className="overflow-y-auto flex-1 p-6 space-y-3">
            {/* Add note / Bewerbung / Weiteres / Anhang */}
            {!addingNote && !addingBewerbung && !addingOther && !addingFile && (
              <div className="flex items-center gap-3 mb-1 flex-wrap">
                <button onClick={() => setAddingNote(true)} className="flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-700">
                  <Plus className="h-3 w-3" /> {t('timeline.addNote')}
                </button>
                <button onClick={() => setAddingBewerbung(true)} className="flex items-center gap-1 text-xs text-green-600 hover:text-green-700">
                  <Plus className="h-3 w-3" /> {t('timeline.addApplication')}
                </button>
                <button onClick={() => setAddingOther(true)} className="flex items-center gap-1 text-xs text-purple-600 hover:text-purple-700">
                  <Plus className="h-3 w-3" /> {t('timeline.addOther')}
                </button>
                <button onClick={() => setAddingFile(true)} className="flex items-center gap-1 text-xs text-amber-600 hover:text-amber-700">
                  <Paperclip className="h-3 w-3" /> {t('timeline.addAttachment')}
                </button>
              </div>
            )}

            {addingNote && (
              <div className="rounded-lg border border-indigo-200 bg-indigo-50 p-3 space-y-2">
                <textarea autoFocus rows={2}
                  className="w-full rounded-md border border-gray-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder={t('timeline.notePlaceholder')} value={noteDraft.notiz}
                  onChange={e => setNoteDraft(d => ({ ...d, notiz: e.target.value }))}
                />
                <div className="flex items-center justify-between">
                  <input type="date"
                    className="rounded-md border border-gray-200 px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    value={noteDraft.datum} onChange={e => setNoteDraft(d => ({ ...d, datum: e.target.value }))}
                  />
                  <div className="flex gap-2">
                    <button type="button" onClick={() => { setAddingNote(false); setNoteDraft({ notiz: '', datum: '' }) }} className="text-xs text-gray-500 hover:text-gray-700 px-2 py-1">{t('timeline.cancel')}</button>
                    <button type="button" disabled={!noteDraft.notiz.trim() || savingNote} onClick={saveNote} className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50">
                      {savingNote ? t('timeline.saving') : t('timeline.save')}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {addingBewerbung && (
              <div className="rounded-lg border border-green-200 bg-green-50 p-3 space-y-2">
                <p className="text-xs text-green-700 font-medium">{t('timeline.setApplicationDate')}</p>
                <input autoFocus
                  className="w-full rounded-md border border-gray-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
                  placeholder={t('timeline.titlePlaceholder')} value={bewerbungDraft.titel}
                  onChange={e => setBewerbungDraft(d => ({ ...d, titel: e.target.value }))}
                />
                <div className="flex items-center justify-between">
                  <input type="date"
                    className="rounded-md border border-gray-200 px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-green-500"
                    value={bewerbungDraft.datum} onChange={e => setBewerbungDraft(d => ({ ...d, datum: e.target.value }))}
                  />
                  <div className="flex gap-2">
                    <button type="button" onClick={() => { setAddingBewerbung(false); setBewerbungDraft({ datum: '', titel: 'Bewerbung eingereicht' }) }} className="text-xs text-gray-500 hover:text-gray-700 px-2 py-1">{t('timeline.cancel')}</button>
                    <button type="button" disabled={!bewerbungDraft.datum || savingBewerbung} onClick={saveBewerbung} className="rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700 disabled:opacity-50">
                      {savingBewerbung ? t('timeline.saving') : t('timeline.save')}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {addingOther && (
              <div className="rounded-lg border border-purple-200 bg-purple-50 p-3 space-y-2">
                <select autoFocus
                  className="w-full rounded-md border border-gray-200 px-2 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                  value={otherDraft.typ} onChange={e => setOtherDraft(d => ({ ...d, typ: e.target.value }))}
                >
                  {OTHER_EVENT_TYPES.map(o => (
                    <option key={o.value} value={o.value}>{t(`eventType.${o.value}`, { defaultValue: o.label })}</option>
                  ))}
                </select>
                <input
                  className="w-full rounded-md border border-gray-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder={t('timeline.titleOptionalPlaceholder')} value={otherDraft.titel}
                  onChange={e => setOtherDraft(d => ({ ...d, titel: e.target.value }))}
                />
                <textarea rows={2}
                  className="w-full rounded-md border border-gray-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder={t('timeline.noteOptionalPlaceholder')} value={otherDraft.notiz}
                  onChange={e => setOtherDraft(d => ({ ...d, notiz: e.target.value }))}
                />
                <div className="flex items-center justify-between">
                  <input type="date"
                    className="rounded-md border border-gray-200 px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-purple-500"
                    value={otherDraft.datum} onChange={e => setOtherDraft(d => ({ ...d, datum: e.target.value }))}
                  />
                  <div className="flex gap-2">
                    <button type="button" onClick={() => { setAddingOther(false); setOtherDraft({ typ: 'status', datum: '', titel: '', notiz: '' }) }} className="text-xs text-gray-500 hover:text-gray-700 px-2 py-1">{t('timeline.cancel')}</button>
                    <button type="button" disabled={savingOther} onClick={saveOther} className="rounded-md bg-purple-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-purple-700 disabled:opacity-50">
                      {savingOther ? t('timeline.saving') : t('timeline.save')}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {addingFile && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 space-y-2">
                <input
                  ref={fileInputRef}
                  type="file"
                  className="hidden"
                  onChange={e => { const f = e.target.files?.[0] ?? null; setFileDraft(d => ({ ...d, file: f, titel: d.titel || f?.name || '' })) }}
                />
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="flex items-center gap-1.5 rounded-md border border-amber-300 bg-white px-3 py-1.5 text-xs font-medium text-amber-700 hover:bg-amber-100"
                >
                  <Paperclip className="h-3.5 w-3.5" />
                  {fileDraft.file ? fileDraft.file.name : t('timeline.chooseFile')}
                </button>
                <input
                  className="w-full rounded-md border border-gray-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                  placeholder={t('timeline.fileTitlePlaceholder')} value={fileDraft.titel}
                  onChange={e => setFileDraft(d => ({ ...d, titel: e.target.value }))}
                />
                <div className="flex items-center justify-between">
                  <input type="date"
                    className="rounded-md border border-gray-200 px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-amber-500"
                    value={fileDraft.datum} onChange={e => setFileDraft(d => ({ ...d, datum: e.target.value }))}
                  />
                  <div className="flex gap-2">
                    <button type="button" onClick={() => { setAddingFile(false); setFileDraft({ datum: '', titel: '', file: null }); if (fileInputRef.current) fileInputRef.current.value = '' }} className="text-xs text-gray-500 hover:text-gray-700 px-2 py-1">{t('timeline.cancel')}</button>
                    <button type="button" disabled={!fileDraft.file || savingFile} onClick={saveFile} className="rounded-md bg-amber-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-700 disabled:opacity-50">
                      {savingFile ? t('timeline.uploading') : t('timeline.upload')}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {timelineEvents.length === 0 && !addingNote && !addingBewerbung && !addingOther && !addingFile ? (
              <p className="text-sm text-gray-400 italic">
                {rawTimelineEvents.length > 0 ? t('timeline.noEntriesForFilter') : t('timeline.noEntriesYet')}
              </p>
            ) : (
              <div className="relative">
                <div className="absolute left-2 top-0 bottom-0 w-px bg-gray-200" />
                <div className="space-y-3 pl-7">
                  {[...timelineEvents].sort(compareTimelineEventsNewestFirst).map(ev => (
                    <div key={ev.id} className="flex items-start gap-2">
                      <input type="checkbox" checked={selectedEventIds.has(ev.id)} onChange={() => toggleEventSelect(ev.id)}
                        className="mt-1 rounded border-gray-300 text-indigo-600 cursor-pointer shrink-0" />
                      <div className="flex-1 min-w-0">
                        <TimelineEvent event={ev} appId={appId!} onUpdated={refreshContacts} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
        )}

        {/* Tab: Anhänge */}
        {activeTab === 'attachments' && (
        <div className="overflow-y-auto flex-1 p-6 space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide flex items-center gap-1.5">
              <File className="h-3.5 w-3.5" /> {t('attachments.documents')}
            </p>
            <button
              onClick={openDocBrowse}
              className="flex items-center gap-1.5 text-xs text-indigo-600 hover:text-indigo-700"
            >
              <Plus className="h-3 w-3" /> {t('attachments.addDocument')}
            </button>
          </div>
          {fileEvents.length === 0 ? (
            <p className="text-sm text-gray-400 italic">{t('attachments.none')}</p>
          ) : (
            <>
              <div className="flex items-center gap-2">
                <input type="checkbox"
                  checked={fileEvents.length > 0 && fileEvents.every(ev => selectedEventIds.has(ev.id))}
                  ref={el => { if (el) el.indeterminate = selectedEventIds.size > 0 && !fileEvents.every(ev => selectedEventIds.has(ev.id)) }}
                  onChange={() => {
                    setSelectedEventIds(prev => {
                      const allSelected = fileEvents.every(ev => prev.has(ev.id))
                      if (allSelected) return new Set()
                      return new Set(fileEvents.map(ev => ev.id))
                    })
                  }}
                  className="rounded border-gray-300 text-indigo-600 cursor-pointer"
                />
                <span className="text-xs text-gray-400">{t('attachments.selectAll')}</span>
                {selectedEventIds.size > 0 && (
                  <button onClick={bulkDeleteSelectedEvents} disabled={bulkDeleting}
                    className="flex items-center gap-1 text-xs text-red-600 hover:text-red-700 disabled:opacity-50 ml-2">
                    <Trash2 className="h-3 w-3" /> {t('attachments.deleteAttachments', { count: selectedEventIds.size })}
                  </button>
                )}
              </div>
              <div className="space-y-1">
                {fileEvents.map(ev => (
                  <div key={ev.id} className="flex items-center gap-2">
                    <input type="checkbox" checked={selectedEventIds.has(ev.id)} onChange={() => toggleEventSelect(ev.id)}
                      className="rounded border-gray-300 text-indigo-600 cursor-pointer shrink-0" />
                    <div className="flex-1 min-w-0">
                      <FileRow event={ev} appId={appId!} onDeleted={refreshContacts} />
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
        )}

        {/* Tab: Kontakte */}
        {activeTab === 'contacts' && (
        <div className="overflow-y-auto flex-1 p-6 space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{t('contacts.title')}</p>
            {!addingContact && (
              <button onClick={() => { setAddingContact(true); setAddMode('new') }} className="flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-700">
                <Plus className="h-3 w-3" /> {t('contacts.add')}
              </button>
            )}
          </div>

          {(app?.contacts ?? []).length > 0 && (
            <div className="flex items-center gap-2">
              <input type="checkbox"
                checked={app!.contacts!.length > 0 && app!.contacts!.every(c => selectedContactIds.has(c.id))}
                ref={el => { if (el) el.indeterminate = selectedContactIds.size > 0 && !app!.contacts!.every(c => selectedContactIds.has(c.id)) }}
                onChange={() => {
                  setSelectedContactIds(prev => {
                    const allSelected = app!.contacts!.every(c => prev.has(c.id))
                    if (allSelected) return new Set()
                    return new Set(app!.contacts!.map(c => c.id))
                  })
                }}
                className="rounded border-gray-300 text-indigo-600 cursor-pointer"
              />
              <span className="text-xs text-gray-400">{t('contacts.selectAll')}</span>
              {selectedContactIds.size > 0 && (
                <button onClick={bulkDeleteSelectedContacts} disabled={bulkDeleting}
                  className="flex items-center gap-1 text-xs text-red-600 hover:text-red-700 disabled:opacity-50 ml-2">
                  <Trash2 className="h-3 w-3" /> {t('contacts.deleteContacts', { count: selectedContactIds.size })}
                </button>
              )}
            </div>
          )}

          {(app?.contacts ?? []).length > 0 && (
            <div className="space-y-2">
              {app!.contacts!.map(c => (
                <div key={c.id} className="rounded-lg border border-gray-100 bg-gray-50 px-3 py-2 text-sm">
                  {editingContactId === c.id ? (
                    <div className="space-y-2">
                      <div className="grid grid-cols-2 gap-2">
                        <input autoFocus
                          className="rounded-md border border-gray-200 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                          value={editContactDraft.vorname ?? ''} placeholder={t('contacts.firstNamePlaceholder')}
                          onChange={e => setEditContactDraft(d => ({ ...d, vorname: e.target.value }))}
                        />
                        <input
                          className="rounded-md border border-gray-200 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                          value={editContactDraft.name ?? ''} placeholder={t('contacts.lastNamePlaceholder')}
                          onChange={e => setEditContactDraft(d => ({ ...d, name: e.target.value }))}
                        />
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        <input className="rounded-md border border-gray-200 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" placeholder={t('contacts.emailPlaceholder')} value={editContactDraft.email ?? ''} onChange={e => setEditContactDraft(d => ({ ...d, email: e.target.value }))} />
                        <input className="rounded-md border border-gray-200 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" placeholder={t('contacts.phonePlaceholder')} value={editContactDraft.telefon ?? ''} onChange={e => setEditContactDraft(d => ({ ...d, telefon: e.target.value }))} />
                        <input className="rounded-md border border-gray-200 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" placeholder={t('contacts.rolePlaceholder')} value={editContactDraft.rolle ?? ''} onChange={e => setEditContactDraft(d => ({ ...d, rolle: e.target.value }))} />
                        <div className="relative" ref={ecFirmaRef}>
                          <div
                            className="flex items-center justify-between rounded-md border border-gray-200 px-2 py-1 text-sm cursor-pointer hover:border-indigo-300"
                            onClick={() => setEcFirmaPicker(o => !o)}
                          >
                            <span className={editContactDraft.firma ? 'text-gray-900 truncate' : 'text-gray-400'}>
                              {editContactDraft.firma || t('contacts.companyPlaceholder')}
                            </span>
                            <Building2 className="h-3.5 w-3.5 text-gray-400 shrink-0 ml-1" />
                          </div>
                          {ecFirmaPicker && (
                            <div className="absolute z-50 top-full left-0 mt-1 w-64 bg-white border border-gray-200 rounded-lg shadow-lg">
                              <div className="p-1.5 border-b border-gray-100">
                                <input autoFocus value={ecFirmaQuery} onChange={e => setEcFirmaQuery(e.target.value)}
                                  placeholder={t('contacts.companySearchPlaceholder')} className="w-full rounded border border-gray-200 px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500" />
                              </div>
                              <div className="max-h-40 overflow-y-auto py-1">
                                {ecFirmaLoading && <p className="text-xs text-gray-400 px-3 py-1.5">{t('contacts.searching')}</p>}
                                {!ecFirmaLoading && ecFirmaResults.length === 0 && !ecFirmaQuery && (
                                  <p className="text-xs text-gray-400 px-3 py-1.5 italic">{t('enterSearchTerm')}</p>
                                )}
                                {ecFirmaResults.slice(0, 8).map(c => (
                                  <button key={c.id} type="button" onClick={() => pickEditContactCompany(c)}
                                    className="w-full text-left px-3 py-1 text-xs hover:bg-indigo-50 hover:text-indigo-700 transition-colors">
                                    {c.name_display ?? c.name_norm}
                                  </button>
                                ))}
                                {ecFirmaQuery.trim() && (
                                  <button type="button" disabled={ecFirmaCreating} onClick={() => createAndPickEditContactCompany(ecFirmaQuery.trim())}
                                    className="w-full text-left px-3 py-1 text-xs text-indigo-600 hover:bg-indigo-50 flex items-center gap-1 border-t border-gray-100 mt-1">
                                    <Plus className="h-3 w-3 shrink-0" />
                                    {ecFirmaCreating ? t('creating') : t('createNew', { name: ecFirmaQuery.trim() })}
                                  </button>
                                )}
                              </div>
                            </div>
                          )}
                        </div>
                        <select className="col-span-2 rounded-md border border-gray-200 px-2 py-1 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500" value={editContactDraft.typ ?? ''} onChange={e => setEditContactDraft(d => ({ ...d, typ: e.target.value }))}>
                          <option value="">{t('contacts.typeSelectPlaceholder')}</option>
                          {CONTACT_TYPES.map(ct => <option key={ct} value={ct}>{ct}</option>)}
                        </select>
                      </div>
                      <input className="w-full rounded-md border border-gray-200 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" placeholder={t('contacts.linkedinUrlPlaceholder')} value={editContactDraft.linkedin_url ?? ''} onChange={e => setEditContactDraft(d => ({ ...d, linkedin_url: e.target.value }))} />
                      <div className="flex justify-end gap-2 pt-1">
                        <button type="button" onClick={() => setEditingContactId(null)} className="text-xs text-gray-500 hover:text-gray-700 px-2 py-1">{t('contacts.cancel')}</button>
                        <button type="button" disabled={!editContactDraft.name || !editContactDraft.email || savingContact} onClick={() => updateContact(c.id)} className="flex items-center gap-1 rounded-md bg-indigo-600 px-2 py-1 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50">
                          <Check className="h-3 w-3" /> {t('contacts.save')}
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-start gap-2">
                      <input type="checkbox" checked={selectedContactIds.has(c.id)} onChange={() => toggleContactSelect(c.id)}
                        className="mt-1 rounded border-gray-300 text-indigo-600 cursor-pointer shrink-0" />
                      <div
                        className={`flex-1 min-w-0 ${onOpenContact ? 'cursor-pointer' : ''}`}
                        onClick={() => onOpenContact?.(c.id)}
                      >
                        <p className="font-medium text-gray-900 truncate">{displayName(c)}</p>
                        <p className="text-xs text-gray-500 truncate">{[c.typ, c.rolle].filter(Boolean).join(' · ')}</p>
                        {c.firma && <p className="text-xs text-gray-400 truncate">{c.firma}</p>}
                        {c.email && <p className="text-xs text-gray-400 truncate">{c.email}</p>}
                        {(c.phones?.length ?? 0) > 0 && <p className="text-xs text-gray-400">{c.phones![0].number}</p>}
                        {c.linkedin_url && <a href={c.linkedin_url} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()} className="text-xs text-indigo-500 hover:underline truncate block">{t('contacts.linkedin')}</a>}
                      </div>
                      <div className="flex gap-1 shrink-0">
                        <button onClick={() => { setEditingContactId(c.id); setEditContactDraft({ vorname: c.vorname, name: c.name, email: c.email, telefon: c.phones?.[0]?.number ?? '', rolle: c.rolle, firma: c.firma, typ: c.typ, linkedin_url: c.linkedin_url }) }}
                          className="p-1 rounded hover:bg-gray-200 text-gray-400 hover:text-gray-600" title={t('contacts.edit')}><Pencil className="h-3.5 w-3.5" /></button>
                        <button onClick={() => deleteContact(c.id, displayName(c))}
                          className="p-1 rounded hover:bg-red-50 text-gray-400 hover:text-red-500" title={t('contacts.delete')}><Trash2 className="h-3.5 w-3.5" /></button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {(app?.contacts ?? []).length === 0 && !addingContact && (
            <p className="text-sm text-gray-400 italic">{t('contacts.none')}</p>
          )}

          {addingContact && (
            <div className="rounded-lg border border-indigo-200 bg-indigo-50 p-3 space-y-2">
              {/* Mode toggle */}
              <div className="flex rounded-md overflow-hidden border border-indigo-200 text-xs font-medium">
                <button type="button"
                  onClick={() => { setAddMode('new'); setLinkSearch(''); setLinkResults([]) }}
                  className={`flex-1 px-2 py-1.5 ${addMode === 'new' ? 'bg-indigo-600 text-white' : 'bg-white text-gray-600 hover:bg-indigo-50'}`}>
                  {t('contacts.createNewMode')}
                </button>
                <button type="button"
                  onClick={() => { setAddMode('link'); setContactDraft(EMPTY_CONTACT) }}
                  className={`flex-1 px-2 py-1.5 ${addMode === 'link' ? 'bg-indigo-600 text-white' : 'bg-white text-gray-600 hover:bg-indigo-50'}`}>
                  {t('contacts.linkExistingMode')}
                </button>
              </div>

              {addMode === 'new' ? (
                <>
                  <div className="grid grid-cols-2 gap-2">
                    <input autoFocus
                      className="rounded-md border border-gray-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      placeholder={t('contacts.firstNamePlaceholder')} value={contactDraft.vorname ?? ''}
                      onChange={e => setContactDraft(d => ({ ...d, vorname: e.target.value }))}
                    />
                    <input
                      className="rounded-md border border-gray-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      placeholder={t('contacts.lastNamePlaceholder')} value={contactDraft.name ?? ''}
                      onChange={e => setContactDraft(d => ({ ...d, name: e.target.value }))}
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <input className="rounded-md border border-gray-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" placeholder={t('contacts.emailPlaceholder')} value={contactDraft.email ?? ''} onChange={e => setContactDraft(d => ({ ...d, email: e.target.value }))} />
                    <input className="rounded-md border border-gray-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" placeholder={t('contacts.phonePlaceholder')} value={contactDraft.telefon ?? ''} onChange={e => setContactDraft(d => ({ ...d, telefon: e.target.value }))} />
                    <input className="rounded-md border border-gray-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" placeholder={t('contacts.rolePlaceholder')} value={contactDraft.rolle ?? ''} onChange={e => setContactDraft(d => ({ ...d, rolle: e.target.value }))} />
                    <div className="relative" ref={cFirmaRef}>
                      <div
                        className="flex items-center justify-between rounded-md border border-gray-200 px-2 py-1.5 text-sm cursor-pointer hover:border-indigo-300"
                        onClick={() => setCFirmaPicker(o => !o)}
                      >
                        <span className={contactDraft.firma ? 'text-gray-900 truncate' : 'text-gray-400'}>
                          {contactDraft.firma || t('contacts.companyPlaceholder')}
                        </span>
                        <Building2 className="h-3.5 w-3.5 text-gray-400 shrink-0 ml-1" />
                      </div>
                      {cFirmaPicker && (
                        <div className="absolute z-50 top-full left-0 mt-1 w-64 bg-white border border-gray-200 rounded-lg shadow-lg">
                          <div className="p-1.5 border-b border-gray-100">
                            <input autoFocus value={cFirmaQuery} onChange={e => setCFirmaQuery(e.target.value)}
                              placeholder={t('contacts.companySearchPlaceholder')} className="w-full rounded border border-gray-200 px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500" />
                          </div>
                          <div className="max-h-40 overflow-y-auto py-1">
                            {cFirmaLoading && <p className="text-xs text-gray-400 px-3 py-1.5">{t('contacts.searching')}</p>}
                            {!cFirmaLoading && cFirmaResults.length === 0 && !cFirmaQuery && (
                              <p className="text-xs text-gray-400 px-3 py-1.5 italic">{t('enterSearchTerm')}</p>
                            )}
                            {cFirmaResults.slice(0, 8).map(c => (
                              <button key={c.id} type="button" onClick={() => pickContactCompany(c)}
                                className="w-full text-left px-3 py-1 text-xs hover:bg-indigo-50 hover:text-indigo-700 transition-colors">
                                {c.name_display ?? c.name_norm}
                              </button>
                            ))}
                            {cFirmaQuery.trim() && (
                              <button type="button" disabled={cFirmaCreating} onClick={() => createAndPickContactCompany(cFirmaQuery.trim())}
                                className="w-full text-left px-3 py-1 text-xs text-indigo-600 hover:bg-indigo-50 flex items-center gap-1 border-t border-gray-100 mt-1">
                                <Plus className="h-3 w-3 shrink-0" />
                                {cFirmaCreating ? t('creating') : t('createNew', { name: cFirmaQuery.trim() })}
                              </button>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                    <select className="col-span-2 rounded-md border border-gray-200 px-2 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500" value={contactDraft.typ ?? ''} onChange={e => setContactDraft(d => ({ ...d, typ: e.target.value }))}>
                      <option value="">{t('contacts.typeSelectPlaceholder')}</option>
                      {CONTACT_TYPES.map(ct => <option key={ct} value={ct}>{ct}</option>)}
                    </select>
                  </div>
                  <div className="flex justify-end gap-2 pt-1">
                    <button type="button" onClick={() => { setAddingContact(false); setContactDraft(EMPTY_CONTACT) }} className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700">
                      <Trash2 className="h-3 w-3" /> {t('contacts.cancel')}
                    </button>
                    <button type="button" disabled={!contactDraft.name || !contactDraft.email || savingContact} onClick={saveContact}
                      className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50">
                      {savingContact ? t('contacts.saving') : t('contacts.save')}
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <div className="relative">
                    <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-gray-400" />
                    <input autoFocus
                      className="w-full rounded-md border border-gray-200 pl-7 pr-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      placeholder={t('contacts.linkSearchPlaceholder')}
                      value={linkSearch}
                      onChange={e => setLinkSearch(e.target.value)}
                    />
                  </div>
                  {linkLoading && <p className="text-xs text-gray-400 text-center py-1">{t('contacts.searching')}</p>}
                  {!linkLoading && linkSearch.trim() && linkResults.length === 0 && (
                    <p className="text-xs text-gray-400 italic text-center py-1">{t('contacts.noneFound')}</p>
                  )}
                  {linkResults.length > 0 && (
                    <div className="space-y-1 max-h-48 overflow-y-auto">
                      {linkResults.map(c => (
                        <button key={c.id} type="button" disabled={savingContact}
                          onClick={() => linkContact(c.id)}
                          className="w-full text-left rounded-md border border-gray-200 bg-white px-3 py-2 hover:border-indigo-400 hover:bg-indigo-50 disabled:opacity-50 transition-colors">
                          <p className="text-sm font-medium text-gray-900">{displayName(c)}</p>
                          <p className="text-xs text-gray-500">{[c.typ, c.rolle, c.firma].filter(Boolean).join(' · ')}</p>
                          {c.email && <p className="text-xs text-gray-400">{c.email}</p>}
                        </button>
                      ))}
                    </div>
                  )}
                  <div className="flex justify-end pt-1">
                    <button type="button" onClick={() => { setAddingContact(false); setLinkSearch(''); setLinkResults([]) }} className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700">
                      <Trash2 className="h-3 w-3" /> {t('contacts.cancel')}
                    </button>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
        )}

        {/* Tab: Gehalt */}
        {activeTab === 'salary' && (
        <div className="overflow-y-auto flex-1 p-6 space-y-5">
          {editing ? (
            <>
              <div>
                <label className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5 block">{t('salary.currency')}</label>
                <select
                  className="rounded-lg border border-gray-200 px-3 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  value={draft.salary_currency || 'EUR'}
                  onChange={e => setDraft(d => ({ ...d, salary_currency: e.target.value }))}
                >
                  {CURRENCIES.map(c => <option key={c.code} value={c.code}>{c.code} ({c.symbol})</option>)}
                </select>
              </div>

              {([
                ['salary_expectation_min', 'salary_expectation_max',
                 'salary_expectation_min_fixed', 'salary_expectation_min_bonus',
                 'salary_expectation_max_fixed', 'salary_expectation_max_bonus',
                 t('salary.expectation'), 'salary_expectation_company_car', t('salary.companyCarExpectation')],
                ['salary_budget_min', 'salary_budget_max',
                 'salary_budget_min_fixed', 'salary_budget_min_bonus',
                 'salary_budget_max_fixed', 'salary_budget_max_bonus',
                 t('salary.budget'), 'salary_budget_company_car', t('salary.companyCarBudget')],
              ] as const).map(([minKey, maxKey, minFixedKey, minBonusKey, maxFixedKey, maxBonusKey, label, carKey, carLabel]) => {
                const minVal = draft[minKey]
                const maxVal = draft[maxKey]
                const hasRange = maxVal != null

                const renderAmountInput = (
                  key: typeof minKey | typeof maxKey,
                  fixedKey: typeof minFixedKey | typeof maxFixedKey,
                  bonusKey: typeof minBonusKey | typeof maxBonusKey,
                  placeholder: string,
                  clearAlso?: Partial<Application>,
                ) => {
                  const fixedVal = draft[fixedKey]
                  const bonusVal = draft[bonusKey]
                  const hasBreakdown = fixedVal != null || bonusVal != null
                  return (
                    <div className="flex items-center gap-2 flex-wrap">
                      <input type="number" min={0} readOnly={hasBreakdown}
                        className={`w-28 rounded-lg border px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 ${hasBreakdown ? 'bg-gray-50 text-gray-500 border-gray-200' : 'border-gray-200'}`}
                        placeholder={placeholder}
                        value={draft[key] ?? ''}
                        onChange={hasBreakdown ? undefined : e => {
                          const val = e.target.value === '' ? null : Number(e.target.value)
                          setDraft(d => ({ ...d, [key]: val, ...(val === null && clearAlso ? clearAlso : {}) }))
                        }}
                      />
                      {hasBreakdown ? (
                        <>
                          <span className="text-xs text-gray-400">=</span>
                          <input type="number" min={0}
                            className="w-24 rounded-lg border border-gray-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                            placeholder={t('salary.fixed')}
                            value={fixedVal ?? ''}
                            onChange={e => {
                              const val = e.target.value === '' ? null : Number(e.target.value)
                              setDraft(d => ({ ...d, [fixedKey]: val, [key]: (val ?? 0) + (d[bonusKey] ?? 0) }))
                            }}
                          />
                          <span className="text-xs text-gray-400">+</span>
                          <input type="number" min={0}
                            className="w-24 rounded-lg border border-gray-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                            placeholder={t('salary.bonus')}
                            value={bonusVal ?? ''}
                            onChange={e => {
                              const val = e.target.value === '' ? null : Number(e.target.value)
                              setDraft(d => ({ ...d, [bonusKey]: val, [key]: (d[fixedKey] ?? 0) + (val ?? 0) }))
                            }}
                          />
                          <button type="button" className="text-xs text-gray-400 hover:text-gray-600 underline whitespace-nowrap"
                            onClick={() => setDraft(d => ({ ...d, [fixedKey]: null, [bonusKey]: null }))}>
                            {t('salary.breakdownToggleOff')}
                          </button>
                        </>
                      ) : (
                        <button type="button" className="text-xs text-indigo-500 hover:text-indigo-700 whitespace-nowrap"
                          disabled={draft[key] == null}
                          onClick={() => setDraft(d => ({ ...d, [fixedKey]: d[key] ?? 0, [bonusKey]: 0 }))}>
                          {t('salary.breakdownToggleOn')}
                        </button>
                      )}
                    </div>
                  )
                }

                return (
                  <div key={minKey} className="space-y-2">
                    <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">{label}</p>
                    <div className="flex items-center gap-3 flex-wrap">
                      {renderAmountInput(minKey, minFixedKey, minBonusKey, t('salary.amountPlaceholder'))}
                      <label className="flex items-center gap-1.5 text-xs text-gray-500 cursor-pointer">
                        <input type="checkbox" checked={hasRange}
                          className="rounded border-gray-300 text-indigo-600"
                          disabled={minVal == null}
                          onChange={e => setDraft(d => ({
                            ...d,
                            [maxKey]: e.target.checked ? (minVal ?? 0) : null,
                            ...(e.target.checked ? {} : { [maxFixedKey]: null, [maxBonusKey]: null }),
                          }))}
                        />
                        {t('salary.rangeToggle')}
                      </label>
                    </div>
                    {hasRange && renderAmountInput(maxKey, maxFixedKey, maxBonusKey, t('salary.amountMaxPlaceholder'))}
                    <label className="flex items-center gap-1.5 text-xs text-gray-500 cursor-pointer pt-1">
                      <input type="checkbox" checked={!!draft[carKey]}
                        className="rounded border-gray-300 text-indigo-600"
                        onChange={e => setDraft(d => ({ ...d, [carKey]: e.target.checked }))}
                      />
                      <Car className="h-3.5 w-3.5 text-gray-400" />
                      {carLabel}
                    </label>
                  </div>
                )
              })}
            </>
          ) : (
            <>
              {app?.salary_mismatch && (
                <div className="flex items-center gap-2 rounded-lg bg-red-50 ring-1 ring-inset ring-red-200 px-3 py-2 text-sm text-red-700">
                  <AlertTriangle className="h-4 w-4 shrink-0" />
                  {t('salary.mismatchWarning')}
                </div>
              )}
              {([
                ['salary_expectation_min', 'salary_expectation_max',
                 'salary_expectation_min_fixed', 'salary_expectation_min_bonus',
                 'salary_expectation_max_fixed', 'salary_expectation_max_bonus',
                 t('salary.expectation'), 'salary_expectation_company_car', t('salary.companyCarExpectation')],
                ['salary_budget_min', 'salary_budget_max',
                 'salary_budget_min_fixed', 'salary_budget_min_bonus',
                 'salary_budget_max_fixed', 'salary_budget_max_bonus',
                 t('salary.budget'), 'salary_budget_company_car', t('salary.companyCarBudget')],
              ] as const).map(([minKey, maxKey, minFixedKey, minBonusKey, maxFixedKey, maxBonusKey, label, carKey, carLabel]) => {
                const isRange = app?.[maxKey] != null
                return (
                  <div key={minKey}>
                    <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1 flex items-center gap-1.5">
                      {label}
                      {app?.[carKey] && (
                        <span title={carLabel}><Car className="h-3.5 w-3.5 text-gray-400" /></span>
                      )}
                    </p>
                    <p className={`text-sm ${app?.salary_mismatch ? 'text-red-600 font-medium' : 'text-gray-900'}`}>
                      {formatSalaryRange(app?.[minKey], app?.[maxKey], app?.salary_currency, locale)
                        ?? <span className="text-gray-400 italic font-normal">{t('salary.notSet')}</span>}
                    </p>
                    {app?.[minFixedKey] != null && app?.[minBonusKey] != null && (
                      <p className="text-xs text-gray-400 mt-0.5">
                        {isRange && `${t('salary.breakdownLabelMin')}: `}
                        {formatCurrencyAmount(app[minFixedKey]!, app?.salary_currency, locale)} {t('salary.fixed').toLowerCase()} + {formatCurrencyAmount(app[minBonusKey]!, app?.salary_currency, locale)} {t('salary.bonus').toLowerCase()}
                      </p>
                    )}
                    {app?.[maxFixedKey] != null && app?.[maxBonusKey] != null && (
                      <p className="text-xs text-gray-400 mt-0.5">
                        {t('salary.breakdownLabelMax')}: {formatCurrencyAmount(app[maxFixedKey]!, app?.salary_currency, locale)} {t('salary.fixed').toLowerCase()} + {formatCurrencyAmount(app[maxBonusKey]!, app?.salary_currency, locale)} {t('salary.bonus').toLowerCase()}
                      </p>
                    )}
                  </div>
                )
              })}
            </>
          )}
        </div>
        )}

        {/* Footer */}
        <div className="flex items-center justify-between p-6 border-t border-gray-100 bg-gray-50 rounded-b-2xl">
          <button
            onClick={deleteApp}
            data-testid="delete-application-button"
            className="text-sm text-red-600 hover:text-red-700 hover:underline"
          >
            {t('footer.delete')}
          </button>
          <div className="flex gap-3">
            {editing ? (
              <>
                <button onClick={() => { setEditing(false); setDraft(app ?? {}) }} data-testid="cancel-edit-button" className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100">
                  {t('footer.cancel')}
                </button>
                <button onClick={save} disabled={saving} data-testid="save-application-button" className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60">
                  {saving ? t('footer.saving') : t('footer.save')}
                </button>
              </>
            ) : (
              <button onClick={() => setEditing(true)} data-testid="edit-application-button" className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700">
                {t('footer.edit')}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>

    {/* Manual assign dialog */}
    {manualOpen && (
      <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4" onClick={e => { if (e.target === e.currentTarget) { setManualOpen(false); setManualConflict(null) } }}>
        <div className="w-full max-w-lg rounded-2xl bg-white shadow-2xl flex flex-col max-h-[80vh]">
          <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
            <h3 className="font-semibold text-gray-900 text-sm">{t('manualAssign.title')}</h3>
            <button onClick={() => { setManualOpen(false); setManualConflict(null) }} className="p-1 rounded hover:bg-gray-100 text-gray-400">
              <X className="h-4 w-4" />
            </button>
          </div>
          {manualConflict ? (
            <div className="p-5 space-y-4">
              <p className="text-sm text-gray-700">
                {t('manualAssign.conflictPrefix')} <strong>{manualConflict.conflict_app_firma}</strong>{t('manualAssign.conflictSuffix')}
              </p>
              <div className="flex gap-2 justify-end">
                <button onClick={() => setManualConflict(null)} className="text-xs text-gray-500 hover:text-gray-700 px-3 py-2">{t('manualAssign.cancel')}</button>
                <button onClick={() => assignCandidate(manualConflict.candidate, false)} className="rounded-md border border-gray-200 px-3 py-2 text-xs hover:bg-gray-50">{t('manualAssign.linkBoth')}</button>
                <button onClick={() => assignCandidate(manualConflict.candidate, true)} className="rounded-md bg-indigo-600 px-3 py-2 text-xs text-white hover:bg-indigo-700">{t('manualAssign.removeFromOther')}</button>
              </div>
            </div>
          ) : (
            <>
              <div className="px-5 py-3 border-b border-gray-100 flex gap-2">
                <input
                  className="flex-1 rounded-lg border border-gray-200 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder={t('manualAssign.searchPlaceholder')}
                  value={manualQuery}
                  onChange={e => setManualQuery(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && searchManual()}
                />
                <button onClick={searchManual} disabled={manualLoading} className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm text-white hover:bg-indigo-700 disabled:opacity-50">
                  <Search className="h-4 w-4" />
                </button>
              </div>
              {manualSelected.size > 0 && (
                <div className="px-5 py-2 border-b border-gray-100 flex items-center justify-between bg-indigo-50/50">
                  <span className="text-xs text-gray-600">{t('manualAssign.selected', { count: manualSelected.size })}</span>
                  <div className="flex items-center gap-2">
                    <button onClick={() => setManualSelected(new Set())} className="text-xs text-gray-500 hover:text-gray-700 px-2 py-1">
                      {t('manualAssign.deselect')}
                    </button>
                    <button
                      onClick={assignSelectedCandidates}
                      disabled={manualBulkBusy}
                      data-testid="manual-assign-import-button"
                      className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs text-white hover:bg-indigo-700 disabled:opacity-50"
                    >
                      {manualBulkBusy ? t('manualAssign.importing') : t('manualAssign.import', { count: manualSelected.size })}
                    </button>
                  </div>
                </div>
              )}
              {manualBulkErrors.length > 0 && (
                <div className="px-5 py-2 border-b border-gray-100 bg-amber-50 text-xs text-amber-700 space-y-0.5">
                  {manualBulkErrors.map((msg, i) => <p key={i}>{msg}</p>)}
                </div>
              )}
              <div className="overflow-y-auto flex-1 p-3 space-y-3">
                {manualLoading && <p className="text-sm text-gray-400 text-center py-4">{t('manualAssign.loading')}</p>}
                {!manualLoading && manualCandidates.length === 0 && (
                  <p className="text-sm text-gray-400 italic text-center py-4">{t('manualAssign.noMatches')}</p>
                )}
                {!manualLoading && (() => {
                  const SOURCE_ORDER = ['gmail','gcal','icloud_mail','icloud_cal','icloud_notes','pending','event']
                  const grouped: Record<string, typeof manualCandidates> = {}
                  manualCandidates.forEach(c => {
                    const key = c.source || 'event'
                    ;(grouped[key] ??= []).push(c)
                  })
                  const keys = [
                    ...SOURCE_ORDER.filter(k => grouped[k]),
                    ...Object.keys(grouped).filter(k => !SOURCE_ORDER.includes(k)),
                  ]
                  return keys.map(src => {
                    const items = grouped[src]
                    const meta = SOURCE_META[src]
                    const label = t(`sourceLabel.${src}`, { defaultValue: src })
                    const cls   = meta?.cls   ?? 'bg-gray-50 text-gray-600 border-gray-200'
                    return (
                      <details key={src} open className="text-xs">
                        <summary className="flex items-center gap-1.5 cursor-pointer select-none list-none mb-1.5">
                          <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium ${cls}`}>
                            {meta?.icon}{label}
                          </span>
                          <span className="text-gray-400">({items.length})</span>
                        </summary>
                        <div className="space-y-1.5 pl-1">
                          {items.map(c => (
                            <div
                              key={candidateKey(c)}
                              className="w-full flex items-start gap-2 rounded-lg border border-gray-200 hover:border-indigo-300 hover:bg-indigo-50 p-3 transition-colors"
                            >
                              <input
                                type="checkbox"
                                checked={manualSelected.has(candidateKey(c))}
                                onChange={() => toggleManualSelected(c)}
                                onClick={e => e.stopPropagation()}
                                className="mt-0.5 flex-shrink-0"
                              />
                              <button
                                onClick={() => assignCandidate(c)}
                                className="flex-1 min-w-0 text-left"
                              >
                                <p className="text-sm font-medium text-gray-800 truncate">{c.titel || c.event_type || c.source}</p>
                                {c.datum && <p className="text-xs text-gray-500">{formatDate(c.datum, locale)}</p>}
                                {c.extract && <p className="text-xs text-gray-400 truncate mt-0.5">{c.extract}</p>}
                                {c.suggested_app_firma && <p className="text-xs text-amber-600 mt-0.5">{t('manualAssign.suggestion', { firma: c.suggested_app_firma })}</p>}
                              </button>
                            </div>
                          ))}
                        </div>
                      </details>
                    )
                  })
                })()}
              </div>
            </>
          )}
        </div>
      </div>
    )}

    {/* Document browser dialog */}
    {docBrowseOpen && (() => {
      const pathParts = docBrowsePath.split('/').filter(Boolean)
      const isAtRoot = docBrowsePath === docBrowseRoot || docBrowsePath === '/'
      return (
      <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4" onClick={e => { if (e.target === e.currentTarget) setDocBrowseOpen(false) }}>
        <div className="w-full max-w-lg rounded-2xl bg-white shadow-2xl flex flex-col max-h-[80vh]">
          <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
            <h3 className="font-semibold text-gray-900 text-sm">{t('docBrowser.title')}</h3>
            <button onClick={() => setDocBrowseOpen(false)} className="p-1 rounded hover:bg-gray-100 text-gray-400">
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Path bar */}
          <div className="px-3 py-2 border-b border-gray-100 flex items-center gap-1 min-w-0 overflow-x-auto">
            {!isAtRoot && (
              <button
                onClick={() => browseInto(parentPath(docBrowsePath))}
                className="flex-shrink-0 p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-700"
                title={t('docBrowser.up')}
              >
                <ChevronRight className="h-3.5 w-3.5 rotate-180" />
              </button>
            )}
            <div className="flex items-center gap-0.5 text-xs text-gray-500 min-w-0 overflow-x-auto">
              {pathParts.map((part, i) => (
                <span key={i} className="flex items-center gap-0.5 flex-shrink-0">
                  {i > 0 && <ChevronRight className="h-3 w-3 text-gray-300" />}
                  <button
                    onClick={() => browseInto('/' + pathParts.slice(0, i + 1).join('/'))}
                    className={`hover:text-indigo-600 truncate max-w-[120px] ${i === pathParts.length - 1 ? 'text-gray-800 font-medium' : ''}`}
                  >
                    {part}
                  </button>
                </span>
              ))}
            </div>
            {docBrowseRoot && docBrowsePath !== docBrowseRoot && (
              <button
                onClick={() => browseInto(docBrowseRoot)}
                className="flex-shrink-0 ml-auto text-[10px] text-indigo-500 hover:text-indigo-700 whitespace-nowrap pl-2"
              >
                {t('docBrowser.home')}
              </button>
            )}
          </div>

          <div className="overflow-y-auto flex-1 p-3 space-y-1">
            {docBrowseLoading && <p className="text-sm text-gray-400 text-center py-6">{t('docBrowser.loading')}</p>}
            {docBrowseError && <p className="text-sm text-red-500 text-center py-4">{docBrowseError}</p>}
            {!docBrowseLoading && !docBrowseError && docBrowseItems.length === 0 && (
              <p className="text-sm text-gray-400 italic text-center py-6">{t('docBrowser.noFiles')}</p>
            )}
            {!docBrowseLoading && docBrowseItems.map(item => (
              <div key={item.path} className="flex items-center gap-2 group">
                <button
                  disabled={docAttaching !== null}
                  onClick={() => item.type === 'folder' ? browseInto(item.path) : attachDoc(item)}
                  className="flex-1 min-w-0 text-left flex items-center gap-3 rounded-lg border border-gray-200 hover:border-indigo-300 hover:bg-indigo-50 px-3 py-2.5 transition-colors disabled:opacity-50"
                >
                  {item.type === 'folder' ? (
                    <Folder className="h-4 w-4 text-amber-400 flex-shrink-0" />
                  ) : (
                    <FileText className="h-4 w-4 text-indigo-400 flex-shrink-0" />
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-gray-800 truncate">{item.name}</p>
                    {item.type === 'file' && item.modified > 0 && (
                      <p className="text-[10px] text-gray-400">
                        {formatDate(new Date(item.modified * 1000), locale)}
                      </p>
                    )}
                  </div>
                  {item.type === 'folder' && <ChevronRight className="h-4 w-4 text-gray-300 flex-shrink-0" />}
                  {item.type === 'file' && docAttaching === item.path && (
                    <span className="text-[10px] text-indigo-500 flex-shrink-0">{t('docBrowser.attaching')}</span>
                  )}
                </button>
                {/* "Hinzufügen"-Button für Ordner */}
                {item.type === 'folder' && (
                  <button
                    disabled={docAttaching !== null}
                    onClick={() => attachDoc(item)}
                    title={t('docBrowser.addFolder')}
                    className="flex-shrink-0 p-2 rounded-lg border border-gray-200 hover:border-indigo-400 hover:bg-indigo-50 text-gray-400 hover:text-indigo-600 transition-colors disabled:opacity-50"
                  >
                    <Plus className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
      )
    })()}
    </>
  )
}

const OTHER_EVENT_TYPES = [
  { value: 'status',   label: 'Status' },
  { value: 'gespräch', label: 'Gespräch' },
  { value: 'mail',     label: 'Mail' },
  { value: 'anruf',    label: 'Anruf' },
  { value: 'angebot',  label: 'Angebot' },
  { value: 'absage',   label: 'Absage' },
]

function timelineSortKey(ev: Event): string {
  // Prefer the full timestamp (datum_zeit) when the sync source had one;
  // pad a bare date to midnight so it compares consistently against a
  // full-precision key on another event the same day (an event with a
  // known time later that day correctly sorts as newer).
  if (ev.datum_zeit) return ev.datum_zeit
  if (ev.datum) return `${ev.datum}T00:00:00`
  return ''
}

export function compareTimelineEventsNewestFirst(a: Event, b: Event): number {
  const ka = timelineSortKey(a)
  const kb = timelineSortKey(b)
  if (ka !== kb) return kb.localeCompare(ka)
  return b.id - a.id
}

// Event.datum_zeit is a naive datetime representing UTC (see _to_naive_utc()
// in sync_common.py) -- appending "Z" forces the browser to parse it as UTC
// rather than (per the ECMA-402 default for a timezone-less ISO string) the
// browser's own local time. Formatted into the app's single hardcoded
// reference zone (Europe/Berlin, matching _TZ_BERLIN backend-side) for the
// edit form's <input type="time"> value.
export function datumZeitToBerlinTimeInput(datumZeit: string | undefined | null): string {
  if (!datumZeit) return ''
  const utcDate = new Date(`${datumZeit}Z`)
  if (isNaN(utcDate.getTime())) return ''
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Europe/Berlin', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(utcDate)
}

// datum_zeit_is_placeholder marks a v4.6.7 noon-backfill placeholder rather
// than a genuine timestamp (see database.py's _flag_noon_backfill_placeholders())
// -- surfacing it as a real time (e.g. "14:00" for every old entry) would be
// worse than showing nothing, so treat it the same as "no time known" here.
export function displayableDatumZeit(event: Event): string | undefined {
  return event.datum_zeit_is_placeholder ? undefined : event.datum_zeit
}

function getEventIcon(event: Event): { icon: React.ReactNode; bg: string; fg: string } {
  const sz = 'h-[9px] w-[9px]'
  const src = event.source
  if (src === 'icloud_calls' || src === 'call') return { icon: <Phone className={sz} />, bg: 'bg-green-100', fg: 'text-green-700' }
  if (src === 'gmail') return { icon: <Mail className={sz} />, bg: 'bg-red-100', fg: 'text-red-600' }
  if (src === 'icloud_mail') return { icon: <Mail className={sz} />, bg: 'bg-sky-100', fg: 'text-sky-600' }
  if (src === 'linkedin_msg') return { icon: <Linkedin className={sz} />, bg: 'bg-blue-100', fg: 'text-blue-700' }
  if (src === 'gcal') return { icon: <Calendar className={sz} />, bg: 'bg-blue-100', fg: 'text-blue-600' }
  if (src === 'icloud_cal') return { icon: <Calendar className={sz} />, bg: 'bg-sky-100', fg: 'text-sky-700' }
  if (src === 'icloud_notes' || src === 'notes') return { icon: <FileText className={sz} />, bg: 'bg-amber-100', fg: 'text-amber-700' }
  if (src === 'icloud_todo') return { icon: <FileText className={sz} />, bg: 'bg-orange-100', fg: 'text-orange-700' }
  const typ = event.typ
  if (typ === 'bewerbung') return { icon: <Send className={sz} />, bg: 'bg-green-100', fg: 'text-green-700' }
  if (typ === 'status') return { icon: <TrendingUp className={sz} />, bg: 'bg-indigo-100', fg: 'text-indigo-600' }
  if (typ === 'gespräch') return { icon: <MessageCircle className={sz} />, bg: 'bg-purple-100', fg: 'text-purple-600' }
  return { icon: <PenLine className={sz} />, bg: 'bg-gray-100', fg: 'text-gray-500' }
}

const SOURCE_META: Record<string, { icon: React.ReactNode; label: string; cls: string }> = {
  gmail:        { icon: <Mail className="h-3 w-3" />,     label: 'Gmail',          cls: 'bg-red-50 text-red-600 border-red-100' },
  gcal:         { icon: <Calendar className="h-3 w-3" />, label: 'Google Kalender',cls: 'bg-blue-50 text-blue-600 border-blue-100' },
  icloud_mail:  { icon: <Mail className="h-3 w-3" />,     label: 'iCloud Mail',    cls: 'bg-sky-50 text-sky-600 border-sky-100' },
  icloud_cal:   { icon: <Calendar className="h-3 w-3" />, label: 'iCloud Kalender',cls: 'bg-sky-50 text-sky-700 border-sky-100' },
  icloud_notes: { icon: <FileText className="h-3 w-3" />, label: 'iCloud Notizen', cls: 'bg-yellow-50 text-yellow-700 border-yellow-100' },
  icloud_todo:  { icon: <FileText className="h-3 w-3" />, label: 'Erinnerungen',   cls: 'bg-orange-50 text-orange-700 border-orange-100' },
  notes:        { icon: <FileText className="h-3 w-3" />, label: 'Notizen',        cls: 'bg-yellow-50 text-yellow-700 border-yellow-100' },
  call:         { icon: <Phone className="h-3 w-3" />,    label: 'Anruf',          cls: 'bg-green-50 text-green-700 border-green-100' },
  linkedin_msg: { icon: <Linkedin className="h-3 w-3" />, label: 'LinkedIn',       cls: 'bg-blue-50 text-blue-700 border-blue-100' },
}

export function buildDeepLink(source: string | undefined, external_id: string | undefined, external_url: string | undefined): string | null {
  if (!source || !external_id) return null
  // Strip status-suffix used for PendingMatch keys (e.g. "abc__status")
  const rawId = external_id.replace(/__status$/, '')
  switch (source) {
    case 'gmail':
      return `https://mail.google.com/mail/u/0/#all/${rawId}`
    case 'gcal':
      // Google Calendar's "eventedit" deep link needs the calendar ID baked
      // into the same base64 blob as the event ID -- the frontend has no
      // access to that, so external_url (the API's own ready-made link,
      // captured at sync time) is required here; no reconstructed fallback.
      return external_url || null
    case 'icloud_mail':
      return `message://${rawId}`
    case 'icloud_cal':
      return `x-apple-calevent:///${rawId}`
    case 'icloud_notes':
      return `applenotes://${rawId}`
    case 'linkedin_msg':
      // external_url is the participant's own LinkedIn profile (captured
      // from the export CSV's SENDER/RECIPIENT PROFILE URL column at
      // import time) -- there's no reliable way to reconstruct a link to
      // the exact conversation thread from just the CSV's conversation ID.
      return external_url || null
    default:
      return null
  }
}

export function SourceBadge({ source, external_id, external_url }: { source?: string; external_id?: string; external_url?: string }) {
  const { t } = useTranslation('applications')
  if (!source) return null
  const meta = SOURCE_META[source]
  const deepLink = buildDeepLink(source, external_id, external_url)
  const cls = meta
    ? `inline-flex items-center gap-0.5 rounded-full border px-1.5 py-0.5 text-[10px] font-medium ${meta.cls}`
    : 'inline-flex items-center rounded-full border px-1.5 py-0.5 text-[10px] font-medium bg-gray-50 text-gray-500 border-gray-200'
  const label = t(`sourceLabel.${source}`, { defaultValue: source })
  if (deepLink) {
    return (
      <a href={deepLink} target="_blank" rel="noreferrer" className={`${cls} hover:opacity-80 cursor-pointer`} title={t('timeline.openInApp')}>
        {label} <ExternalLink className="h-2.5 w-2.5 opacity-60" />
      </a>
    )
  }
  return <span className={cls}>{label}</span>
}

const EVENT_TYPES = ['bewerbung', 'status', 'notiz', 'gespräch', 'mail', 'anruf', 'angebot', 'absage'] as const

function FileRow({ event, appId, onDeleted }: { event: Event; appId: number; onDeleted: () => void }) {
  const { t } = useTranslation('applications')
  const [opening, setOpening] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const path = event.notiz ?? ''
  const ext = path.split('.').pop()?.toLowerCase() ?? ''

  async function openFile() {
    if (!path) return
    setOpening(true)
    try { await api.files.openFile(path) } catch { /* bridge may be off */ }
    finally { setOpening(false) }
  }

  async function deleteFile() {
    setDeleting(true)
    try {
      await api.applications.deleteEvent(appId, event.id)
      onDeleted()
    } finally { setDeleting(false) }
  }

  return (
    <div className="flex items-center gap-2 rounded-lg border border-gray-100 bg-gray-50 px-3 py-2 group hover:border-gray-200">
      <FileText className="h-4 w-4 text-gray-400 shrink-0" />
      <button
        onClick={openFile}
        disabled={opening || !path}
        className="flex-1 min-w-0 text-left text-sm text-gray-800 hover:text-indigo-600 truncate disabled:opacity-50"
        title={path}
      >
        {event.titel ?? path.split('/').pop()}
      </button>
      {ext && <span className="text-[10px] uppercase font-medium text-gray-400 shrink-0">{ext}</span>}
      <button
        onClick={deleteFile}
        disabled={deleting}
        className="p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-red-50 text-gray-400 hover:text-red-500 shrink-0 transition-opacity"
        title={t('timeline.removeTitle')}
      >
        <Trash2 className="h-3.5 w-3.5" />
      </button>
    </div>
  )
}

function TimelineEvent({ event, appId, onUpdated }: { event: Event; appId: number; onUpdated: () => void }) {
  const { t } = useTranslation('applications')
  const locale = useLocale()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState({
    typ: event.typ, datum: event.datum ?? '', zeit: datumZeitToBerlinTimeInput(displayableDatumZeit(event)),
    titel: event.titel ?? '', notiz: event.notiz ?? '',
  })
  const [saving, setSaving] = useState(false)

  const styleLabel = t(`eventType.${event.typ}`, { defaultValue: event.typ })
  const dateStr = event.datum
    ? formatDate(event.datum, locale, { day: '2-digit', month: '2-digit', year: 'numeric' })
    : null
  // Prefer datum_zeit when it's a genuine timestamp (real per-event time,
  // whether sync-derived or user-edited). Falls back to the legacy
  // leading-time-in-notiz convention (e.g. "10:30–10:50 Uhr (20min)") for
  // everything else: events with no datum_zeit at all (no date to begin
  // with, e.g. LinkedIn's own relative-date scrape), and events whose
  // datum_zeit is just the v4.6.7 noon-backfill placeholder (see
  // displayableDatumZeit() above).
  const timeStr = (() => {
    const fromDatumZeit = datumZeitToBerlinTimeInput(displayableDatumZeit(event))
    if (fromDatumZeit) return fromDatumZeit
    const m = (event.notiz ?? '').match(/^(\d{1,2}:\d{2}(?:–\d{1,2}:\d{2})?\s*Uhr)/)
    return m ? m[1] : null
  })()

  async function save() {
    setSaving(true)
    try {
      await api.applications.updateEvent(appId, event.id, {
        typ: draft.typ,
        datum: draft.datum || undefined,
        // Sent as a naive Europe/Berlin wall-clock reading; the backend
        // converts to UTC before storing (_berlin_naive_to_utc_naive()).
        datum_zeit: draft.datum && draft.zeit ? `${draft.datum}T${draft.zeit}:00` : null,
        titel: draft.titel || undefined,
        notiz: draft.notiz || undefined,
      })
      onUpdated()
      setEditing(false)
    } finally {
      setSaving(false)
    }
  }

  async function deleteEvent() {
    if (!confirm(t('timeline.confirmDeleteEvent'))) return
    await api.applications.deleteEvent(appId, event.id)
    onUpdated()
  }

  if (editing) {
    const { icon: editIcon, bg: editBg, fg: editFg } = getEventIcon(event)
    return (
      <div className="relative">
        <div className={`absolute -left-5 top-1.5 h-[18px] w-[18px] rounded-full border-2 border-white flex items-center justify-center ${editBg}`}>
          <span className={editFg}>{editIcon}</span>
        </div>
        <div className="rounded-lg border border-indigo-200 bg-indigo-50 p-3 space-y-2">
          <div className="grid grid-cols-3 gap-2">
            <select
              className="rounded-md border border-gray-200 px-2 py-1.5 text-xs bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
              value={draft.typ}
              onChange={e => setDraft(d => ({ ...d, typ: e.target.value }))}
            >
              {EVENT_TYPES.map(typ => (
                <option key={typ} value={typ}>{t(`eventType.${typ}`, { defaultValue: typ })}</option>
              ))}
            </select>
            <input
              type="date"
              className="rounded-md border border-gray-200 px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
              value={draft.datum}
              onChange={e => setDraft(d => ({ ...d, datum: e.target.value }))}
            />
            <input
              type="time"
              title={t('timeline.timeOptional')}
              className="rounded-md border border-gray-200 px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
              value={draft.zeit}
              onChange={e => setDraft(d => ({ ...d, zeit: e.target.value }))}
            />
          </div>
          <input
            className="w-full rounded-md border border-gray-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder={t('timeline.titlePlaceholderPlain')}
            value={draft.titel}
            onChange={e => setDraft(d => ({ ...d, titel: e.target.value }))}
          />
          <textarea
            rows={2}
            className="w-full rounded-md border border-gray-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder={t('timeline.notePlaceholderPlain')}
            value={draft.notiz}
            onChange={e => setDraft(d => ({ ...d, notiz: e.target.value }))}
          />
          <div className="flex justify-end gap-2 pt-1">
            <button type="button" onClick={() => setEditing(false)} className="text-xs text-gray-500 hover:text-gray-700 px-2 py-1">{t('timeline.cancel')}</button>
            <button type="button" disabled={saving} onClick={save} className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50">
              {saving ? t('timeline.saving') : t('timeline.save')}
            </button>
          </div>
        </div>
      </div>
    )
  }

  const { icon: evIcon, bg: evBg, fg: evFg } = getEventIcon(event)
  return (
    <div className="relative group">
      <div className={`absolute -left-5 top-1 h-[18px] w-[18px] rounded-full border-2 border-white flex items-center justify-center ${evBg}`}>
        <span className={evFg}>{evIcon}</span>
      </div>
      <div className="text-xs text-gray-400 mb-0.5 flex items-center gap-2 flex-wrap">
        <span>{dateStr ?? <span className="italic">{t('timeline.noDate')}</span>}{timeStr && <span className="text-gray-400">, {timeStr}</span>}</span>
        <span className="uppercase tracking-wide font-medium text-gray-400">{styleLabel}</span>
        <SourceBadge source={event.source} external_id={event.external_id} external_url={event.external_url} />
        <span className="ml-auto hidden group-hover:flex items-center gap-1">
          <button
            onClick={() => { setDraft({ typ: event.typ, datum: event.datum ?? '', zeit: datumZeitToBerlinTimeInput(displayableDatumZeit(event)), titel: event.titel ?? '', notiz: event.notiz ?? '' }); setEditing(true) }}
            className="p-0.5 rounded hover:bg-gray-200 text-gray-400 hover:text-gray-600"
            title={t('timeline.editTitle')}
          >
            <Pencil className="h-3 w-3" />
          </button>
          <button
            onClick={deleteEvent}
            className="p-0.5 rounded hover:bg-red-50 text-gray-400 hover:text-red-500"
            title={t('timeline.deleteTitle')}
          >
            <Trash2 className="h-3 w-3" />
          </button>
        </span>
      </div>
      {event.titel && <p className="text-sm font-medium text-gray-800">{event.titel}</p>}
      {event.autor && <p className="text-xs text-gray-500 italic">{event.autor}</p>}
      {event.notiz && <p className="text-sm text-gray-600 whitespace-pre-wrap">{event.notiz}</p>}
      {(event.attachments ?? []).length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {event.attachments!.map(att => (
            <button
              key={att.id}
              type="button"
              onClick={() => api.attachments.download(att.id, att.filename)}
              className="inline-flex items-center gap-1 rounded border border-gray-200 bg-gray-50 px-2 py-0.5 text-xs text-gray-600 hover:bg-gray-100"
            >
              <Paperclip className="h-3 w-3 text-gray-400" />
              <span className="truncate max-w-[160px]">{att.filename}</span>
              {att.size_bytes && (
                <span className="text-gray-400">({(att.size_bytes / 1024).toFixed(0)} KB)</span>
              )}
              <Download className="h-2.5 w-2.5 text-gray-400" />
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
