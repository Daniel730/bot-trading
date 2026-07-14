import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, afterEach } from 'vitest';

vi.mock('../services/api', () => ({
  fetchBrokerPositions: vi.fn(),
}));

import { fetchBrokerPositions } from '../services/api';
import BrokerPositionsPanel from './BrokerPositionsPanel';

const mockFetch = fetchBrokerPositions as ReturnType<typeof vi.fn>;

afterEach(() => {
  vi.clearAllMocks();
});

describe('BrokerPositionsPanel', () => {
  it('renders broker holdings with computed P&L', async () => {
    mockFetch.mockResolvedValue({
      provider: 'ALPACA',
      total_market_value: 104.95,
      positions: [
        {
          ticker: 'BTC-USD',
          quantity: 0.00208,
          avg_price: 60000,
          current_price: 62000,
          market_value: 128.96,
          unrealized_pl: 4.16,
          unrealized_pl_pct: 0.0333,
        },
      ],
    });

    render(<BrokerPositionsPanel token="t" sessionToken="s" />);

    expect(await screen.findByText('BTC-USD')).toBeInTheDocument();
    expect(screen.getByText(/ALPACA/)).toBeInTheDocument();
    expect(screen.getByText(/\$4\.16/)).toBeInTheDocument();
    expect(screen.getByText(/3\.33%/)).toBeInTheDocument();
  });

  it('shows an empty state when there are no holdings', async () => {
    mockFetch.mockResolvedValue({ provider: 'ALPACA', total_market_value: 0, positions: [] });
    render(<BrokerPositionsPanel token="t" sessionToken="s" />);
    expect(await screen.findByText('No broker holdings')).toBeInTheDocument();
  });

  it('surfaces backend errors instead of silently showing empty', async () => {
    mockFetch.mockResolvedValue({ provider: 'ALPACA', total_market_value: 0, positions: [], error: 'broker unreachable' });
    render(<BrokerPositionsPanel token="t" sessionToken="s" />);
    await waitFor(() =>
      expect(screen.getByText(/Could not load broker holdings: broker unreachable/)).toBeInTheDocument(),
    );
  });
});
