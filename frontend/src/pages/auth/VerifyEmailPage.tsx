import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../../context/AuthContext'
import { errorMessage } from '../../i18n/errorMessage'
import { AuthLayout, authInputClass, authButtonClass, AuthError } from './AuthLayout'

export function VerifyEmailPage() {
  const { t } = useTranslation('auth')
  const { verifyEmail, resendCode } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [email, setEmail] = useState(params.get('email') ?? '')
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [resending, setResending] = useState(false)
  const [resent, setResent] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await verifyEmail(email, code.trim())
      navigate('/')
    } catch (err) {
      setError(errorMessage(err, t))
    } finally {
      setSubmitting(false)
    }
  }

  async function onResend() {
    setError(null)
    setResent(false)
    setResending(true)
    try {
      await resendCode(email)
      setResent(true)
    } catch (err) {
      setError(errorMessage(err, t))
    } finally {
      setResending(false)
    }
  }

  return (
    <AuthLayout title={t('verifyEmail.title')} subtitle={t('verifyEmail.subtitle')}>
      {error && <AuthError message={error} />}
      {resent && !error && (
        <div className="mb-3 rounded-lg bg-green-50 px-3 py-2 text-xs text-green-700">
          {t('verifyEmail.resentMessage')}
        </div>
      )}
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
          <label className="block text-xs font-medium text-gray-700 mb-1">{t('verifyEmail.codeLabel')}</label>
          <input
            type="text" required autoFocus value={code}
            onChange={e => setCode(e.target.value)}
            className={`${authInputClass} tracking-[0.3em] text-center font-mono text-base`}
            placeholder="000000" maxLength={6} inputMode="numeric"
          />
        </div>
        <button type="submit" disabled={submitting} className={authButtonClass}>
          {submitting ? t('verifyEmail.submitting') : t('verifyEmail.submit')}
        </button>
      </form>
      <button
        type="button" onClick={onResend} disabled={resending || !email}
        className="mt-3 w-full text-center text-xs text-indigo-600 hover:underline font-medium disabled:opacity-50 disabled:no-underline"
      >
        {resending ? t('verifyEmail.resending') : t('verifyEmail.resend')}
      </button>
      <p className="mt-4 text-center text-xs text-gray-500">
        {t('backToLogin')} <Link to="/login" className="text-indigo-600 hover:underline font-medium">{t('loginLink')}</Link>
      </p>
    </AuthLayout>
  )
}
