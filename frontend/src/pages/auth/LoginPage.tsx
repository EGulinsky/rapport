import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../../context/AuthContext'
import { ApiError } from '../../api/client'
import { errorMessage } from '../../i18n/errorMessage'
import { AuthLayout, authInputClass, authButtonClass, AuthError } from './AuthLayout'

export function LoginPage() {
  const { t } = useTranslation('auth')
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
      setError(errorMessage(err, t))
      if (err instanceof ApiError && err.errorKey === 'auth.email_not_verified') setNeedsVerification(true)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthLayout title={t('login.title')} subtitle={t('login.subtitle')}>
      {error && <AuthError message={error} />}
      {needsVerification && (
        <p className="text-xs text-gray-500 mb-4">
          <Link to={`/verify-email?email=${encodeURIComponent(email)}`} className="text-indigo-600 hover:underline font-medium">
            {t('login.verifyNowLink')}
          </Link>
        </p>
      )}
      <form onSubmit={onSubmit} className="space-y-3">
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">{t('emailLabel')}</label>
          <input
            type="email" required autoFocus value={email}
            onChange={e => setEmail(e.target.value)}
            className={authInputClass} placeholder={t('emailPlaceholder')}
          />
        </div>
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="block text-xs font-medium text-gray-700">{t('login.passwordLabel')}</label>
            <Link to="/forgot-password" className="text-xs text-indigo-600 hover:underline">{t('login.forgotLink')}</Link>
          </div>
          <input
            type="password" required value={password}
            onChange={e => setPassword(e.target.value)}
            className={authInputClass}
          />
        </div>
        <button type="submit" disabled={submitting} className={authButtonClass}>
          {submitting ? t('login.submitting') : t('login.submit')}
        </button>
      </form>
      <p className="mt-4 text-center text-xs text-gray-500">
        {t('login.noAccount')}{' '}
        <Link to="/register" className="text-indigo-600 hover:underline font-medium">{t('login.registerLink')}</Link>
      </p>
    </AuthLayout>
  )
}
