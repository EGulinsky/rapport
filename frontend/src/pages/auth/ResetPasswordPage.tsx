import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../../context/AuthContext'
import { errorMessage } from '../../i18n/errorMessage'
import { AuthLayout, authInputClass, authButtonClass, AuthError, AuthSuccess } from './AuthLayout'

export function ResetPasswordPage() {
  const { t } = useTranslation('auth')
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
      setError(t('validation.passwordTooShort'))
      return
    }
    if (password !== confirm) {
      setError(t('validation.passwordMismatch'))
      return
    }
    setSubmitting(true)
    try {
      await resetPassword(email, code.trim(), password)
      setDone(true)
    } catch (err) {
      setError(errorMessage(err, t))
    } finally {
      setSubmitting(false)
    }
  }

  if (done) {
    return (
      <AuthLayout title={t('resetPassword.doneTitle')}>
        <AuthSuccess message={t('resetPassword.doneMessage')} />
        <button onClick={() => navigate('/login')} className={authButtonClass}>{t('resetPassword.doneButton')}</button>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout title={t('resetPassword.title')} subtitle={t('resetPassword.subtitle')}>
      {error && <AuthError message={error} />}
      <form onSubmit={onSubmit} className="space-y-3">
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">{t('emailLabel')}</label>
          <input
            type="email" required value={email}
            onChange={e => setEmail(e.target.value)}
            className={authInputClass}
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">{t('resetPassword.codeLabel')}</label>
          <input
            type="text" required autoFocus value={code}
            onChange={e => setCode(e.target.value)}
            className={`${authInputClass} tracking-[0.3em] text-center font-mono text-base`}
            placeholder="000000" maxLength={6} inputMode="numeric"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">{t('resetPassword.passwordLabel')}</label>
          <input
            type="password" required minLength={8} value={password}
            onChange={e => setPassword(e.target.value)}
            className={authInputClass} placeholder={t('resetPassword.passwordPlaceholder')}
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">{t('resetPassword.confirmLabel')}</label>
          <input
            type="password" required minLength={8} value={confirm}
            onChange={e => setConfirm(e.target.value)}
            className={authInputClass}
          />
        </div>
        <button type="submit" disabled={submitting} className={authButtonClass}>
          {submitting ? t('resetPassword.submitting') : t('resetPassword.submit')}
        </button>
      </form>
      <p className="mt-4 text-center text-xs text-gray-500">
        {t('backToLogin')} <Link to="/login" className="text-indigo-600 hover:underline font-medium">{t('loginLink')}</Link>
      </p>
    </AuthLayout>
  )
}
