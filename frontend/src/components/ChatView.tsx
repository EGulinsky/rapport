import { useState, useEffect, useRef, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Send, Trash2, AlertCircle, Sparkles } from 'lucide-react'
import { api, ApiError } from '../api/client'
import type { ChatMessage } from '../types'
import clsx from 'clsx'

interface PendingUserMessage {
  tempId: string
  content: string
}

export function ChatView() {
  const { t } = useTranslation('chat')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loading, setLoading] = useState(true)
  const [input, setInput] = useState('')
  const [pending, setPending] = useState<PendingUserMessage | null>(null)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<{ key: string | null; message: string } | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    api.chat.history().then(r => setMessages(r.messages)).finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, pending, sending])

  const errorCopy = useCallback((key: string | null): string => {
    switch (key) {
      case 'ai.rate_limit': return t('errors.rateLimited')
      case 'ai.tools_unsupported': return t('errors.toolsUnsupported')
      default: return t('errors.generic')
    }
  }, [t])

  async function doSend(content: string) {
    setSending(true)
    setError(null)
    try {
      const result = await api.chat.send(content)
      setMessages(m => [...m, result.user_message, result.assistant_message])
      setPending(null)
    } catch (e) {
      const apiErr = e instanceof ApiError ? e : null
      const key = apiErr?.errorKey ?? null
      setError({ key, message: errorCopy(key) })
    } finally {
      setSending(false)
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const content = input.trim()
    if (!content || sending) return
    setPending({ tempId: `temp-${Date.now()}`, content })
    setInput('')
    doSend(content)
  }

  function retry() {
    if (!pending) return
    doSend(pending.content)
  }

  async function clearConversation() {
    if (!confirm(t('clearConfirm'))) return
    await api.chat.clear()
    setMessages([])
    setPending(null)
    setError(null)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
      </div>
    )
  }

  return (
    <div className="flex flex-col h-[calc(100vh-180px)] max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-indigo-600" />
          <h2 className="text-lg font-semibold text-gray-800">{t('tabLabel')}</h2>
        </div>
        {messages.length > 0 && (
          <button type="button" onClick={clearConversation}
            className="flex items-center gap-1 text-xs text-gray-400 hover:text-red-500">
            <Trash2 className="h-3.5 w-3.5" /> {t('clearConversation')}
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto rounded-xl border border-gray-100 bg-gray-50 p-4 space-y-3">
        {messages.length === 0 && !pending && (
          <p className="text-sm text-gray-400 text-center mt-8">{t('emptyState')}</p>
        )}
        {messages.map(m => (
          <div key={m.id} className={clsx('flex', m.role === 'user' ? 'justify-end' : 'justify-start')}>
            <div className={clsx(
              'max-w-[80%] rounded-2xl px-4 py-2 text-sm whitespace-pre-wrap',
              m.role === 'user' ? 'bg-indigo-600 text-white' : 'bg-white border border-gray-200 text-gray-800'
            )}>
              {m.content}
            </div>
          </div>
        ))}
        {pending && (
          <div className="flex justify-end">
            <div className="max-w-[80%] rounded-2xl px-4 py-2 text-sm whitespace-pre-wrap bg-indigo-600 text-white">
              {pending.content}
            </div>
          </div>
        )}
        {sending && (
          <div className="flex justify-start">
            <div className="rounded-2xl px-4 py-2.5 bg-white border border-gray-200 flex items-center gap-1">
              <span className="h-1.5 w-1.5 rounded-full bg-gray-300 animate-bounce [animation-delay:-0.3s]" />
              <span className="h-1.5 w-1.5 rounded-full bg-gray-300 animate-bounce [animation-delay:-0.15s]" />
              <span className="h-1.5 w-1.5 rounded-full bg-gray-300 animate-bounce" />
            </div>
          </div>
        )}
        {error && (
          <div className="flex justify-start">
            <div className="max-w-[80%] rounded-2xl px-4 py-2 text-sm bg-red-50 border border-red-200 text-red-700 flex items-start gap-2">
              <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
              <div>
                <p>{error.message}</p>
                <button type="button" onClick={retry} className="mt-1 text-xs font-medium text-red-800 hover:underline">
                  {t('retry')}
                </button>
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={handleSubmit} className="mt-3 flex gap-2">
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder={t('placeholder')}
          disabled={sending}
          className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
        />
        <button type="submit" disabled={sending || !input.trim()}
          className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50 disabled:hover:bg-indigo-600">
          <Send className="h-4 w-4" /> {t('send')}
        </button>
      </form>
    </div>
  )
}
