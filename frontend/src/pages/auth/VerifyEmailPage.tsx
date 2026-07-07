import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { AuthLayout, authInputClass, authButtonClass, AuthError } from './AuthLayout'

export function VerifyEmailPage() {
  const { verifyEmail, resendCode } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [email, setEmail] = useState(params.get('email') ?? '')
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [resending, setResending] = useState(false)
  const [resent, setResent] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await verifyEmail(email, code.trim())
      navigate('/')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSubmitting(false)
    }
  }

  async function onResend() {
    setError(null)
    setResent(false)
    setResending(true)
    try {
      await resendCode(email)
      setResent(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setResending(false)
    }
  }

  return (
    <AuthLayout
      title="E-Mail bestätigen"
      subtitle="Wir haben einen 6-stelligen Code an deine E-Mail-Adresse geschickt."
    >
      {error && <AuthError message={error} />}
      {resent && !error && (
        <div className="mb-3 rounded-lg bg-green-50 px-3 py-2 text-xs text-green-700">
          Falls ein unbestätigtes Konto mit dieser E-Mail-Adresse existiert, wurde ein neuer Code gesendet.
        </div>
      )}
      <form onSubmit={onSubmit} className="space-y-3">
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">E-Mail</label>
          <input
            type="email" required value={email}
            onChange={e => setEmail(e.target.value)}
            className={authInputClass}
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Bestätigungscode</label>
          <input
            type="text" required autoFocus value={code}
            onChange={e => setCode(e.target.value)}
            className={`${authInputClass} tracking-[0.3em] text-center font-mono text-base`}
            placeholder="000000" maxLength={6} inputMode="numeric"
          />
        </div>
        <button type="submit" disabled={submitting} className={authButtonClass}>
          {submitting ? 'Bestätige…' : 'Bestätigen'}
        </button>
      </form>
      <button
        type="button" onClick={onResend} disabled={resending || !email}
        className="mt-3 w-full text-center text-xs text-indigo-600 hover:underline font-medium disabled:opacity-50 disabled:no-underline"
      >
        {resending ? 'Sende…' : 'Code erneut senden'}
      </button>
      <p className="mt-4 text-center text-xs text-gray-500">
        Zurück zur <Link to="/login" className="text-indigo-600 hover:underline font-medium">Anmeldung</Link>
      </p>
    </AuthLayout>
  )
}
