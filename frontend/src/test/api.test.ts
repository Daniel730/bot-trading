/**
 * Tests for the PR-changed parts of frontend/src/services/api.ts:
 *
 * - Renamed interfaces: WalletSyncOrder, WalletSyncResponse, WalletRecommendation, etc.
 * - Backward-compat type aliases (T212Wallet* -> Wallet*)
 * - syncWallet function (new name, new endpoint /api/wallet/sync)
 * - syncT212Wallet is the same function as syncWallet
 * - fetchWalletRecommendations hits /api/wallet/recommendations
 * - buyWalletRecommendations hits /api/wallet/recommendations/buy
 * - WalletSyncResponse.mode is now a plain string (not 'demo'|'live')
 * - WalletRecommendation.broker_ticker is required; t212_ticker optional
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  syncWallet,
  syncT212Wallet,
  fetchWalletRecommendations,
  buyWalletRecommendations,
  ApiError,
  type WalletSyncOrder,
  type WalletSyncResponse,
  type WalletRecommendation,
  type WalletRecommendationResponse,
  type WalletRecommendationBuyResponse,
  type T212WalletSyncOrder,
  type T212WalletSyncResponse,
  type T212WalletRecommendation,
  type T212WalletRecommendationResponse,
  type T212WalletRecommendationBuyResponse,
} from '../services/api';

// ---------------------------------------------------------------------------
// Fetch mock setup
// ---------------------------------------------------------------------------

function makeFetchMock(responseData: unknown, status = 200) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: vi.fn().mockResolvedValue(responseData),
  });
}

const MOCK_TOKEN = 'test-token';
const MOCK_SESSION = 'test-session';

beforeEach(() => {
  // Reset fetch mocks between tests
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Type alias backward-compatibility checks (compile-time via structural typing)
// ---------------------------------------------------------------------------

describe('Backward-compat type aliases', () => {
  it('T212WalletSyncOrder is structurally identical to WalletSyncOrder', () => {
    const order: T212WalletSyncOrder = {
      ticker: 'AAPL',
      amount: 10.0,
      status: 'ok',
      order_id: 'abc',
      broker_ticker: 'AAPL',
      t212_ticker: 'AAPL_US_EQ',
      price: 150.0,
    };
    // Must also be assignable to the new type
    const newOrder: WalletSyncOrder = order;
    expect(newOrder.ticker).toBe('AAPL');
    expect(newOrder.broker_ticker).toBe('AAPL');
  });

  it('T212WalletSyncResponse is structurally identical to WalletSyncResponse', () => {
    const response: T212WalletSyncResponse = {
      status: 'ok',
      mode: 'T212',           // now a plain string, not 'demo'|'live'
      message: 'done',
      coint_pairs: 2,
      candidate_tickers: ['AAPL'],
      target_tickers: ['AAPL'],
      skipped: [],
      budget: 100,
      spendable_cash: 90,
      orders: [],
      failures: 0,
    };
    const newResponse: WalletSyncResponse = response;
    expect(newResponse.mode).toBe('T212');
  });

  it('T212WalletRecommendation accepts broker_ticker with optional t212_ticker', () => {
    const rec: T212WalletRecommendation = {
      ticker: 'AAPL',
      broker_ticker: 'AAPL',        // required in new interface
      t212_ticker: undefined,        // now optional
      category: 'coint',
      categories: ['coint'],
      pairs: [],
      sectors: [],
      score: 100,
      max_abs_z_score: 2.5,
      estimated_cost_pct: 0.001,
      rank: 1,
      suggested_amount: 25.0,
      status: 'ready',
    };
    const newRec: WalletRecommendation = rec;
    expect(newRec.broker_ticker).toBe('AAPL');
  });

  it('T212WalletRecommendationResponse mode is plain string', () => {
    const resp: T212WalletRecommendationResponse = {
      status: 'ok',
      mode: 'ALPACA',        // plain string, not 'demo'|'live'
      message: 'ok',
      generated_at: '2026-01-01T00:00:00',
      include_broken: false,
      coint_pairs: 1,
      broken_eligible_pairs: 0,
      candidate_tickers: [],
      recommended_tickers: [],
      budget: 100,
      usable_budget: 100,
      cash_limited: false,
      spendable_cash: null,
      effective_cash: null,
      can_buy: true,
      recommendations: [],
      skipped: [],
    };
    const newResp: WalletRecommendationResponse = resp;
    expect(newResp.mode).toBe('ALPACA');
  });

  it('T212WalletRecommendationBuyResponse mode is plain string', () => {
    const resp: T212WalletRecommendationBuyResponse = {
      status: 'ok',
      mode: 'T212',
      message: 'done',
      budget: 100,
      target_tickers: [],
      recommendations: [],
      skipped: [],
      orders: [],
      failures: 0,
    };
    const newResp: WalletRecommendationBuyResponse = resp;
    expect(newResp.mode).toBe('T212');
  });
});

// ---------------------------------------------------------------------------
// WalletSyncOrder.broker_ticker is present in the interface
// ---------------------------------------------------------------------------

describe('WalletSyncOrder interface', () => {
  it('accepts broker_ticker field alongside optional t212_ticker', () => {
    const order: WalletSyncOrder = {
      ticker: 'MSFT',
      amount: 50.0,
      status: 'pending',
      broker_ticker: 'MSFT',
      t212_ticker: null,
    };
    expect(order.broker_ticker).toBe('MSFT');
    expect(order.t212_ticker).toBeNull();
  });

  it('status can be pending | ok | error | skipped', () => {
    const statuses: WalletSyncOrder['status'][] = ['pending', 'ok', 'error', 'skipped'];
    statuses.forEach(status => {
      const order: WalletSyncOrder = { ticker: 'X', amount: 1, status };
      expect(order.status).toBe(status);
    });
  });
});

// ---------------------------------------------------------------------------
// syncWallet – calls /api/wallet/sync and returns WalletSyncResponse
// ---------------------------------------------------------------------------

describe('syncWallet', () => {
  it('POSTs to /api/wallet/sync with budget in body', async () => {
    const mockResponse: WalletSyncResponse = {
      status: 'ok',
      mode: 'T212',
      message: 'Submitted 2/2 BUY orders.',
      coint_pairs: 2,
      candidate_tickers: ['AAPL', 'MSFT'],
      target_tickers: ['AAPL', 'MSFT'],
      skipped: [],
      budget: 100,
      spendable_cash: 95,
      orders: [],
      failures: 0,
    };

    const fetchMock = makeFetchMock(mockResponse);
    vi.stubGlobal('fetch', fetchMock);

    const result = await syncWallet(MOCK_TOKEN, MOCK_SESSION, 100);

    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url.toString()).toContain('/api/wallet/sync');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ budget: 100 });
    expect(result.mode).toBe('T212');
    expect(result.status).toBe('ok');
  });

  it('includes auth headers when token and session are provided', async () => {
    vi.stubGlobal('fetch', makeFetchMock({ status: 'ok', mode: 'T212', message: '', coint_pairs: 0, candidate_tickers: [], target_tickers: [], skipped: [], budget: 0, spendable_cash: 0, orders: [], failures: 0 }));

    await syncWallet('my-token', 'my-session', 50);

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    const headers = new Headers(init.headers);
    expect(headers.get('Authorization')).toBe('Bearer my-token');
    expect(headers.get('X-Dashboard-Session')).toBe('my-session');
  });

  it('throws ApiError on non-ok response', async () => {
    vi.stubGlobal('fetch', makeFetchMock({ detail: 'Not configured' }, 400));

    await expect(syncWallet(MOCK_TOKEN, MOCK_SESSION, 100)).rejects.toBeInstanceOf(ApiError);
  });

  it('mode field is a plain string (not restricted to demo|live)', async () => {
    const mockResponse: WalletSyncResponse = {
      status: 'ok',
      mode: 'ALPACA',   // provider name, not demo/live
      message: 'ok',
      coint_pairs: 0,
      candidate_tickers: [],
      target_tickers: [],
      skipped: [],
      budget: 0,
      spendable_cash: 0,
      orders: [],
      failures: 0,
    };
    vi.stubGlobal('fetch', makeFetchMock(mockResponse));

    const result = await syncWallet(null, null, 10);
    expect(result.mode).toBe('ALPACA');
  });
});

// ---------------------------------------------------------------------------
// syncT212Wallet – must be the same function reference as syncWallet
// ---------------------------------------------------------------------------

describe('syncT212Wallet backward-compat alias', () => {
  it('is the same function as syncWallet', () => {
    expect(syncT212Wallet).toBe(syncWallet);
  });

  it('also POSTs to /api/wallet/sync (not the old /api/t212/wallet/sync)', async () => {
    vi.stubGlobal('fetch', makeFetchMock({ status: 'ok', mode: 'T212', message: '', coint_pairs: 0, candidate_tickers: [], target_tickers: [], skipped: [], budget: 0, spendable_cash: 0, orders: [], failures: 0 }));

    await syncT212Wallet(null, null, 10);

    const [url] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url.toString()).toContain('/api/wallet/sync');
    expect(url.toString()).not.toContain('/api/t212/');
  });
});

// ---------------------------------------------------------------------------
// fetchWalletRecommendations – calls /api/wallet/recommendations
// ---------------------------------------------------------------------------

describe('fetchWalletRecommendations', () => {
  it('GETs /api/wallet/recommendations with correct query params', async () => {
    const mockResponse: WalletRecommendationResponse = {
      status: 'ok',
      mode: 'T212',
      message: 'Calculated 2 recommendations.',
      generated_at: '2026-01-01T00:00:00',
      include_broken: false,
      coint_pairs: 2,
      broken_eligible_pairs: 0,
      candidate_tickers: ['AAPL', 'MSFT'],
      recommended_tickers: ['AAPL', 'MSFT'],
      budget: 100,
      usable_budget: 100,
      cash_limited: false,
      spendable_cash: 95,
      effective_cash: 90,
      can_buy: true,
      recommendations: [],
      skipped: [],
    };
    vi.stubGlobal('fetch', makeFetchMock(mockResponse));

    const result = await fetchWalletRecommendations(MOCK_TOKEN, MOCK_SESSION, {
      budget: 100,
      includeBroken: true,
      skipOwned: false,
      skipPending: true,
    });

    const [url] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    const urlObj = new URL(url.toString());
    expect(urlObj.pathname).toContain('/api/wallet/recommendations');
    expect(urlObj.searchParams.get('budget')).toBe('100');
    expect(urlObj.searchParams.get('include_broken')).toBe('true');
    expect(urlObj.searchParams.get('skip_owned')).toBe('false');
    expect(urlObj.searchParams.get('skip_pending')).toBe('true');
    expect(result.mode).toBe('T212');
  });

  it('does NOT use old /api/t212/wallet/ path', async () => {
    vi.stubGlobal('fetch', makeFetchMock({ status: 'ok', mode: 'T212', message: '', generated_at: '', include_broken: false, coint_pairs: 0, broken_eligible_pairs: 0, candidate_tickers: [], recommended_tickers: [], budget: 0, usable_budget: 0, cash_limited: false, spendable_cash: null, effective_cash: null, can_buy: false, recommendations: [], skipped: [] }));

    await fetchWalletRecommendations(null, null, { budget: 10 });

    const [url] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url.toString()).not.toContain('/t212/');
  });

  it('uses default params when optional fields omitted', async () => {
    vi.stubGlobal('fetch', makeFetchMock({ status: 'ok', mode: 'T212', message: '', generated_at: '', include_broken: false, coint_pairs: 0, broken_eligible_pairs: 0, candidate_tickers: [], recommended_tickers: [], budget: 0, usable_budget: 0, cash_limited: false, spendable_cash: null, effective_cash: null, can_buy: false, recommendations: [], skipped: [] }));

    await fetchWalletRecommendations(null, null, { budget: 50 });

    const [url] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    const urlObj = new URL(url.toString());
    expect(urlObj.searchParams.get('include_broken')).toBe('false');
    expect(urlObj.searchParams.get('skip_owned')).toBe('true');
    expect(urlObj.searchParams.get('skip_pending')).toBe('true');
  });
});

// ---------------------------------------------------------------------------
// buyWalletRecommendations – calls /api/wallet/recommendations/buy
// ---------------------------------------------------------------------------

describe('buyWalletRecommendations', () => {
  it('POSTs to /api/wallet/recommendations/buy with correct payload', async () => {
    const mockResponse: WalletRecommendationBuyResponse = {
      status: 'ok',
      mode: 'ALPACA',
      message: 'Submitted 2/2.',
      budget: 100,
      target_tickers: ['AAPL', 'MSFT'],
      recommendations: [],
      skipped: [],
      orders: [],
      failures: 0,
    };
    vi.stubGlobal('fetch', makeFetchMock(mockResponse));

    const result = await buyWalletRecommendations(MOCK_TOKEN, MOCK_SESSION, {
      budget: 100,
      includeBroken: true,
      tickers: ['AAPL', 'MSFT'],
      skipOwned: false,
      skipPending: false,
      delaySeconds: 0,
    });

    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url.toString()).toContain('/api/wallet/recommendations/buy');
    expect(url.toString()).not.toContain('/t212/');
    expect(init.method).toBe('POST');
    const body = JSON.parse(init.body);
    expect(body.budget).toBe(100);
    expect(body.include_broken).toBe(true);
    expect(body.tickers).toEqual(['AAPL', 'MSFT']);
    expect(body.skip_owned).toBe(false);
    expect(body.delay_seconds).toBe(0);
    expect(result.mode).toBe('ALPACA');
  });

  it('uses correct defaults when optional payload fields are omitted', async () => {
    vi.stubGlobal('fetch', makeFetchMock({ status: 'ok', mode: 'T212', message: '', budget: 0, target_tickers: [], recommendations: [], skipped: [], orders: [], failures: 0 }));

    await buyWalletRecommendations(null, null, { budget: 50 });

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    const body = JSON.parse(init.body);
    expect(body.include_broken).toBe(false);
    expect(body.skip_owned).toBe(true);
    expect(body.skip_pending).toBe(true);
    expect(body.delay_seconds).toBe(0.5);
    expect(body.tickers).toBeUndefined();
  });

  it('throws ApiError on 400 response', async () => {
    vi.stubGlobal('fetch', makeFetchMock({ detail: 'No tickers available' }, 400));

    await expect(
      buyWalletRecommendations(MOCK_TOKEN, MOCK_SESSION, { budget: 100 })
    ).rejects.toBeInstanceOf(ApiError);
  });
});

// ---------------------------------------------------------------------------
// discoverPairs removal – PR removed this export from api.ts
// ---------------------------------------------------------------------------

describe('discoverPairs removal (PR change)', () => {
  it('discoverPairs is NOT exported from api.ts', async () => {
    // Dynamic import so TypeScript does not prevent the access at compile time.
    const apiModule = await import('../services/api');
    expect((apiModule as Record<string, unknown>).discoverPairs).toBeUndefined();
  });

  it('fetchPairs is still exported', async () => {
    const apiModule = await import('../services/api');
    expect(typeof (apiModule as Record<string, unknown>).fetchPairs).toBe('function');
  });

  it('updatePairs is still exported', async () => {
    const apiModule = await import('../services/api');
    expect(typeof (apiModule as Record<string, unknown>).updatePairs).toBe('function');
  });
});

// ---------------------------------------------------------------------------
// WalletRecommendation interface – broker_ticker required, t212_ticker optional
// ---------------------------------------------------------------------------

describe('WalletRecommendation interface shape', () => {
  it('requires broker_ticker and allows omitting t212_ticker', () => {
    const rec: WalletRecommendation = {
      ticker: 'AAPL',
      broker_ticker: 'AAPL',
      // t212_ticker intentionally omitted — should be optional
      category: 'coint',
      categories: ['coint'],
      pairs: [],
      sectors: ['Tech'],
      score: 120,
      max_abs_z_score: 2.1,
      estimated_cost_pct: 0.001,
      rank: 1,
      suggested_amount: 50.0,
      status: 'ready',
    };
    expect(rec.broker_ticker).toBe('AAPL');
    expect(rec.t212_ticker).toBeUndefined();
  });

  it('category can be coint | broken_eligible | manual_override', () => {
    const categories: WalletRecommendation['category'][] = [
      'coint',
      'broken_eligible',
      'manual_override',
    ];
    categories.forEach(category => {
      const rec: WalletRecommendation = {
        ticker: 'X', broker_ticker: 'X', category,
        categories: [category], pairs: [], sectors: [],
        score: 1, max_abs_z_score: 0, estimated_cost_pct: 0,
        rank: null, suggested_amount: 0, status: 'ready',
      };
      expect(rec.category).toBe(category);
    });
  });
});