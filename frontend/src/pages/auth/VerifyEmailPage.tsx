import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { AuthLayout, authInputClass, authButtonClass, AuthError } from './AuthLayout'

export function VerifyEmailPage() {
  const { verifyEmail } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [email, setEmail] = useState(params.get('email') ?? '')
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

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

  return (
    <AuthLayout
      title="E-Mail bestätigen"
      subtitle="Wir haben einen 6-stelligen Code an deine E-Mail-Adresse geschickt."
    >
      {error && <AuthError message={error} />}
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
      <p className="mt-4 text-center text-xs text-gray-500">
        Zurück zur <Link to="/login" className="text-indigo-600 hover:underline font-medium">Anmeldung</Link>
      </p>
    </AuthLayout>
  )
}
