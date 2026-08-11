/**
 * Browser Sentry — fail-closed when VITE_SENTRY_DSN is empty.
 * Errors only by default; keep tracesSampleRate at 0 when OTel owns traces.
 */
import * as Sentry from '@sentry/react'

const dsn = (import.meta.env.VITE_SENTRY_DSN as string | undefined)?.trim() || ''
const enabledFlag = String(import.meta.env.VITE_SENTRY_ENABLED || '').toLowerCase() === 'true'

export function initSentry(): boolean {
  if (!dsn || !enabledFlag) {
    return false
  }

  const tracesSampleRate = Number(import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE ?? 0)
  const environment =
    (import.meta.env.VITE_SENTRY_ENVIRONMENT as string | undefined)?.trim() ||
    (import.meta.env.MODE as string) ||
    'development'
  const release =
    (import.meta.env.VITE_SENTRY_RELEASE as string | undefined)?.trim() ||
    (import.meta.env.VITE_IMAGE_TAG as string | undefined)?.trim() ||
    undefined

  Sentry.init({
    dsn,
    environment,
    release,
    sendDefaultPii: false,
    tracesSampleRate: Number.isFinite(tracesSampleRate) ? tracesSampleRate : 0,
    beforeSend(event) {
      const headers = event.request?.headers
      if (headers && typeof headers === 'object') {
        for (const key of Object.keys(headers)) {
          if (/authorization|dashboard|token|session/i.test(key)) {
            headers[key] = '[Filtered]'
          }
        }
      }
      return event
    },
  })
  return true
}
