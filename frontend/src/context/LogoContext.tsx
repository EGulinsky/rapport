import { createContext, useContext, useState, useEffect, type ReactNode } from 'react'
import { api } from '../api/client'

interface LogoContextValue {
  logoDevKey: string | null
  setLogoDevKey: (key: string | null) => void
}

const LogoContext = createContext<LogoContextValue>({ logoDevKey: null, setLogoDevKey: () => {} })

export function LogoProvider({ children }: { children: ReactNode }) {
  const [logoDevKey, setLogoDevKey] = useState<string | null>(null)

  useEffect(() => {
    api.settings.getLogo().then(r => setLogoDevKey(r.api_key)).catch(() => {})
  }, [])

  return (
    <LogoContext.Provider value={{ logoDevKey, setLogoDevKey }}>
      {children}
    </LogoContext.Provider>
  )
}

export const useLogoKey = () => useContext(LogoContext)
