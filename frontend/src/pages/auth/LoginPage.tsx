import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { AuthLayout, authInputClass, authButtonClass, AuthError } from './AuthLayout'

export function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [needsVerification, setNeedsVerification] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setNeedsVerification(false)
    setSubmitting(true)
    try {
      await login(email, password)
      navigate('/')
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      setError(message)
      if (message.toLowerCase().includes('bestätigt')) setNeedsVerification(true)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthLayout title="Anmelden" subtitle="Melde dich mit deinem rapport-Konto an.">
      {error && <AuthError message={error} />}
      {needsVerification && (
        <p className="text-xs text-gray-500 mb-4">
          <Link to={`/verify-email?email=${encodeURIComponent(email)}`} className="text-indigo-600 hover:underline font-medium">
            Jetzt E-Mail-Adresse bestätigen →
          </Link>
        </p>
      )}
      <form onSubmit={onSubmit} className="space-y-3">
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">E-Mail</label>
          <input
            type="email" required autoFocus value={email}
            onChange={e => setEmail(e.target.value)}
            className={authInputClass} placeholder="du@beispiel.de"
          />
        </div>
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="block text-xs font-medium text-gray-700">Passwort</label>
            <Link to="/forgot-password" className="text-xs text-indigo-600 hover:underline">Vergessen?</Link>
          </div>
          <input
            type="password" required value={password}
            onChange={e => setPassword(e.target.value)}
            className={authInputClass}
          />
        </div>
        <button type="submit" disabled={submitting} className={authButtonClass}>
          {submitting ? 'Anmelden…' : 'Anmelden'}
        </button>
      </form>
      <p className="mt-4 text-center text-xs text-gray-500">
        Noch kein Konto?{' '}
        <Link to="/register" className="text-indigo-600 hover:underline font-medium">Registrieren</Link>
      </p>
    </AuthLayout>
  )
}
