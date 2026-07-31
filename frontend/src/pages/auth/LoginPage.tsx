import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../../context/AuthContext'
import { errorMessage } from '../../i18n/errorMessage'
import { AuthLayout, authInputClass, authButtonClass, AuthError } from './AuthLayout'

export function LoginPage() {
  const { t } = useTranslation('auth')
  const { login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login(email, password)
      navigate('/')
    } catch (err) {
      setError(errorMessage(err, t))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthLayout title={t('login.title')} subtitle={t('login.subtitle')}>
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
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">{t('login.passwordLabel')}</label>
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
