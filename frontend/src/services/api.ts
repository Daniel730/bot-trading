import { useEffect, useState } from 'react';

export interface VenueMetrics {
  available_cash: number | null;
  pending_orders_value: number | null;
  spendable_cash: number | null;
  daily_budget: number | null;
  daily_used?: number | null;
  daily_usage_pct: number | null;
  daily_profit: number | null;
  total_revenue: number | null;
  total_invested: number | null;
}

export interface PortfolioMetrics {
  total_revenue: number | null;
  total_invested: number | null;
  daily_profit: number | null;
  available_cash: number | null;
  pending_orders_value: number | null;
  spendable_cash: number | null;
  daily_budget: number | null;
  daily_usage_pct: number | null;
  t212?: VenueMetrics;
  web3?: VenueMetrics;
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
  approval_threshold?: number;
  desired_bot_state?: string;
  last_control_action?: {
    action: string;
    actor: string;
    timestamp: string;
  } | null;
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
  is_crypto: boolean;
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

export interface T212WalletSyncOrder {
  ticker: string;
  amount: number;
  status: 'ok' | 'error';
  order_id?: string | null;
  message?: string | null;
}

export interface T212WalletSyncResponse {
  status: 'ok' | 'partial';
  mode: 'demo' | 'live';
  message: string;
  coint_pairs: number;
  candidate_tickers: string[];
  target_tickers: string[];
  skipped: { ticker: string; reason: string }[];
  budget: number;
  spendable_cash: number | null;
  effective_cash?: number | null;
  per_ticker_min?: number;
  per_ticker_max?: number;
  orders: T212WalletSyncOrder[];
  failures: number;
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

export interface TradeLeg {
  ticker: string;
  side: 'BUY' | 'SELL';
  quantity: number;
  price: number;
  fee: number;
  status: string;
  timestamp: string | null;
}

export interface TradeHistoryItem {
  signal_id: string;
  pair: string;
  venue: string;
  status: string;
  opened_at: string | null;
  notional: number;
  pnl: number | null;
  legs: TradeLeg[];
}

export interface TradeHistoryResponse {
  items: TradeHistoryItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface SummaryResponse {
  current_balance: number | null;
  capital_deployed: number | null;
  profit_today: number | null;
  trades_today: number;
  win_rate: number;
  wins: number;
  losses: number;
  closed_trades: number;
  system_uptime_seconds: number | null;
  system_uptime_human: string;
  bot_status: string;
  stage: string;
  cpu_pct: number | null;
  memory_pct: number | null;
  open_signals: number;
  open_positions: number;
  mode: string;
}

export interface ChartPoint {
  timestamp: string;
  value?: number;
  daily?: number;
  wins?: number;
  losses?: number;
}

export interface ChartResponse {
  metric: string;
  points: ChartPoint[];
}

export interface HealthPoint {
  timestamp: string;
  cpu_pct: number | null;
  rss_mb: number | null;
  vms_mb: number | null;
  threads: number | null;
  net_sent_mb: number | null;
  net_recv_mb: number | null;
  system_memory_pct: number | null;
  uptime_seconds: number | null;
  hostname: string;
}

export interface HealthResponse {
  status: string;
  current: HealthPoint;
  history: HealthPoint[];
}

export interface LogEvent {
  level: string;
  source: string;
  message: string;
  metadata?: any;
  timestamp: string;
}

export interface LogsResponse {
  file: string | null;
  lines: string[];
  events: LogEvent[];
}

export interface ConfigItem {
  key: string;
  value: string | number | boolean | null;
  type: 'float' | 'int' | 'bool' | 'str';
  sensitive: boolean;
}

export interface TwoFactorStatus {
  enabled: boolean;
  pending_setup: boolean;
  backup_codes_remaining: number;
}

export interface ConfigAuditEntry {
  actor: string;
  key: string;
  old_value: any;
  new_value: any;
  requires_2fa: boolean;
  timestamp: string;
}

export interface ConfigResponse {
  items: ConfigItem[];
  two_factor: TwoFactorStatus;
  audit_log: ConfigAuditEntry[];
}

export interface TwoFactorInitiateResponse {
  enabled: boolean;
  secret: string;
  otpauth_url: string;
  backup_codes: string[];
}

export interface AuthSession {
  status: 'ok';
  session_token: string;
  expires_at: string;
  actor: string;
  two_factor: TwoFactorStatus;
}

export interface AuthChallenge {
  status: 'pending';
  challenge_id: string;
  expires_at: string;
  message?: string;
  two_factor: TwoFactorStatus;
}

export type AuthLoginResponse = AuthSession | AuthChallenge;

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

const getApiBase = () => {
  if (import.meta.env.VITE_API_URL) return import.meta.env.VITE_API_URL;
  const isLocalHost = ['localhost', '127.0.0.1', '::1'].includes(window.location.hostname);
  const isFrontendPort = window.location.port === '3000';
  if ((isLocalHost || isFrontendPort) && window.location.port !== '8080') {
    return `${window.location.protocol}//${window.location.hostname}:8080`;
  }
  return window.location.origin;
};

const API_BASE = getApiBase();
const DEFAULT_REQUEST_TIMEOUT_MS = 15_000;
const configuredTimeout = Number(import.meta.env.VITE_API_TIMEOUT_MS);
const REQUEST_TIMEOUT_MS = Number.isFinite(configuredTimeout) && configuredTimeout > 0
  ? configuredTimeout
  : DEFAULT_REQUEST_TIMEOUT_MS;

const apiUrl = (path: string) => new URL(path, API_BASE);

const authHeaders = (token: string | null, sessionToken?: string | null, initHeaders?: HeadersInit) => {
  const headers = new Headers(initHeaders);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (sessionToken) headers.set('X-Dashboard-Session', sessionToken);
  return headers;
};

async function fetchWithTimeout(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const callerSignal = init?.signal;
  const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  const abortFromCaller = () => controller.abort();
  if (callerSignal?.aborted) {
    controller.abort();
  } else {
    callerSignal?.addEventListener('abort', abortFromCaller, { once: true });
  }

  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new Error(`Backend request timed out after ${Math.round(REQUEST_TIMEOUT_MS / 1000)}s`);
    }
    throw err;
  } finally {
    window.clearTimeout(timeoutId);
    callerSignal?.removeEventListener('abort', abortFromCaller);
  }
}

async function requestJson<T>(
  path: string,
  token: string | null,
  init?: RequestInit,
  sessionToken?: string | null,
): Promise<T> {
  const response = await fetchWithTimeout(apiUrl(path), {
    ...init,
    headers: authHeaders(token, sessionToken, init?.headers),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new ApiError(response.status, errorData.detail || `Request failed (${response.status})`, errorData);
  }
  return response.json();
}

export const useDashboardStream = (token: string | null, sessionToken?: string | null) => {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!sessionToken) return;
    const controller = new AbortController();
    let retryCount = 0;

    const connect = async () => {
      while (!controller.signal.aborted) {
        try {
          const response = await fetch(apiUrl('/stream').toString(), {
            headers: authHeaders(token, sessionToken),
            signal: controller.signal,
          });
          if (!response.ok || !response.body) throw new Error(`SSE failed (${response.status})`);

          retryCount = 0;
          setError(null);
          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let buffer = '';

          while (!controller.signal.aborted) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const events = buffer.split(/\r?\n\r?\n/);
            buffer = events.pop() || '';

            for (const event of events) {
              const dataLines = event
                .split(/\r?\n/)
                .filter((line) => line.startsWith('data:'))
                .map((line) => line.slice(5).trimStart());
              if (dataLines.length === 0) continue;
              try {
                setData(JSON.parse(dataLines.join('\n')));
                setError(null);
              } catch (err) {
                console.error('Failed to parse SSE data:', err);
              }
            }
          }
        } catch (err) {
          if (controller.signal.aborted) return;
          console.error('SSE Error:', err);
          setError('Connection to backend lost. Retrying...');
          const delay = Math.min(1000 * Math.pow(2, retryCount), 30000);
          retryCount += 1;
          await new Promise((resolve) => window.setTimeout(resolve, delay));
        }
      }
    };

