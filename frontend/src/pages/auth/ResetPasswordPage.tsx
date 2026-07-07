import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { AuthLayout, authInputClass, authButtonClass, AuthError, AuthSuccess } from './AuthLayout'

export function ResetPasswordPage() {
  const { resetPassword } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [email, setEmail] = useState(params.get('email') ?? '')
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)
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
      await resetPassword(email, code.trim(), password)
      setDone(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSubmitting(false)
    }
  }

  if (done) {
    return (
      <AuthLayout title="Passwort zurückgesetzt">
        <AuthSuccess message="Dein Passwort wurde geändert. Du kannst dich jetzt anmelden." />
        <button onClick={() => navigate('/login')} className={authButtonClass}>Zur Anmeldung</button>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout title="Neues Passwort setzen" subtitle="Gib den Code aus der E-Mail und dein neues Passwort ein.">
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
          <label className="block text-xs font-medium text-gray-700 mb-1">Code</label>
          <input
            type="text" required autoFocus value={code}
            onChange={e => setCode(e.target.value)}
            className={`${authInputClass} tracking-[0.3em] text-center font-mono text-base`}
            placeholder="000000" maxLength={6} inputMode="numeric"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Neues Passwort</label>
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
          {submitting ? 'Setze Passwort…' : 'Passwort setzen'}
        </button>
      </form>
      <p className="mt-4 text-center text-xs text-gray-500">
        Zurück zur <Link to="/login" className="text-indigo-600 hover:underline font-medium">Anmeldung</Link>
      </p>
    </AuthLayout>
  )
}
