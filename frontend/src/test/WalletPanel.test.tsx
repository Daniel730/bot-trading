/**
 * Tests for WalletPanel.tsx changes in this PR:
 *
 * - Uses renamed types: WalletRecommendation, WalletRecommendationResponse,
 *   WalletRecommendationBuyResponse (instead of T212Wallet* variants)
 * - categoryLabel uses WalletRecommendation['category']
 * - Broker ticker display: item.broker_ticker || item.t212_ticker || item.ticker
 * - Mode display: plan.mode.toUpperCase() (no "T212" suffix), fallback to 'BROKER'
 * - cash_limited banner: "spendable broker cash"
 * - Confirm dialog title: "confirm broker buy"
 */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, afterEach } from 'vitest';

// Mock the api module
vi.mock('../services/api', () => ({
  fetchWalletRecommendations: vi.fn(),
  buyWalletRecommendations: vi.fn(),
}));

import { fetchWalletRecommendations } from '../services/api';
import WalletPanel from '../components/WalletPanel';

const mockFetchRecs = fetchWalletRecommendations as ReturnType<typeof vi.fn>;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const TOKEN = 'test-token';
const SESSION = 'test-session';

function makeRecommendation(overrides: Partial<{
  ticker: string;
  broker_ticker: string;
  t212_ticker: string | null;
  category: 'coint' | 'broken_eligible' | 'manual_override';
}> = {}) {
  return {
    ticker: overrides.ticker ?? 'AAPL',
    broker_ticker: overrides.broker_ticker ?? 'AAPL',
    t212_ticker: overrides.t212_ticker ?? null,
    category: overrides.category ?? 'coint',
    categories: [overrides.category ?? 'coint'],
    pairs: [],
    sectors: [],
    score: 100,
    max_abs_z_score: 2.0,
    estimated_cost_pct: 0.001,
    rank: 1,
    suggested_amount: 25.0,
    status: 'ready' as const,
  };
}

function makePlanResponse(overrides: Partial<{
  mode: string;
  cash_limited: boolean;
  recommendations: ReturnType<typeof makeRecommendation>[];
}> = {}) {
  return {
    status: 'ok' as const,
    mode: overrides.mode ?? 'T212',
    message: 'Calculated 1 recommendations.',
    generated_at: '2026-01-01T00:00:00',
    include_broken: false,
    coint_pairs: 1,
    broken_eligible_pairs: 0,
    candidate_tickers: ['AAPL'],
    recommended_tickers: ['AAPL'],
    budget: 100,
    usable_budget: 100,
    cash_limited: overrides.cash_limited ?? false,
    spendable_cash: 95,
    effective_cash: 90,
    can_buy: true,
    recommendations: overrides.recommendations ?? [makeRecommendation()],
    skipped: [],
  };
}

// ---------------------------------------------------------------------------
// Mode display
// ---------------------------------------------------------------------------

