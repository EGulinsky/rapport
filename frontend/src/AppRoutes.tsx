import type { ReactNode } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './context/AuthContext'
import { LoginPage } from './pages/auth/LoginPage'
import { RegisterPage } from './pages/auth/RegisterPage'
import { VerifyEmailPage } from './pages/auth/VerifyEmailPage'
import { ForgotPasswordPage } from './pages/auth/ForgotPasswordPage'
import { ResetPasswordPage } from './pages/auth/ResetPasswordPage'

/** Bereits eingeloggte Nutzer werden von den Auth-Seiten weg zur App geleitet
 * (z.B. Browser-Zurück auf /login nach erfolgreichem Login). Während der
 * Session-Hydration (loading) wird nichts umgeleitet, um Flackern zu vermeiden. */
function RedirectIfAuthenticated({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  if (!loading && user) return <Navigate to="/" replace />
  return <>{children}</>
}

export function AppRoutes({ app }: { app: ReactNode }) {
  return (
    <Routes>
      <Route path="/login" element={<RedirectIfAuthenticated><LoginPage /></RedirectIfAuthenticated>} />
      <Route path="/register" element={<RedirectIfAuthenticated><RegisterPage /></RedirectIfAuthenticated>} />
      <Route path="/verify-email" element={<VerifyEmailPage />} />
      <Route path="/forgot-password" element={<RedirectIfAuthenticated><ForgotPasswordPage /></RedirectIfAuthenticated>} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/*" element={app} />
    </Routes>
  )
}
