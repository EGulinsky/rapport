import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { AuthLayout, authInputClass, authButtonClass, AuthError } from './AuthLayout'

export function ForgotPasswordPage() {
  const { forgotPassword } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await forgotPassword(email)
      navigate(`/reset-password?email=${encodeURIComponent(email)}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthLayout
      title="Passwort vergessen"
      subtitle="Wir schicken dir einen 6-stelligen Code, falls ein Konto mit dieser E-Mail-Adresse existiert."
    >
      {error && <AuthError message={error} />}
      <form onSubmit={onSubmit} className="space-y-3">
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">E-Mail</label>
          <input
            type="email" required autoFocus value={email}
            onChange={e => setEmail(e.target.value)}
            className={authInputClass} placeholder="du@beispiel.de"
          />
        </div>
        <button type="submit" disabled={submitting} className={authButtonClass}>
          {submitting ? 'Sende Code…' : 'Code anfordern'}
        </button>
      </form>
      <p className="mt-4 text-center text-xs text-gray-500">
        Zurück zur <Link to="/login" className="text-indigo-600 hover:underline font-medium">Anmeldung</Link>
      </p>
    </AuthLayout>
  )
}
