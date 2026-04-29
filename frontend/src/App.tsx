import React, { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  BarChart3,
  Bot,
  Cpu,
  Gauge,
  History,
  Layers,
  LogOut,
  Play,
  RefreshCw,
  Search,
  Settings as SettingsIcon,
  Shield,
  Square,
} from 'lucide-react';
import './App.css';
import PairsPanel from './components/PairsPanel';
import {
  type ChartPoint,
  type ChartResponse,
  type ConfigResponse,
  type HealthResponse,
  type LogsResponse,
  type OpenPosition,
  type SummaryResponse,
  type TerminalMessage,
  type TradeHistoryResponse,
  type TwoFactorInitiateResponse,
  completeLogin,
  controlBot,
  fetchChartMetric,
  fetchConfig,
  fetchOpenPositions,
  fetchSummary,
  fetchSystemHealth,
  fetchSystemLogs,
  fetchTradeHistory,
  initiateTwoFactor,
  login,
  logout,
  updateConfig,
  useDashboardStream,
  verifyTwoFactor,
} from './services/api';
import { useTelemetry } from './hooks/useTelemetry';

type Page = 'overview' | 'pairs' | 'analytics' | 'trades' | 'control' | 'settings' | 'health';

const NAV_ITEMS: { key: Page; label: string; icon: React.ReactNode }[] = [
  { key: 'overview', label: 'Overview', icon: <Gauge size={16} /> },
  { key: 'pairs', label: 'Pairs', icon: <Layers size={16} /> },
  { key: 'analytics', label: 'Analytics', icon: <BarChart3 size={16} /> },
  { key: 'trades', label: 'Trade History', icon: <History size={16} /> },
  { key: 'control', label: 'Bot Control', icon: <Bot size={16} /> },
  { key: 'settings', label: 'Settings', icon: <SettingsIcon size={16} /> },
  { key: 'health', label: 'System Health', icon: <Cpu size={16} /> },
];

function formatCurrency(value: number | null | undefined) {
  if (value === null || value === undefined) return '—';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(value);
}

function formatPercent(value: number | null | undefined, scale = 100) {
  if (value === null || value === undefined) return '—';
  return `${(value * scale).toFixed(scale === 100 ? 1 : 0)}%`;
}

function formatCompact(value: number | null | undefined, suffix = '') {
  if (value === null || value === undefined) return '—';
  return `${value.toFixed(1)}${suffix}`;
}

function formatDateTime(value?: string | null) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function getTrendClass(value: number | null | undefined) {
  if (value === null || value === undefined) return '';
  if (value > 0) return 'positive';
  if (value < 0) return 'negative';
  return '';
}

function sparklinePath(values: number[], width: number, height: number) {
  if (!values.length) return '';
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  return values
    .map((value, index) => {
      const x = (index / Math.max(values.length - 1, 1)) * width;
      const y = height - ((value - min) / range) * height;
      return `${index === 0 ? 'M' : 'L'} ${x} ${y}`;
    })
    .join(' ');
}

