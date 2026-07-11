import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../../context/AuthContext'
import { errorMessage } from '../../i18n/errorMessage'
import { AuthLayout, authInputClass, authButtonClass, AuthError } from './AuthLayout'

export function ForgotPasswordPage() {
  const { t } = useTranslation('auth')
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
      setError(errorMessage(err, t))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthLayout title={t('forgotPassword.title')} subtitle={t('forgotPassword.subtitle')}>
      {error && <AuthError message={error} />}
      <form onSubmit={onSubmit} className="space-y-3">
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">{t('emailLabel')}</label>
          <input
            type="email" required autoFocus value={email}
            onChange={e => setEmail(e.target.value)}
            className={authInputClass} placeholder={t('emailPlaceholder')}
          />
        </div>
        <button type="submit" disabled={submitting} className={authButtonClass}>
          {submitting ? t('forgotPassword.submitting') : t('forgotPassword.submit')}
        </button>
      </form>
      <p className="mt-4 text-center text-xs text-gray-500">
        {t('backToLogin')} <Link to="/login" className="text-indigo-600 hover:underline font-medium">{t('loginLink')}</Link>
      </p>
    </AuthLayout>
  )
}