    void connect();

    return () => {
      controller.abort();
    };
  }, [token, sessionToken]);

  return { data, error };
};

export const login = async (securityToken: string, otpToken?: string): Promise<AuthLoginResponse> =>
  requestJson<AuthLoginResponse>('/api/auth/login/', null, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ security_token: securityToken, otp_token: otpToken || undefined, actor: 'dashboard' }),
  });

export const completeLogin = async (challengeId: string): Promise<AuthLoginResponse> =>
  requestJson<AuthLoginResponse>('/api/auth/login/complete/', null, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ challenge_id: challengeId }),
  });

export const logout = async (token: string | null, sessionToken: string | null) =>
  requestJson<{ status: string }>('/api/auth/logout', token, { method: 'POST' }, sessionToken);

export const sendTerminalCommand = async (command: string, token: string | null, sessionToken: string | null, metadata?: any) =>
  requestJson<{ status: string; message: string }>('/api/terminal/command', token, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command, metadata }),
  }, sessionToken);

export const fetchPairs = async (token: string | null, sessionToken?: string | null): Promise<PairsResponse> =>
  requestJson<PairsResponse>('/api/pairs', token, undefined, sessionToken);

export const updatePairs = async (
  token: string | null,
  pairs: PairConfigEntry[],
  options: { applyNow?: boolean; cryptoPairs?: PairConfigEntry[] } = {},
  sessionToken?: string | null,
): Promise<{ status: string; saved_pairs: number; reloaded: boolean; reload_error: string | null }> =>
  requestJson('/api/pairs', token, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      pairs,
      crypto_pairs: options.cryptoPairs,
      apply_now: options.applyNow ?? true,
    }),
  }, sessionToken);

