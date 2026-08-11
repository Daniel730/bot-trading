import type { Page } from '@playwright/test'

/** Mock dashboard APIs for paper-safe e2e — no live broker/capital. */
export async function installDashboardMocks(page: Page) {
  await page.route('**/api/auth/login/**', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback()
      return
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        session_token: 'e2e-session-token',
        expires_at: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
        actor: 'dashboard',
        two_factor: { enabled: true, pending_setup: false, backup_codes_remaining: 8 },
      }),
    })
  })

  await page.route('**/api/**', async (route) => {
    const url = route.request().url()
    if (url.includes('/api/auth/login')) {
      await route.fallback()
      return
    }
    // Generic empty-ok payloads so the shell can mount without a backend.
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(emptyPayloadFor(url)),
    })
  })

  // Swallow websocket/stream probes.
  await page.route('**/stream**', async (route) => {
    await route.fulfill({ status: 200, body: '' })
  })
}

function emptyPayloadFor(url: string): unknown {
  if (url.includes('/pairs')) {
    return { pairs: [], scout_candidates: [], active: [], waiting: [] }
  }
  if (url.includes('/positions') || url.includes('/broker')) {
    return { positions: [], provider: 'ALPACA', total_market_value: 0 }
  }
  if (url.includes('/summary')) {
    return {
      open_signals: 0,
      open_positions: 0,
      equity: 10000,
      cash: 10000,
      pnl_today: 0,
    }
  }
  if (url.includes('/health')) {
    return { current: { cpu_pct: 1, system_memory_pct: 10, rss_mb: 100, threads: 4 }, history: [], runtime: { mode: 'paper' } }
  }
  if (url.includes('/config')) {
    return { PAPER_TRADING: true, settings: {} }
  }
  if (url.includes('/logs')) {
    return { lines: [] }
  }
  if (url.includes('/trades') || url.includes('/history')) {
    return { trades: [], total: 0, page: 1 }
  }
  if (url.includes('/chart')) {
    return { points: [] }
  }
  return { status: 'ok' }
}
