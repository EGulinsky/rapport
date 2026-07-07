import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'
import { api, getToken, setToken, AUTH_UNAUTHORIZED_EVENT, type AuthUser } from '../api/client'

interface AuthContextValue {
  user: AuthUser | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  verifyEmail: (email: string, code: string) => Promise<void>
  resendCode: (email: string) => Promise<void>
  forgotPassword: (email: string) => Promise<void>
  resetPassword: (email: string, code: string, newPassword: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)

  const refreshUser = useCallback(async () => {
    if (!getToken()) {
      setUser(null)
      return
    }
    try {
      setUser(await api.auth.me())
    } catch {
      setUser(null)
    }
  }, [])

  useEffect(() => {
    refreshUser().finally(() => setLoading(false))
  }, [refreshUser])

  useEffect(() => {
    function onUnauthorized() { setUser(null) }
    window.addEventListener(AUTH_UNAUTHORIZED_EVENT, onUnauthorized)
    return () => window.removeEventListener(AUTH_UNAUTHORIZED_EVENT, onUnauthorized)
  }, [])

  async function login(email: string, password: string) {
    const res = await api.auth.login(email, password)
    setToken(res.access_token)
    await refreshUser()
  }

  async function register(email: string, password: string) {
    await api.auth.register(email, password)
  }

  async function verifyEmail(email: string, code: string) {
    const res = await api.auth.verifyEmail(email, code)
    setToken(res.access_token)
    await refreshUser()
  }

  async function resendCode(email: string) {
    await api.auth.resendCode(email)
  }

  async function forgotPassword(email: string) {
    await api.auth.forgotPassword(email)
  }

  async function resetPassword(email: string, code: string, newPassword: string) {
    await api.auth.resetPassword(email, code, newPassword)
  }

  function logout() {
    setToken(null)
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, register, verifyEmail, resendCode, forgotPassword, resetPassword, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth muss innerhalb von <AuthProvider> verwendet werden')
  return ctx
}
