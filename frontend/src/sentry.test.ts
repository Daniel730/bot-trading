import { describe, expect, it, vi, beforeEach } from 'vitest'

const initMock = vi.fn()

vi.mock('@sentry/react', () => ({
  init: (...args: unknown[]) => initMock(...args),
}))

describe('initSentry', () => {
  beforeEach(() => {
    initMock.mockReset()
    vi.resetModules()
  })

  it('does not init when DSN is empty (fail-closed)', async () => {
    vi.stubEnv('VITE_SENTRY_DSN', '')
    vi.stubEnv('VITE_SENTRY_ENABLED', 'true')
    const { initSentry } = await import('./sentry')
    expect(initSentry()).toBe(false)
    expect(initMock).not.toHaveBeenCalled()
  })

  it('does not init when enabled flag is false', async () => {
    vi.stubEnv('VITE_SENTRY_DSN', 'https://key@example.ingest.sentry.io/1')
    vi.stubEnv('VITE_SENTRY_ENABLED', 'false')
    const { initSentry } = await import('./sentry')
    expect(initSentry()).toBe(false)
    expect(initMock).not.toHaveBeenCalled()
  })

  it('inits when DSN and enabled are set', async () => {
    vi.stubEnv('VITE_SENTRY_DSN', 'https://key@example.ingest.sentry.io/1')
    vi.stubEnv('VITE_SENTRY_ENABLED', 'true')
    vi.stubEnv('VITE_SENTRY_TRACES_SAMPLE_RATE', '0')
    vi.stubEnv('VITE_SENTRY_ENVIRONMENT', 'test')
    const { initSentry } = await import('./sentry')
    expect(initSentry()).toBe(true)
    expect(initMock).toHaveBeenCalledOnce()
    expect(initMock.mock.calls[0][0].sendDefaultPii).toBe(false)
  })
})
