import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { AuthLayout, authInputClass, authButtonClass, AuthError } from './AuthLayout'

export function RegisterPage() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (password.length < 8) {
      setError('Das Passwort muss mindestens 8 Zeichen lang sein.')
      return
    }
    if (password !== confirm) {
      setError('Die Passwörter stimmen nicht überein.')
      return
    }
    setSubmitting(true)
    try {
      await register(email, password)
      navigate(`/verify-email?email=${encodeURIComponent(email)}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthLayout title="Konto erstellen" subtitle="Registriere dich mit E-Mail und Passwort.">
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
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Passwort</label>
          <input
            type="password" required minLength={8} value={password}
            onChange={e => setPassword(e.target.value)}
            className={authInputClass} placeholder="Mindestens 8 Zeichen"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Passwort bestätigen</label>
          <input
            type="password" required minLength={8} value={confirm}
            onChange={e => setConfirm(e.target.value)}
            className={authInputClass}
          />
        </div>
        <button type="submit" disabled={submitting} className={authButtonClass}>
          {submitting ? 'Erstelle Konto…' : 'Konto erstellen'}
        </button>
      </form>
      <p className="mt-4 text-center text-xs text-gray-500">
        Bereits ein Konto?{' '}
        <Link to="/login" className="text-indigo-600 hover:underline font-medium">Einloggen</Link>
      </p>
    </AuthLayout>
  )
}
