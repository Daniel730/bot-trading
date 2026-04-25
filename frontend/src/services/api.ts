import { useEffect, useState } from 'react';

export interface PortfolioMetrics {
  daily_budget: number | null;
  total_invested: number | null;
  daily_profit: number | null;
  daily_usage_pct: number | null;
}

export interface Signal {
  ticker_a: string;
  ticker_b: string;
  z_score: number;
  status: string;
}

export interface TerminalMessage {
  type: 'BOT' | 'USER' | 'SYSTEM';
  text: string;
  timestamp: string;
  metadata?: any;
}

export interface TelemetryMessage {
  type: 'risk' | 'thought' | 'bot_state';
  timestamp: string;
  data: any;
}

export interface RiskTelemetry {
  risk_multiplier: number;
  max_drawdown_pct: number;
  volatility_status: 'NORMAL' | 'HIGH_VOLATILITY';
  l2_entropy: number;
}

export interface ThoughtTelemetry {
  agent_name: string;
  signal_id?: string;
  thought: string;
  verdict: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'VETO';
}

export interface RuntimeInfo {
  mode: 'LIVE' | 'PAPER' | 'DEV';
  paper_trading: boolean;
  dev_mode: boolean;
  live_capital_danger: boolean;
  region: string;
  bot_start_time: string;
}

export interface DashboardData {
  stage: string;
  details?: string;
  bot_start_time?: string;
  runtime?: RuntimeInfo;
  metrics?: PortfolioMetrics;
  market_regime?: {
    regime: string;
    confidence: number;
    features?: any;
  };
  global_accuracy?: number;
  active_signals?: Signal[];
  terminal_messages?: TerminalMessage[];
  timestamp: string;
}

export interface PairInfo {
  id: string;
  ticker_a: string;
  ticker_b: string;
  hedge_ratio: number | null;
  mean: number | null;
  std: number | null;
  is_cointegrated: boolean | null;
  sector: string;
  last_cointegration_check: string | null;
  last_z_score: number | null;
}

export interface PairConfigEntry {
  ticker_a: string;
  ticker_b: string;
}

export interface PairsResponse {
  active_pairs: PairInfo[];
  configured_pairs: PairConfigEntry[];
  crypto_test_pairs: PairConfigEntry[];
  dev_mode: boolean;
}

export interface OpenPosition {
  signal_id: string;
  ticker_a: string;
  ticker_b: string;
  side_a: 'BUY' | 'SELL';
  side_b: 'BUY' | 'SELL';
  qty_a: number;
  qty_b: number;
  entry_a: number;
  entry_b: number;
  current_a: number | null;
  current_b: number | null;
  cost_basis: number;
  current_value: number;
  pnl: number;
  opened_at: string | null;
}

const API_BASE = (window.location.port === '5173' || window.location.port === '3000')
  ? `${window.location.protocol}//${window.location.hostname}:8080` 
  : window.location.origin;

export const useDashboardStream = (token: string | null) => {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const url = new URL('/stream', API_BASE);
    if (token) url.searchParams.set('token', token);

    const eventSource = new EventSource(url.toString());

    eventSource.onmessage = (event) => {
      try {
        const parsedData = JSON.parse(event.data);
        setData(parsedData);
      } catch (err) {
        console.error('Failed to parse SSE data:', err);
      }
    };

    eventSource.onerror = (err) => {
      console.error('SSE Error:', err);
      setError('Connection to backend lost. Retrying...');
      eventSource.close();
    };

    return () => {
      eventSource.close();
    };
  }, [token]);

  return { data, error };
};

export const sendTerminalCommand = async (command: string, token: string | null, metadata?: any) => {
  const url = new URL('/api/terminal/command', API_BASE);
  if (token) url.searchParams.set('token', token);

  const response = await fetch(url.toString(), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command, metadata }),
  });

  if (!response.ok) {
    const errorData = await response.json();
    throw new Error(errorData.detail || 'Failed to send command');
  }

  return response.json();
};

export const fetchPairs = async (token: string | null): Promise<PairsResponse> => {
  const url = new URL('/api/pairs', API_BASE);
  if (token) url.searchParams.set('token', token);
  const response = await fetch(url.toString());
  if (!response.ok) throw new Error(`Failed to fetch pairs (${response.status})`);
  return response.json();
};

export const updatePairs = async (
  token: string | null,
  pairs: PairConfigEntry[],
  options: { applyNow?: boolean; cryptoPairs?: PairConfigEntry[] } = {},
): Promise<{ status: string; saved_pairs: number; reloaded: boolean; reload_error: string | null }> => {
  const url = new URL('/api/pairs', API_BASE);
  if (token) url.searchParams.set('token', token);
  const response = await fetch(url.toString(), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      pairs,
      crypto_pairs: options.cryptoPairs,
      apply_now: options.applyNow ?? true,
    }),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to update pairs (${response.status})`);
  }
  return response.json();
};

export const fetchOpenPositions = async (token: string | null): Promise<{ positions: OpenPosition[] }> => {
  const url = new URL('/api/positions', API_BASE);
  if (token) url.searchParams.set('token', token);
  const response = await fetch(url.toString());
  if (!response.ok) throw new Error(`Failed to fetch positions (${response.status})`);
  return response.json();
};