function LineMiniChart({ points, color }: { points: ChartPoint[]; color: string }) {
  const values = points.map((point) => point.value ?? 0);
  const path = sparklinePath(values, 300, 90);
  return (
    <svg viewBox="0 0 300 90" className="mini-chart">
      <path d={path} fill="none" stroke={color} strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

function DualBarChart({ points }: { points: ChartPoint[] }) {
  const max = Math.max(1, ...points.flatMap((point) => [point.wins ?? 0, point.losses ?? 0]));
  return (
    <div className="dual-bars">
      {points.slice(-12).map((point) => (
        <div key={point.timestamp} className="dual-bar-item">
          <div className="dual-bar-stack">
            <div className="dual-bar win" style={{ height: `${((point.wins ?? 0) / max) * 100}%` }} />
            <div className="dual-bar loss" style={{ height: `${((point.losses ?? 0) / max) * 100}%` }} />
          </div>
          <span>{point.timestamp.slice(5)}</span>
        </div>
      ))}
    </div>
  );
}

function SectionHeader({ title, subtitle, action }: { title: string; subtitle?: string; action?: React.ReactNode }) {
  return (
    <div className="section-header">
      <div>
        <h2>{title}</h2>
        {subtitle ? <p>{subtitle}</p> : null}
      </div>
      {action}
    </div>
  );
}

function App() {
  const [securityToken, setSecurityToken] = useState('');
  const [sessionToken, setSessionToken] = useState('');
  const [loginToken, setLoginToken] = useState('');
  const [loginOtp, setLoginOtp] = useState('');
  const [loginChallengeId, setLoginChallengeId] = useState<string | null>(null);
  const [loginNotice, setLoginNotice] = useState<string | null>(null);
  const [loginError, setLoginError] = useState<string | null>(null);

  const isAuthenticated = Boolean(securityToken && sessionToken);
  const { data, error } = useDashboardStream(isAuthenticated ? securityToken : null, sessionToken);
  const { isConnected, risk, thoughts, botState } = useTelemetry(isAuthenticated ? securityToken : null, sessionToken);

  const [page, setPage] = useState<Page>('overview');
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [profitChart, setProfitChart] = useState<ChartResponse | null>(null);
  const [winLossChart, setWinLossChart] = useState<ChartResponse | null>(null);
  const [tradeHistory, setTradeHistory] = useState<TradeHistoryResponse | null>(null);
  const [tradeSearch, setTradeSearch] = useState('');
  const [tradeStatus, setTradeStatus] = useState('');
  const [tradeVenue, setTradeVenue] = useState('');
  const [tradePage, setTradePage] = useState(1);
  const [positions, setPositions] = useState<OpenPosition[]>([]);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [logs, setLogs] = useState<LogsResponse | null>(null);
  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [configForm, setConfigForm] = useState<Record<string, string>>({});
  const [otpToken, setOtpToken] = useState('');
  const [twoFactorSetup, setTwoFactorSetup] = useState<TwoFactorInitiateResponse | null>(null);
  const [twoFactorCode, setTwoFactorCode] = useState('');
  const [systemMessage, setSystemMessage] = useState<string | null>(null);
  const [systemError, setSystemError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  useEffect(() => {
    const currentUrl = new URL(window.location.href);
    if (!currentUrl.searchParams.has('token') && !currentUrl.searchParams.has('session')) return;
    currentUrl.searchParams.delete('token');
    currentUrl.searchParams.delete('session');
    window.history.replaceState({}, document.title, currentUrl.toString());
  }, []);

  const refreshDashboard = async () => {
    if (!isAuthenticated) return;
    try {
      const [summaryData, profitData, winLossData, positionsData] = await Promise.all([
        fetchSummary(securityToken, sessionToken),
        fetchChartMetric(securityToken, sessionToken, 'cumulative_profit'),
        fetchChartMetric(securityToken, sessionToken, 'win_loss'),
        fetchOpenPositions(securityToken, sessionToken),
      ]);
      setSummary(summaryData);
      setProfitChart(profitData);
      setWinLossChart(winLossData);
      setPositions(positionsData.positions);
    } catch (err: any) {
      setSystemError(err.message || 'Failed to load dashboard data.');
    }
  };

  const refreshTradeHistory = async () => {
    if (!isAuthenticated) return;
    try {
      const history = await fetchTradeHistory(securityToken, sessionToken, {
        page: tradePage,
        pageSize: 12,
        search: tradeSearch || undefined,
        status: tradeStatus || undefined,
        venue: tradeVenue || undefined,
      });
      setTradeHistory(history);
    } catch (err: any) {
      setSystemError(err.message || 'Failed to load trade history.');
    }
  };

  const refreshHealth = async () => {
    if (!isAuthenticated) return;
    const [healthResult, logsResult] = await Promise.allSettled([
      fetchSystemHealth(securityToken, sessionToken),
      fetchSystemLogs(securityToken, sessionToken, 80),
    ]);

    if (healthResult.status === 'fulfilled') {
      const healthData = healthResult.value;
      setHealth(healthData);
    } else {
      setSystemError(healthResult.reason?.message || 'Failed to load system health.');
    }

    if (logsResult.status === 'fulfilled') {
      setLogs(logsResult.value);
    } else if (healthResult.status === 'fulfilled') {
      setLogs({ file: null, lines: [], events: [] });
    }
  };

  const refreshConfig = async () => {
    if (!isAuthenticated) return;
    try {
      const configData = await fetchConfig(securityToken, sessionToken);
      setConfig(configData);
      setConfigForm(
        Object.fromEntries(configData.items.map((item) => [item.key, String(item.value)])),
      );
    } catch (err: any) {
      setSystemError(err.message || 'Failed to load config.');
    }
  };

  useEffect(() => {
    refreshDashboard();
    refreshTradeHistory();
    refreshHealth();
    refreshConfig();
    const interval = window.setInterval(() => {
      refreshDashboard();
      refreshHealth();
    }, 15000);
    return () => window.clearInterval(interval);
    // Dashboard refresh callbacks intentionally read the latest token/form state.
    // They are triggered by the explicit dependency keys below to avoid resetting
    // the polling interval on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated, securityToken, sessionToken]);

  useEffect(() => {
    refreshTradeHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tradePage, tradeStatus, tradeVenue]);

  const recentThoughts = useMemo(() => [...thoughts].reverse().slice(0, 6), [thoughts]);
  const terminalMessages = useMemo(
    () => (data?.terminal_messages ?? []).slice(-8).reverse(),
    [data?.terminal_messages],
  );
  const currentMode = data?.runtime?.mode ?? summary?.mode ?? '—';
  const currentStage = data?.stage ?? summary?.stage ?? botState ?? 'Initializing';
  const currentBotState = data?.runtime?.desired_bot_state ?? summary?.bot_status ?? 'RUNNING';

  const handleBotAction = async (action: 'start' | 'stop' | 'restart') => {
    setIsBusy(true);
    setSystemError(null);
    setSystemMessage(null);
    try {
      const result = await controlBot(securityToken, sessionToken, action);
      setSystemMessage(`Bot ${result.action} request accepted.`);
      await refreshDashboard();
    } catch (err: any) {
      setSystemError(err.message || `Failed to ${action} bot.`);
    } finally {
      setIsBusy(false);
    }
  };

  const handleSaveConfig = async () => {
    if (!config) return;
    setIsBusy(true);
    setSystemError(null);
    setSystemMessage(null);
    try {
      const updates = Object.fromEntries(
        config.items
          .filter((item) => configForm[item.key] !== String(item.value))
          .map((item) => [item.key, configForm[item.key]]),
      );
      if (!Object.keys(updates).length) {
        setSystemMessage('No settings changed.');
        return;
      }
      const response = await updateConfig(securityToken, sessionToken, updates, 'dashboard', otpToken || undefined);
      setConfig(response);
      setConfigForm(Object.fromEntries(response.items.map((item) => [item.key, String(item.value)])));
      setOtpToken('');
      setSystemMessage('Configuration updated.');
    } catch (err: any) {
      setSystemError(err.message || 'Failed to update configuration.');
    } finally {
      setIsBusy(false);
    }
  };

  const handleInitiate2FA = async () => {
    setIsBusy(true);
    setSystemError(null);
    setSystemMessage(null);
    try {
      const result = await initiateTwoFactor(securityToken, sessionToken);
      setTwoFactorSetup(result);
      setSystemMessage('2FA setup secret generated. Verify with your authenticator code to enable it.');
    } catch (err: any) {
      setSystemError(err.message || 'Failed to initiate 2FA.');
    } finally {
      setIsBusy(false);
    }
  };

  const handleVerify2FA = async () => {
    setIsBusy(true);
    setSystemError(null);
    setSystemMessage(null);
    try {
      await verifyTwoFactor(securityToken, sessionToken, twoFactorCode);
      setTwoFactorCode('');
      setTwoFactorSetup(null);
      await refreshConfig();
      setSystemMessage('2FA verification succeeded.');
    } catch (err: any) {
      setSystemError(err.message || 'Invalid 2FA code.');
    } finally {
      setIsBusy(false);
    }
  };

  const handleLogin = async (event: React.FormEvent) => {
    event.preventDefault();
    setIsBusy(true);
    setLoginError(null);
    setSystemError(null);
    try {
      const result = await login(loginToken.trim(), loginOtp.trim() || undefined);
      if (result.status === 'pending') {
        setLoginChallengeId(result.challenge_id);
        setLoginNotice('Approval notification sent. Waiting for confirmation.');
        return;
      }
      setSecurityToken(loginToken.trim());
      setSessionToken(result.session_token);
      setLoginOtp('');
      setSystemMessage('Dashboard login succeeded.');
    } catch (err: any) {
      setLoginError(err.message || 'Login failed.');
    } finally {
      setIsBusy(false);
    }
  };

  useEffect(() => {
    if (!loginChallengeId) return;
    let cancelled = false;
    const interval = window.setInterval(async () => {
      try {
        const result = await completeLogin(loginChallengeId);
        if (cancelled || result.status === 'pending') return;
        setSecurityToken(loginToken.trim());
        setSessionToken(result.session_token);
        setLoginChallengeId(null);
        setLoginNotice(null);
        setLoginOtp('');
        setSystemMessage('Dashboard login approved.');
      } catch (err: any) {
        if (!cancelled) {
          setLoginChallengeId(null);
          setLoginNotice(null);
          setLoginError(err.message || 'Login approval failed.');
        }
      }
    }, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [loginChallengeId, loginToken]);

  const handleLogout = async () => {
    try {
      await logout(securityToken, sessionToken);
    } catch {
      // The local session is cleared either way.
    }
    setSecurityToken('');
    setSessionToken('');
    setSummary(null);
    setConfig(null);
    setLoginToken('');
  };

  if (!isAuthenticated) {
    return (
      <div className="login-screen">
        <form className="login-panel" onSubmit={handleLogin}>
          <div className="login-mark">
            <Shield size={24} />
          </div>
          <div>
            <h1>Alpha Arbitrage</h1>
            <p>Operations Console</p>
          </div>
          {loginNotice ? <div className="banner success">{loginNotice}</div> : null}
          {loginError ? <div className="banner error">{loginError}</div> : null}
          <label className="setting-field">
            <span>Security Token</span>
            <input
              type="password"
              value={loginToken}
              onChange={(event) => setLoginToken(event.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          <label className="setting-field">
            <span>Authenticator / Backup Code</span>
            <input
              value={loginOtp}
              onChange={(event) => setLoginOtp(event.target.value)}
              autoComplete="one-time-code"
            />
          </label>
          <button className="primary-btn" disabled={isBusy || Boolean(loginChallengeId)} type="submit">
            <Shield size={14} />
            {loginChallengeId ? 'Waiting Approval' : 'Login'}
          </button>
        </form>
      </div>
    );
  }

  return (
    <div className="dashboard-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Activity size={16} />
          </div>
          <div>
            <strong>Alpha Arbitrage</strong>
            <span>Operations Console</span>
          </div>
        </div>

        <div className="mode-card">
          <span className={`status-dot ${isConnected ? 'live' : 'warn'}`} />
          <div>
            <strong>{currentStage}</strong>
            <span>{currentMode} mode · {currentBotState}</span>
          </div>
        </div>

        <nav className="nav">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.key}
              className={`nav-item ${page === item.key ? 'active' : ''}`}
              onClick={() => setPage(item.key)}
            >
              {item.icon}
              {item.label}
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="mini-stat">
            <span>Signals</span>
            <strong>{summary?.open_signals ?? data?.active_signals?.length ?? 0}</strong>
          </div>
          <div className="mini-stat">
            <span>Positions</span>
            <strong>{summary?.open_positions ?? positions.length}</strong>
          </div>
        </div>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <h1>{NAV_ITEMS.find((item) => item.key === page)?.label}</h1>
            <p>Live trading intelligence, controls, and audit visibility in one place.</p>
          </div>
          <button className="ghost-btn" onClick={() => { refreshDashboard(); refreshTradeHistory(); refreshHealth(); refreshConfig(); }}>
            <RefreshCw size={14} />
            Refresh
          </button>
          <button className="ghost-btn" onClick={handleLogout}>
            <LogOut size={14} />
            Logout
          </button>
        </header>

        {systemMessage ? <div className="banner success">{systemMessage}</div> : null}
        {systemError || error ? <div className="banner error">{systemError || error}</div> : null}

        {page === 'overview' && (
          <>
            <SectionHeader title="Real-Time Overview" subtitle="Core trading and runtime indicators." />
            <div className="card-grid metrics">
              <div className="metric-card">
                <span>Current Balance</span>
                <strong>{formatCurrency(summary?.current_balance)}</strong>
                <small>Spendable cash across venues</small>
              </div>
              <div className="metric-card">
                <span>Trades Today</span>
                <strong>{summary?.trades_today ?? 0}</strong>
                <small>{summary?.closed_trades ?? 0} closed lifetime</small>
              </div>
              <div className="metric-card">
                <span>Win Rate</span>
                <strong>{formatPercent(summary?.win_rate)}</strong>
                <small>{summary?.wins ?? 0} wins / {summary?.losses ?? 0} losses</small>
              </div>
              <div className="metric-card">
                <span>System Uptime</span>
                <strong>{summary?.system_uptime_human ?? '—'}</strong>
                <small>{summary?.cpu_pct?.toFixed(1) ?? '—'}% CPU · {summary?.memory_pct?.toFixed(1) ?? '—'}% memory</small>
              </div>
            </div>

            <div className="card-grid two-up">
              <section className="panel">
                <SectionHeader title="Profit Trajectory" subtitle="Cumulative realized profit from closed trades." />
                {profitChart?.points?.length ? (
                  <LineMiniChart points={profitChart.points} color="var(--emerald)" />
                ) : (
                  <div className="empty">No chart data yet.</div>
                )}
                <div className="panel-footer">
                  <span className={getTrendClass(summary?.profit_today)}>{formatCurrency(summary?.profit_today)}</span>
                  <span>Today’s realized P&L</span>
                </div>
              </section>

              <section className="panel">
                <SectionHeader title="Open Positions" subtitle="Live mark-to-market snapshot." />
                <div className="list">
                  {positions.length ? positions.slice(0, 5).map((position) => (
                    <div className="list-row" key={position.signal_id}>
                      <div>
                        <strong>{position.ticker_a} / {position.ticker_b}</strong>
                        <span>{formatDateTime(position.opened_at)}</span>
                      </div>
                      <div className={`value ${getTrendClass(position.pnl)}`}>
                        {formatCurrency(position.pnl)}
                      </div>
                    </div>
                  )) : <div className="empty">No open positions.</div>}
                </div>
              </section>
            </div>

            <div className="card-grid two-up">
              <section className="panel">
                <SectionHeader title="Risk Telemetry" subtitle="Live guardrails from the telemetry stream." />
                <div className="risk-grid">
                  <div><span>Risk Mult.</span><strong>{formatCompact(risk?.risk_multiplier)}</strong></div>
                  <div><span>Drawdown</span><strong>{formatPercent(risk?.max_drawdown_pct)}</strong></div>
                  <div><span>L2 Entropy</span><strong>{formatCompact(risk?.l2_entropy)}</strong></div>
                  <div><span>Volatility</span><strong>{risk?.volatility_status ?? '—'}</strong></div>
                </div>
              </section>

              <section className="panel">
                <SectionHeader title="Agent Reasoning" subtitle="Most recent model-side commentary." />
                <div className="feed">
                  {recentThoughts.length ? recentThoughts.map((thought, index) => (
                    <div className="feed-item" key={`${thought.signal_id ?? 'thought'}-${index}`}>
                      <strong>{thought.agent_name}</strong>
                      <span>{thought.verdict}</span>
                      <p>{thought.thought}</p>
                    </div>
                  )) : <div className="empty">No recent reasoning events.</div>}
                </div>
              </section>
            </div>
          </>
        )}

        {page === 'pairs' && (
          <>
            <SectionHeader title="Pair Universe" subtitle="Cointegration status, pair editing, and T212 wallet seeding." />
            <PairsPanel token={securityToken} sessionToken={sessionToken} />
          </>
        )}

        {page === 'analytics' && (
          <>
            <SectionHeader title="Performance Analytics" subtitle="Trade performance and realized outcome trends." />
            <div className="card-grid two-up">
              <section className="panel">
                <SectionHeader title="Cumulative Profit" subtitle="Line view of total realized P&L." />
                {profitChart?.points?.length ? <LineMiniChart points={profitChart.points} color="var(--gold)" /> : <div className="empty">No data yet.</div>}
              </section>
              <section className="panel">
                <SectionHeader title="Win / Loss by Day" subtitle="Daily distribution of positive and negative closes." />
                {winLossChart?.points?.length ? <DualBarChart points={winLossChart.points} /> : <div className="empty">No data yet.</div>}
              </section>
            </div>
            <div className="card-grid metrics">
              <div className="metric-card">
                <span>Total Closed Trades</span>
                <strong>{summary?.closed_trades ?? 0}</strong>
              </div>
              <div className="metric-card">
                <span>Capital Deployed</span>
                <strong>{formatCurrency(summary?.capital_deployed)}</strong>
              </div>
              <div className="metric-card">
                <span>Open Signals</span>
                <strong>{summary?.open_signals ?? 0}</strong>
              </div>
              <div className="metric-card">
                <span>Open Positions</span>
                <strong>{summary?.open_positions ?? 0}</strong>
              </div>
            </div>
          </>
        )}

        {page === 'trades' && (
          <>
            <SectionHeader title="Trade History" subtitle="Search and filter executed trade groups." />
            <div className="toolbar">
              <label className="search-box">
                <Search size={14} />
                <input
                  value={tradeSearch}
                  onChange={(event) => setTradeSearch(event.target.value)}
                  placeholder="Search ticker or signal id"
                />
              </label>
              <select value={tradeStatus} onChange={(event) => { setTradePage(1); setTradeStatus(event.target.value); }}>
                <option value="">All statuses</option>
                <option value="OPEN">Open</option>
                <option value="CLOSED">Closed</option>
                <option value="COMPLETED">Completed</option>
              </select>
              <select value={tradeVenue} onChange={(event) => { setTradePage(1); setTradeVenue(event.target.value); }}>
                <option value="">All venues</option>
                <option value="T212">T212</option>
                <option value="WEB3">WEB3</option>
              </select>
              <button className="ghost-btn" onClick={() => { setTradePage(1); refreshTradeHistory(); }}>Apply</button>
            </div>
            <section className="panel">
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Pair</th>
                      <th>Status</th>
                      <th>Venue</th>
                      <th>Opened</th>
                      <th>Notional</th>
                      <th>P&L</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tradeHistory?.items?.length ? tradeHistory.items.map((trade) => (
                      <tr key={trade.signal_id}>
                        <td>
                          <strong>{trade.pair}</strong>
                          <div className="muted">#{trade.signal_id.slice(0, 8)}</div>
                        </td>
                        <td>{trade.status}</td>
                        <td>{trade.venue}</td>
                        <td>{formatDateTime(trade.opened_at)}</td>
                        <td>{formatCurrency(trade.notional)}</td>
                        <td className={getTrendClass(trade.pnl)}>{formatCurrency(trade.pnl)}</td>
                      </tr>
                    )) : (
                      <tr>
                        <td colSpan={6} className="empty-row">No trades matched the current filters.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              <div className="table-footer">
                <span>{tradeHistory?.total ?? 0} results</span>
                <div className="pager">
                  <button className="ghost-btn" disabled={tradePage === 1} onClick={() => setTradePage((current) => Math.max(1, current - 1))}>Previous</button>
                  <span>Page {tradePage}</span>
                  <button
                    className="ghost-btn"
                    disabled={!!tradeHistory && tradeHistory.page * tradeHistory.page_size >= tradeHistory.total}
                    onClick={() => setTradePage((current) => current + 1)}
                  >
                    Next
                  </button>
                </div>
              </div>
            </section>
          </>
        )}

        {page === 'control' && (
          <>
            <SectionHeader title="Bot Control" subtitle="Operational state, restart queueing, and recent terminal activity." />
            <div className="card-grid metrics">
              <div className="metric-card">
                <span>Bot Status</span>
                <strong>{currentBotState}</strong>
              </div>
              <div className="metric-card">
                <span>Runtime Stage</span>
                <strong>{currentStage}</strong>
              </div>
              <div className="metric-card">
                <span>Mode</span>
                <strong>{currentMode}</strong>
              </div>
              <div className="metric-card">
                <span>Connection</span>
                <strong>{isConnected ? 'Live' : 'Reconnecting'}</strong>
              </div>
            </div>
            <div className="control-strip">
              <button className="primary-btn" disabled={isBusy} onClick={() => handleBotAction('start')}>
                <Play size={14} />
                Start
              </button>
              <button className="ghost-btn" disabled={isBusy} onClick={() => handleBotAction('stop')}>
                <Square size={14} />
                Stop
              </button>
              <button className="ghost-btn" disabled={isBusy} onClick={() => handleBotAction('restart')}>
                <RefreshCw size={14} />
                Restart
              </button>
            </div>
            <div className="card-grid two-up">
              <section className="panel">
                <SectionHeader title="Terminal Feed" subtitle="Most recent dashboard terminal messages." />
                <div className="terminal-feed">
                  {terminalMessages.length ? terminalMessages.map((message, index) => (
                    <TerminalLine key={`${message.timestamp}-${index}`} message={message} />
                  )) : <div className="empty">No terminal activity yet.</div>}
                </div>
              </section>
              <section className="panel">
                <SectionHeader title="Recent Logs" subtitle="Latest file-backed log lines." />
                <div className="log-feed">
                  {logs?.lines?.length ? logs.lines.slice(-12).map((line, index) => (
                    <code key={`${line}-${index}`}>{line}</code>
                  )) : <div className="empty">No recent log lines.</div>}
                </div>
              </section>
            </div>
          </>
        )}

        {page === 'settings' && (
          <>
            <SectionHeader title="Configuration" subtitle="Dashboard-editable runtime values with 2FA for sensitive changes." />
            <div className="card-grid two-up">
              <section className="panel">
                <SectionHeader title="Editable Variables" subtitle="Sensitive changes require a current OTP or backup code." />
                <div className="settings-grid">
                  {config?.items.map((item) => (
                    <label key={item.key} className="setting-field">
                      <span>{item.key}{item.sensitive ? ' · 2FA' : ''}</span>
                      {item.type === 'bool' ? (
                        <select
                          value={configForm[item.key] ?? 'false'}
                          onChange={(event) => setConfigForm((current) => ({ ...current, [item.key]: event.target.value }))}
                        >
                          <option value="true">Enabled</option>
                          <option value="false">Disabled</option>
                        </select>
                      ) : (
                        <input
                          type={item.sensitive ? 'password' : item.type === 'str' ? 'text' : 'number'}
                          step={item.type === 'int' ? '1' : item.type === 'float' ? '0.0001' : undefined}
                          value={configForm[item.key] ?? ''}
                          onChange={(event) => setConfigForm((current) => ({ ...current, [item.key]: event.target.value }))}
                        />
                      )}
                    </label>
                  ))}
                </div>
                <label className="setting-field">
                  <span>OTP / Backup Code</span>
                  <input
                    value={otpToken}
                    onChange={(event) => setOtpToken(event.target.value)}
                    placeholder="Required for sensitive changes"
                  />
                </label>
                <div className="inline-actions">
                  <button className="primary-btn" disabled={isBusy} onClick={handleSaveConfig}>Save Changes</button>
                </div>
              </section>

              <section className="panel">
                <SectionHeader title="Two-Factor Auth" subtitle="Authenticator-based gate for sensitive config writes." />
                <div className="twofa-status">
                  <div><span>Enabled</span><strong>{config?.two_factor.enabled ? 'Yes' : 'No'}</strong></div>
                  <div><span>Pending Setup</span><strong>{config?.two_factor.pending_setup ? 'Yes' : 'No'}</strong></div>
                  <div><span>Backup Codes Left</span><strong>{config?.two_factor.backup_codes_remaining ?? 0}</strong></div>
                </div>
                <div className="inline-actions">
                  <button className="ghost-btn" disabled={isBusy} onClick={handleInitiate2FA}>Generate Setup Secret</button>
                </div>
                {twoFactorSetup ? (
                  <div className="twofa-setup">
                    <p>Secret: <code>{twoFactorSetup.secret}</code></p>
                    <p>otpauth URI:</p>
                    <code className="block-code">{twoFactorSetup.otpauth_url}</code>
                    <p>Backup codes:</p>
                    <div className="code-grid">
                      {twoFactorSetup.backup_codes.map((code) => <code key={code}>{code}</code>)}
                    </div>
                    <div className="inline-actions">
                      <input
                        value={twoFactorCode}
                        onChange={(event) => setTwoFactorCode(event.target.value)}
                        placeholder="Enter authenticator code"
                      />
                      <button className="primary-btn" disabled={isBusy} onClick={handleVerify2FA}>Verify & Enable</button>
                    </div>
                  </div>
                ) : null}
              </section>
            </div>
            <section className="panel">
              <SectionHeader title="Audit Log" subtitle="Recent configuration changes and 2FA usage." />
              <div className="list">
                {config?.audit_log?.length ? config.audit_log.map((entry, index) => (
                  <div className="list-row audit-row" key={`${entry.key}-${entry.timestamp}-${index}`}>
                    <div>
                      <strong>{entry.key}</strong>
                      <span>{entry.actor} · {formatDateTime(entry.timestamp)}</span>
                    </div>
                    <div className="audit-values">
                      <span>{String(entry.old_value)}</span>
                      <span>→</span>
                      <span>{String(entry.new_value)}</span>
                      {entry.requires_2fa ? <em>2FA</em> : null}
                    </div>
                  </div>
                )) : <div className="empty">No config changes recorded yet.</div>}
              </div>
            </section>
          </>
        )}

        {page === 'health' && (
          <>
            <SectionHeader title="System Health" subtitle="CPU, memory, network, and event visibility." />
            <div className="card-grid metrics">
              <div className="metric-card">
                <span>CPU</span>
                <strong>{health?.current?.cpu_pct?.toFixed(1) ?? '—'}%</strong>
              </div>
              <div className="metric-card">
                <span>System Memory</span>
                <strong>{health?.current?.system_memory_pct?.toFixed(1) ?? '—'}%</strong>
              </div>
              <div className="metric-card">
                <span>Process RSS</span>
                <strong>{health?.current?.rss_mb?.toFixed(1) ?? '—'} MB</strong>
              </div>
              <div className="metric-card">
                <span>Threads</span>
                <strong>{health?.current?.threads ?? '—'}</strong>
              </div>
            </div>
            <div className="card-grid two-up">
              <section className="panel">
                <SectionHeader title="CPU History" subtitle="Recent process and host samples." />
                {health?.history?.length ? (
                  <LineMiniChart
                    points={health.history.map((point) => ({ timestamp: point.timestamp, value: point.cpu_pct ?? 0 }))}
                    color="var(--crimson)"
                  />
                ) : <div className="empty">No health samples yet.</div>}
              </section>
              <section className="panel">
                <SectionHeader title="Memory History" subtitle="Recent host memory utilization." />
                {health?.history?.length ? (
                  <LineMiniChart
                    points={health.history.map((point) => ({ timestamp: point.timestamp, value: point.system_memory_pct ?? 0 }))}
                    color="var(--teal)"
                  />
                ) : <div className="empty">No health samples yet.</div>}
              </section>
            </div>
            <section className="panel">
              <SectionHeader title="Recent Events" subtitle={logs?.file ? `Log source: ${logs.file}` : 'SQLite event feed'} />
              <div className="feed">
                {logs?.events?.length ? logs.events.slice(0, 10).map((event, index) => (
                  <div className="feed-item" key={`${event.timestamp}-${index}`}>
                    <strong>{event.source}</strong>
                    <span>{event.level} · {formatDateTime(event.timestamp)}</span>
                    <p>{event.message}</p>
                  </div>
                )) : <div className="empty">No recent events captured.</div>}
              </div>
            </section>
          </>
        )}
      </main>
    </div>
  );
}

function TerminalLine({ message }: { message: TerminalMessage }) {
  return (
    <div className="terminal-line">
      <div>
        <strong>[{message.type}]</strong>
        <span>{formatDateTime(message.timestamp)}</span>
      </div>
      <p>{message.text}</p>
    </div>
  );
}

export default App;
