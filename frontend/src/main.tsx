import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { I18nextProvider } from 'react-i18next'
import App from './App'
import './index.css'
import i18n from './i18n'
import { AuthProvider } from './context/AuthContext'
import { RequireAuth } from './components/RequireAuth'
import { AppRoutes } from './AppRoutes'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <I18nextProvider i18n={i18n}>
      <BrowserRouter>
        <AuthProvider>
          <AppRoutes app={<RequireAuth><App /></RequireAuth>} />
        </AuthProvider>
      </BrowserRouter>
    </I18nextProvider>
  </React.StrictMode>
)