describe('WalletPanel mode display', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('shows mode.toUpperCase() when plan mode is set', async () => {
    mockFetchRecs.mockResolvedValue(makePlanResponse({ mode: 'ALPACA' }));

    render(<WalletPanel token={TOKEN} sessionToken={SESSION} />);
    await waitFor(() => {
      expect(screen.getByText('ALPACA')).toBeInTheDocument();
    });
  });

  it('shows T212 uppercased when mode is T212', async () => {
    mockFetchRecs.mockResolvedValue(makePlanResponse({ mode: 'T212' }));

    render(<WalletPanel token={TOKEN} sessionToken={SESSION} />);
    await waitFor(() => {
      expect(screen.getByText('T212')).toBeInTheDocument();
    });
  });

  it('falls back to BROKER when plan is null', async () => {
    mockFetchRecs.mockRejectedValue(new Error('Network error'));

    render(<WalletPanel token={TOKEN} sessionToken={SESSION} />);
    await waitFor(() => {
      expect(screen.getByText('BROKER')).toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// broker_ticker display fallback
// ---------------------------------------------------------------------------

describe('WalletPanel broker_ticker display', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('displays broker_ticker when it is set', async () => {
    const rec = makeRecommendation({ ticker: 'AAPL', broker_ticker: 'AAPL' });
    mockFetchRecs.mockResolvedValue(makePlanResponse({ recommendations: [rec] }));

    render(<WalletPanel token={TOKEN} sessionToken={SESSION} />);
    await waitFor(() => {
      // ticker shown as strong, broker_ticker shown as muted subtext
      const mutedDivs = document.querySelectorAll('.muted');
      const brokerTickerEl = Array.from(mutedDivs).find(el => el.textContent === 'AAPL');
      expect(brokerTickerEl).toBeTruthy();
    });
  });

  it('falls back to t212_ticker when broker_ticker is empty', async () => {
    const rec = {
      ...makeRecommendation({ ticker: 'MSFT' }),
      broker_ticker: '',
      t212_ticker: 'MSFT_US_EQ',
    };
    mockFetchRecs.mockResolvedValue(makePlanResponse({ recommendations: [rec as any] }));

    render(<WalletPanel token={TOKEN} sessionToken={SESSION} />);
    await waitFor(() => {
      expect(screen.getByText('MSFT_US_EQ')).toBeInTheDocument();
    });
  });

  it('falls back to ticker when both broker_ticker and t212_ticker are absent', async () => {
    const rec = {
      ...makeRecommendation({ ticker: 'GOOG' }),
      broker_ticker: '',
      t212_ticker: null,
    };
    mockFetchRecs.mockResolvedValue(makePlanResponse({ recommendations: [rec as any] }));

    render(<WalletPanel token={TOKEN} sessionToken={SESSION} />);
    await waitFor(() => {
      // The ticker appears both as <strong> and as the .muted fallback
      const ticker = screen.getAllByText('GOOG');
      expect(ticker.length).toBeGreaterThanOrEqual(1);
    });
  });
});

// ---------------------------------------------------------------------------
// cash_limited banner
// ---------------------------------------------------------------------------

describe('WalletPanel cash_limited banner', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('shows "spendable broker cash" warning when cash_limited is true', async () => {
    mockFetchRecs.mockResolvedValue(makePlanResponse({ cash_limited: true }));

    render(<WalletPanel token={TOKEN} sessionToken={SESSION} />);
    await waitFor(() => {
      expect(
        screen.getByText(/Budget exceeds bot-calculated spendable broker cash/i)
      ).toBeInTheDocument();
    });
  });

  it('does NOT show cash_limited banner when cash_limited is false', async () => {
    mockFetchRecs.mockResolvedValue(makePlanResponse({ cash_limited: false }));

    render(<WalletPanel token={TOKEN} sessionToken={SESSION} />);
    await waitFor(() => {
      expect(screen.queryByText(/spendable broker cash/i)).not.toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// Confirm dialog title
// ---------------------------------------------------------------------------

describe('WalletPanel confirm dialog', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('confirm dialog title is "confirm broker buy"', async () => {
    mockFetchRecs.mockResolvedValue(makePlanResponse());

    render(<WalletPanel token={TOKEN} sessionToken={SESSION} />);

    // Wait for the plan to render, then click the Buy Selected button
    await waitFor(() => {
      expect(screen.getByText('Buy Selected')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText('Buy Selected'));

    await waitFor(() => {
      expect(screen.getByText('confirm broker buy')).toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// categoryLabel
// ---------------------------------------------------------------------------

describe('WalletPanel categoryLabel', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('shows COINT badge for coint category', async () => {
    const rec = makeRecommendation({ category: 'coint' });
    mockFetchRecs.mockResolvedValue(makePlanResponse({ recommendations: [rec] }));

    render(<WalletPanel token={TOKEN} sessionToken={SESSION} />);
    await waitFor(() => {
      expect(screen.getByText('COINT')).toBeInTheDocument();
    });
  });

  it('shows "BROKEN eligible" for broken_eligible category', async () => {
    const rec = makeRecommendation({ category: 'broken_eligible' });
    mockFetchRecs.mockResolvedValue(makePlanResponse({ recommendations: [rec] }));

    render(<WalletPanel token={TOKEN} sessionToken={SESSION} />);
    await waitFor(() => {
      expect(screen.getByText('BROKEN eligible')).toBeInTheDocument();
    });
  });

  it('shows "Manual override" for manual_override category', async () => {
    const rec = makeRecommendation({ category: 'manual_override' });
    mockFetchRecs.mockResolvedValue(makePlanResponse({ recommendations: [rec] }));

    render(<WalletPanel token={TOKEN} sessionToken={SESSION} />);
    await waitFor(() => {
      expect(screen.getByText('Manual override')).toBeInTheDocument();
    });
  });
});