export const syncT212Wallet = async (
  token: string | null,
  sessionToken: string | null,
  budget: number,
): Promise<T212WalletSyncResponse> =>
  requestJson('/api/t212/wallet/sync', token, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ budget }),
  }, sessionToken);

export const fetchOpenPositions = async (token: string | null, sessionToken?: string | null): Promise<{ positions: OpenPosition[] }> =>
  requestJson('/api/positions', token, undefined, sessionToken);

export interface SettingsData {
  approval_threshold: number;
}

export const fetchSettings = async (token: string | null, sessionToken?: string | null): Promise<SettingsData> =>
  requestJson('/api/settings', token, undefined, sessionToken);

export const updateSettings = async (token: string | null, sessionToken: string | null, approval_threshold: number) =>
  requestJson<{ status: string; approval_threshold: number }>('/api/settings', token, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approval_threshold }),
  }, sessionToken);

export const fetchSummary = async (token: string | null, sessionToken?: string | null): Promise<SummaryResponse> =>
  requestJson('/api/stats/summary', token, undefined, sessionToken);

export const fetchTradeHistory = async (
  token: string | null,
  sessionToken: string | null,
  params: { page?: number; pageSize?: number; search?: string; status?: string; venue?: string } = {},
): Promise<TradeHistoryResponse> => {
  const url = apiUrl('/api/stats/trades');
  if (params.page) url.searchParams.set('page', String(params.page));
  if (params.pageSize) url.searchParams.set('page_size', String(params.pageSize));
  if (params.search) url.searchParams.set('search', params.search);
  if (params.status) url.searchParams.set('status', params.status);
  if (params.venue) url.searchParams.set('venue', params.venue);
  const response = await fetchWithTimeout(url, {
    headers: authHeaders(token, sessionToken),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new ApiError(response.status, errorData.detail || `Failed to fetch trade history (${response.status})`, errorData);
  }
  return response.json();
};

export const fetchChartMetric = async (token: string | null, sessionToken: string | null, metric: string): Promise<ChartResponse> =>
  requestJson(`/api/stats/charts/${metric}`, token, undefined, sessionToken);

export const fetchSystemHealth = async (token: string | null, sessionToken?: string | null): Promise<HealthResponse> =>
  requestJson('/api/system/health', token, undefined, sessionToken);

export const fetchSystemLogs = async (token: string | null, sessionToken: string | null, limit = 100): Promise<LogsResponse> =>
  requestJson(`/api/system/logs?limit=${limit}`, token, undefined, sessionToken);

export const controlBot = async (
  token: string | null,
  sessionToken: string | null,
  action: 'start' | 'stop' | 'restart',
  actor = 'dashboard',
): Promise<{ status: string; requested_state: string; action: string }> =>
  requestJson('/api/bot/control', token, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, actor }),
  }, sessionToken);

export const fetchConfig = async (token: string | null, sessionToken?: string | null): Promise<ConfigResponse> =>
  requestJson('/api/config', token, undefined, sessionToken);

export const updateConfig = async (
  token: string | null,
  sessionToken: string | null,
  updates: Record<string, string | number | boolean>,
  actor = 'dashboard',
  otpToken?: string,
): Promise<ConfigResponse> =>
  requestJson('/api/config/update', token, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actor, updates, otp_token: otpToken }),
  }, sessionToken);

export const initiateTwoFactor = async (token: string | null, sessionToken: string | null): Promise<TwoFactorInitiateResponse> =>
  requestJson('/api/auth/2fa/initiate', token, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  }, sessionToken);

export const verifyTwoFactor = async (token: string | null, sessionToken: string | null, code: string) =>
  requestJson<{ status: string; verified?: boolean; two_factor: TwoFactorStatus }>('/api/auth/2fa/verify', token, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token: code }),
  }, sessionToken);
