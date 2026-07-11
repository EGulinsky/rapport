import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../../context/AuthContext'
import { errorMessage } from '../../i18n/errorMessage'
import { getPreLoginLanguage, SUPPORTED_LANGUAGES, type SupportedLanguage } from '../../i18n'
import { AuthLayout, authInputClass, authButtonClass, AuthError } from './AuthLayout'

const LANGUAGE_NAMES: Record<SupportedLanguage, string> = { de: 'Deutsch', en: 'English' }

export function RegisterPage() {
  const { t } = useTranslation('auth')
  const { register } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [uiLanguage, setUiLanguage] = useState<SupportedLanguage>(getPreLoginLanguage())
  const [error, setError] = useState<string | null>(null)
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
      await register(email, password, uiLanguage)
      navigate(`/verify-email?email=${encodeURIComponent(email)}`)
    } catch (err) {
      setError(errorMessage(err, t))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthLayout title={t('register.title')} subtitle={t('register.subtitle')}>
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
          <label className="block text-xs font-medium text-gray-700 mb-1">{t('register.passwordLabel')}</label>
          <input
            type="password" required minLength={8} value={password}
            onChange={e => setPassword(e.target.value)}
            className={authInputClass} placeholder={t('register.passwordPlaceholder')}
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">{t('register.confirmLabel')}</label>
          <input
            type="password" required minLength={8} value={confirm}
            onChange={e => setConfirm(e.target.value)}
            className={authInputClass}
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">{t('register.languageLabel')}</label>
          <select
            value={uiLanguage}
            onChange={e => setUiLanguage(e.target.value as SupportedLanguage)}
            className={authInputClass}
          >
            {SUPPORTED_LANGUAGES.map(lang => (
              <option key={lang} value={lang}>{LANGUAGE_NAMES[lang]}</option>
            ))}
          </select>
        </div>
        <button type="submit" disabled={submitting} className={authButtonClass}>
          {submitting ? t('register.submitting') : t('register.submit')}
        </button>
      </form>
      <p className="mt-4 text-center text-xs text-gray-500">
        {t('register.hasAccount')}{' '}
        <Link to="/login" className="text-indigo-600 hover:underline font-medium">{t('register.loginLink')}</Link>
      </p>
    </AuthLayout>
  )
}
