import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  buyWalletRecommendations,
  fetchWalletRecommendations,
  syncWallet,
  type WalletRecommendation,
  type WalletSyncOrder,
} from '../services/api';

const makeFetchMock = (payload: unknown) =>
  vi.fn().mockResolvedValue({
    ok: true,
    json: async () => payload,
    headers: { get: () => 'application/json' },
  });

afterEach(() => {
  vi.restoreAllMocks();
});

describe('wallet API types', () => {
  it('uses broker_ticker without legacy ticker aliases', () => {
    const order: WalletSyncOrder = {
      ticker: 'AAPL',
      amount: 50,
      status: 'ok',
      broker_ticker: 'AAPL',
    };
    const rec: WalletRecommendation = {
      ticker: 'AAPL',
      broker_ticker: 'AAPL',
      category: 'coint',
      categories: ['coint'],
      pairs: [],
      sectors: [],
      score: 1,
      max_abs_z_score: 2,
      estimated_cost_pct: 0,
      rank: 1,
      suggested_amount: 50,
      status: 'ready',
    };

    expect(order.broker_ticker).toBe('AAPL');
    expect(rec.broker_ticker).toBe('AAPL');
  });
});

describe('wallet API routes', () => {
  it('syncWallet posts to the generic wallet route', async () => {
    const fetchMock = makeFetchMock({
      status: 'ok',
      mode: 'ALPACA',
      message: '',
      coint_pairs: 0,
      candidate_tickers: [],
      target_tickers: [],
      skipped: [],
      budget: 0,
      spendable_cash: 0,
      orders: [],
      failures: 0,
    });
    vi.stubGlobal('fetch', fetchMock);

    await syncWallet(null, null, 10);

    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/wallet/sync');
    expect(String(fetchMock.mock.calls[0][0])).not.toContain('/api/t212/');
  });

  it('fetchWalletRecommendations uses the generic recommendations route', async () => {
    const fetchMock = makeFetchMock({
      status: 'ok',
      mode: 'ALPACA',
      message: '',
      generated_at: '',
      include_broken: false,
      coint_pairs: 0,
      broken_eligible_pairs: 0,
      candidate_tickers: [],
      recommended_tickers: [],
      budget: 0,
      usable_budget: 0,
      cash_limited: false,
      spendable_cash: null,
      effective_cash: null,
      can_buy: false,
      recommendations: [],
      skipped: [],
    });
    vi.stubGlobal('fetch', fetchMock);

    await fetchWalletRecommendations(null, null, { budget: 10 });

    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/wallet/recommendations');
    expect(String(fetchMock.mock.calls[0][0])).not.toContain('/api/t212/');
  });

  it('buyWalletRecommendations posts to the generic buy route', async () => {
    const fetchMock = makeFetchMock({
      status: 'ok',
      mode: 'ALPACA',
      message: '',
      budget: 0,
      target_tickers: [],
      recommendations: [],
      skipped: [],
      orders: [],
      failures: 0,
    });
    vi.stubGlobal('fetch', fetchMock);

    await buyWalletRecommendations(null, null, { budget: 10 });

    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/wallet/recommendations/buy');
    expect(String(fetchMock.mock.calls[0][0])).not.toContain('/api/t212/');
  });
});
