import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './theme'
import App from './App.tsx'
import AuthGate from './AuthGate.tsx'
import { API } from './api'
import { installAuth } from './auth'

installAuth(API)
if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => { navigator.serviceWorker.register('/sw.js').catch(() => {}) })
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
    <AuthGate />
  </StrictMode>,
)
