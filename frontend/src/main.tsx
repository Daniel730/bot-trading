import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { scrubAuthQueryParamsFromUrl } from './services/dashboardSession'
import { initSentry } from './sentry'

scrubAuthQueryParamsFromUrl()
initSentry()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
