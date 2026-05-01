import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity,
  BarChart3,
  Bot,
  Cpu,
  Gauge,
  History,
  Layers,
  LogOut,
  RefreshCw,
  Settings as SettingsIcon,
  Shield,
  Wallet,
} from 'lucide-react';
import './App.css';
import PairsPanel from './components/PairsPanel';
import WalletPanel from './components/WalletPanel';
import PositionsPanel from './components/PositionsPanel';
import {
  ApiError,
  type Signal,
  type AuthSession,
  type ChartResponse,
  type ConfigResponse,
  type HealthResponse,
  type LogsResponse,
  type OpenPosition,
  type SummaryResponse,
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

// New page imports
import OverviewPage from './pages/OverviewPage';
import AnalyticsPage from './pages/AnalyticsPage';
import TradeHistoryPage from './pages/TradeHistoryPage';
import BotControlPage from './pages/BotControlPage';
import SettingsPage from './pages/SettingsPage';
import SystemHealthPage from './pages/SystemHealthPage';
import SignalsPage from './pages/SignalsPage';

type Page = 'overview' | 'wallet' | 'pairs' | 'signals' | 'positions' | 'analytics' | 'trades' | 'control' | 'settings' | 'health';

interface NavItem {
  key: Page;
  label: string;
  icon: React.ReactNode;
  category: 'MONITORING' | 'TRADING' | 'SYSTEM';
}

const NAV_ITEMS: NavItem[] = [
  { key: 'overview', label: 'Overview', icon: <Gauge size={16} />, category: 'MONITORING' },
  { key: 'analytics', label: 'Analytics', icon: <BarChart3 size={16} />, category: 'MONITORING' },
  { key: 'trades', label: 'Trade History', icon: <History size={16} />, category: 'MONITORING' },
  
  { key: 'wallet', label: 'Wallet', icon: <Wallet size={16} />, category: 'TRADING' },
  { key: 'pairs', label: 'Pairs', icon: <Layers size={16} />, category: 'TRADING' },
  { key: 'signals', label: 'Signals', icon: <Activity size={16} />, category: 'TRADING' },
  { key: 'positions', label: 'Positions', icon: <History size={16} />, category: 'TRADING' },
  
  { key: 'control', label: 'Bot Control', icon: <Bot size={16} />, category: 'SYSTEM' },
  { key: 'settings', label: 'Settings', icon: <SettingsIcon size={16} />, category: 'SYSTEM' },
  { key: 'health', label: 'System Health', icon: <Cpu size={16} />, category: 'SYSTEM' },
];

const DASHBOARD_SESSION_STORAGE_KEY = 'alpha-arbitrage.dashboardSession';

interface StoredDashboardSession {
  sessionToken: string;
  expiresAt: string;
  actor?: string;
}

function clearStoredDashboardSession() {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(DASHBOARD_SESSION_STORAGE_KEY);
  } catch {
    // Storage can be disabled by browser privacy settings.
  }
}

function readStoredDashboardSession(): StoredDashboardSession | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(DASHBOARD_SESSION_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<StoredDashboardSession>;
    if (!parsed.sessionToken || !parsed.expiresAt) {
      clearStoredDashboardSession();
      return null;
    }
    const expiresAtMs = Date.parse(parsed.expiresAt);
    if (!Number.isFinite(expiresAtMs) || expiresAtMs <= Date.now()) {
      clearStoredDashboardSession();
      return null;
    }
    return {
      sessionToken: parsed.sessionToken,
      expiresAt: parsed.expiresAt,
      actor: parsed.actor,
    };
  } catch {
    clearStoredDashboardSession();
    return null;
  }
}

function writeStoredDashboardSession(session: AuthSession) {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(
      DASHBOARD_SESSION_STORAGE_KEY,
      JSON.stringify({
        sessionToken: session.session_token,
        expiresAt: session.expires_at,
        actor: session.actor,
      } satisfies StoredDashboardSession),
    );
  } catch {
    // The in-memory session still works for this tab.
  }
}

function isDashboardAuthError(err: unknown) {
  const message = err instanceof Error ? err.message : String(err ?? '');
  if (err instanceof ApiError && err.status === 401) return true;
  return /dashboard session|dashboard login is required|invalid dashboard token/i.test(message);
}

/**
 * Root React component for the Alpha Arbitrage authenticated dashboard and login flows.
 *
 * Renders the login screen when not authenticated and the full operations console when authenticated.
 * Manages session persistence, login/approval polling, periodic data refresh (summary, charts, positions, trade history, health, config), startup progress calculation and animation, bot control actions, configuration editing with optional 2FA confirmation, and 2FA setup/verification.
 *
 * @returns The dashboard UI element (login view when not authenticated; main console when authenticated).
 */
function App() {
  const [storedSession] = useState<StoredDashboardSession | null>(() => readStoredDashboardSession());
  const [securityToken, setSecurityToken] = useState('');
  const [sessionToken, setSessionToken] = useState(() => storedSession?.sessionToken ?? '');
  const [loginToken, setLoginToken] = useState('');
  const [loginOtp, setLoginOtp] = useState('');
  const [loginChallengeId, setLoginChallengeId] = useState<string | null>(null);
  const [loginNotice, setLoginNotice] = useState<string | null>(null);
  const [loginError, setLoginError] = useState<string | null>(null);

  const isAuthenticated = Boolean(sessionToken);
  const authToken = securityToken || null;
  const { data, error } = useDashboardStream(isAuthenticated ? authToken : null, sessionToken);
  const { isConnected, risk, thoughts, botState } = useTelemetry(isAuthenticated ? authToken : null, sessionToken);

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
  const [saveOtpModalOpen, setSaveOtpModalOpen] = useState(false);
  const [saveOtpCode, setSaveOtpCode] = useState('');
  const [pendingConfigUpdates, setPendingConfigUpdates] = useState<Record<string, string> | null>(null);
  const [twoFactorSetup, setTwoFactorSetup] = useState<TwoFactorInitiateResponse | null>(null);
  const [twoFactorCode, setTwoFactorCode] = useState('');
  const [systemMessage, setSystemMessage] = useState<string | null>(null);
  const [systemError, setSystemError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  const clearAuthenticatedSession = useCallback((message?: string) => {
    clearStoredDashboardSession();
    setSecurityToken('');
    setSessionToken('');
    setSummary(null);
    setConfig(null);
    setLoginToken('');
    setLoginOtp('');
    setLoginChallengeId(null);
    setLoginNotice(null);
    setSystemMessage(null);
    setSystemError(message ?? null);
  }, []);

  const handleAuthFailure = useCallback((err: unknown) => {
    if (!isDashboardAuthError(err)) return false;
    const message = err instanceof Error ? err.message : 'Dashboard session expired. Please log in again.';
    clearAuthenticatedSession(message);
    return true;
  }, [clearAuthenticatedSession]);

  const establishAuthenticatedSession = useCallback((session: AuthSession, message: string) => {
    writeStoredDashboardSession(session);
    setSecurityToken('');
    setSessionToken(session.session_token);
    setLoginToken('');
    setLoginOtp('');
    setLoginChallengeId(null);
    setLoginNotice(null);
    setLoginError(null);
    setSystemError(null);
    setSystemMessage(message);
  }, []);

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
      if (handleAuthFailure(err)) return;
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
      if (handleAuthFailure(err)) return;
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
    } else if (handleAuthFailure(healthResult.reason)) {
      return;
    } else {
      setSystemError(healthResult.reason?.message || 'Failed to load system health.');
    }

    if (logsResult.status === 'fulfilled') {
      setLogs(logsResult.value);
    } else if (handleAuthFailure(logsResult.reason)) {
      return;
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
      if (handleAuthFailure(err)) return;
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
  const startupStageText = `${currentStage} ${data?.details ?? ''}`.toLowerCase();
  const preWarmingProgress = useMemo(() => {
    const stage = (currentStage || '').toLowerCase();
    const details = data?.details || '';
    if (!/pre[_ -]?warming|initializ/.test(stage) && !/pair list/i.test(details)) return null;
    const match = details.match(/(\d+)\s*\/\s*(\d+)/);
    if (!match) return null;
    const current = Number(match[1]);
    const total = Number(match[2]);
    if (!Number.isFinite(current) || !Number.isFinite(total) || total <= 0) return null;
    return {
      current,
      total,
      pct: Math.max(0, Math.min(100, Math.round((current / total) * 100))),
    };
  }, [currentStage, data?.details]);
  const startupReady = useMemo(() => {
    if (!isAuthenticated) return false;
    if (!summary || !data) return false;
    if (!isConnected) return false;
    const stillStarting = /(boot|init|start|warm|load|attach|connect)/i.test(startupStageText);
    return !stillStarting;
  }, [data, isAuthenticated, isConnected, startupStageText, summary]);
  const startupTargetProgress = useMemo(() => {
    if (!isAuthenticated) return 0;
    if (startupReady) return 100;
    let progress = 10;
    if (data) progress = 28;
    if (summary) progress = 54;
    if (health || tradeHistory || config) progress = 72;
    if (isConnected) progress = 84;
    if (/warm|load|attach|connect/.test(startupStageText)) progress = Math.max(progress, 90);
    return Math.min(progress, 95);
  }, [config, data, health, isAuthenticated, isConnected, startupReady, startupStageText, summary, tradeHistory]);
  const [startupProgress, setStartupProgress] = useState(8);

  useEffect(() => {
    if (!isAuthenticated) {
      setStartupProgress(8);
      return;
    }
    setStartupProgress((current) => {
      if (startupReady) return 100;
      if (current > startupTargetProgress) return startupTargetProgress;
      return current;
    });
  }, [isAuthenticated, startupReady, startupTargetProgress]);

  useEffect(() => {
    if (!isAuthenticated || startupReady) return;
    const id = window.setInterval(() => {
      setStartupProgress((current) => {
        if (current >= startupTargetProgress) return current;
        const remaining = startupTargetProgress - current;
        const step = Math.max(1, Math.ceil(remaining / 6));
        return Math.min(startupTargetProgress, current + step);
      });
    }, 350);
    return () => window.clearInterval(id);
  }, [isAuthenticated, startupReady, startupTargetProgress]);

  const handleBotAction = async (action: 'start' | 'stop' | 'restart') => {
    setIsBusy(true);
    setSystemError(null);
    setSystemMessage(null);
    try {
      const result = await controlBot(securityToken, sessionToken, action);
      setSystemMessage(`Bot ${result.action} request accepted.`);
      await refreshDashboard();
    } catch (err: any) {
      if (handleAuthFailure(err)) return;
      setSystemError(err.message || `Failed to ${action} bot.`);
    } finally {
      setIsBusy(false);
    }
  };

  const handleSaveConfig = async () => {
    if (!config) return;
    const updates = Object.fromEntries(
      config.items
        .filter((item) => configForm[item.key] !== String(item.value))
        .map((item) => [item.key, configForm[item.key]]),
    );
    if (!Object.keys(updates).length) {
      setSystemMessage('No settings changed.');
      return;
    }

    setIsBusy(true);
    setSystemError(null);
    setSystemMessage(null);
    try {
      const response = await updateConfig(securityToken, sessionToken, updates, 'dashboard');
      setConfig(response);
      setConfigForm(Object.fromEntries(response.items.map((item) => [item.key, String(item.value)])));
      setSystemMessage('Configuration updated.');
    } catch (err: any) {
      if (handleAuthFailure(err)) return;
      const errMsg = err?.message || 'Failed to update configuration.';
      const requiresOtp = err instanceof ApiError && err.status === 403 && /2fa|token/i.test(errMsg);
      if (requiresOtp) {
        setPendingConfigUpdates(updates);
        setSaveOtpCode('');
        setSaveOtpModalOpen(true);
        setSystemMessage('2FA confirmation required to save these changes.');
      } else {
        setSystemError(errMsg);
      }
    } finally {
      setIsBusy(false);
    }
  };

  const handleConfirmSaveWithOtp = async () => {
    if (!pendingConfigUpdates || !saveOtpCode.trim()) {
      setSystemError('Enter your authenticator or backup code.');
      return;
    }
    setIsBusy(true);
    setSystemError(null);
    try {
      const response = await updateConfig(
        securityToken,
        sessionToken,
        pendingConfigUpdates,
        'dashboard',
        saveOtpCode.trim(),
      );
      setConfig(response);
      setConfigForm(Object.fromEntries(response.items.map((item) => [item.key, String(item.value)])));
      setPendingConfigUpdates(null);
      setSaveOtpCode('');
      setSaveOtpModalOpen(false);
      setSystemMessage('Configuration updated.');
    } catch (err: any) {
      if (handleAuthFailure(err)) return;
      setSystemError(err?.message || 'Failed to verify 2FA for configuration save.');
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
      if (handleAuthFailure(err)) return;
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
      if (handleAuthFailure(err)) return;
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
      establishAuthenticatedSession(result, 'Dashboard login succeeded.');
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
        establishAuthenticatedSession(result, 'Dashboard login approved.');
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
  }, [loginChallengeId, establishAuthenticatedSession]);

  const handleLogout = async () => {
    try {
      await logout(authToken, sessionToken);
    } catch {
      // The local session is cleared either way.
    }
    clearAuthenticatedSession();
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
          {['MONITORING', 'TRADING', 'SYSTEM'].map((category) => (
            <div key={category} className="nav-group">
              <div className="nav-group-label">{category}</div>
              {NAV_ITEMS.filter((item) => item.category === category).map((item) => (
                <button
                  key={item.key}
                  className={`nav-item ${page === item.key ? 'active' : ''}`}
                  onClick={() => setPage(item.key)}
                >
                  {item.icon}
                  {item.label}
                </button>
              ))}
            </div>
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
          <div className="topbar-actions">
            <button className="ghost-btn" onClick={() => { refreshDashboard(); refreshTradeHistory(); refreshHealth(); refreshConfig(); }}>
              <RefreshCw size={14} />
              Refresh
            </button>
            <button className="ghost-btn" onClick={handleLogout}>
              <LogOut size={14} />
              Logout
            </button>
          </div>
        </header>

        {systemMessage ? <div className="banner success">{systemMessage}</div> : null}
        {systemError || error ? <div className="banner error">{systemError || error}</div> : null}
        {!startupReady ? (
          <div className="startup-progress">
            <div className="startup-progress-head">
              <strong>Bot starting up...</strong>
              <span>{startupProgress}%</span>
            </div>
            <div className="startup-progress-track">
              <div className="startup-progress-fill" style={{ width: `${startupProgress}%` }} />
            </div>
            <small>{data?.details || currentStage || 'Loading services and syncing state...'}</small>
            {preWarmingProgress ? (
              <div className="prewarm-progress">
                <div className="startup-progress-head">
                  <strong>Pre-warming pair list</strong>
                  <span>{preWarmingProgress.current}/{preWarmingProgress.total}</span>
                </div>
                <div className="startup-progress-track">
                  <div className="startup-progress-fill prewarm-progress-fill" style={{ width: `${preWarmingProgress.pct}%` }} />
                </div>
              </div>
            ) : null}
          </div>
        ) : null}

        {page === 'overview' && (
          <OverviewPage
            summary={summary}
            profitChart={profitChart}
            positions={positions}
            risk={risk}
            recentThoughts={recentThoughts}
            marketRegimeConfidence={data?.market_regime?.confidence}
            globalAccuracy={data?.global_accuracy ?? null}
          />
        )}

        {page === 'pairs' && (
          <>
            <PairsPanel token={securityToken} sessionToken={sessionToken} />
          </>
        )}

        {page === 'wallet' && (
          <>
            <WalletPanel token={securityToken} sessionToken={sessionToken} />
          </>
        )}

        {page === 'analytics' && (
          <AnalyticsPage
            summary={summary}
            profitChart={profitChart}
            winLossChart={winLossChart}
          />
        )}

        {page === 'signals' && (
          <SignalsPage signals={(data?.active_signals ?? []) as Signal[]} />
        )}

        {page === 'positions' && (
          <PositionsPanel token={securityToken} sessionToken={sessionToken} />
        )}

        {page === 'trades' && (
          <TradeHistoryPage
            tradeHistory={tradeHistory}
            tradeSearch={tradeSearch}
            setTradeSearch={setTradeSearch}
            tradeStatus={tradeStatus}
            setTradeStatus={setTradeStatus}
            tradeVenue={tradeVenue}
            setTradeVenue={setTradeVenue}
            tradePage={tradePage}
            setTradePage={setTradePage}
            refreshTradeHistory={refreshTradeHistory}
          />
        )}

        {page === 'control' && (
          <BotControlPage
            currentBotState={currentBotState}
            currentStage={currentStage}
            currentMode={currentMode}
            isConnected={isConnected}
            isBusy={isBusy}
            handleBotAction={handleBotAction}
            terminalMessages={terminalMessages}
            logs={logs}
          />
        )}

        {page === 'settings' && (
          <SettingsPage
            config={config}
            configForm={configForm}
            setConfigForm={setConfigForm}
            handleSaveConfig={handleSaveConfig}
            isBusy={isBusy}
            handleInitiate2FA={handleInitiate2FA}
            twoFactorSetup={twoFactorSetup}
            twoFactorCode={twoFactorCode}
            setTwoFactorCode={setTwoFactorCode}
            handleVerify2FA={handleVerify2FA}
          />
        )}

        {page === 'health' && (
          <SystemHealthPage
            health={health}
            logs={logs}
          />
        )}
        {saveOtpModalOpen ? (
          <div className="overlay" onClick={(event) => event.target === event.currentTarget && !isBusy && setSaveOtpModalOpen(false)}>
            <div className="confirm-window">
              <div className="terminal-header">
                <div className="terminal-dots">
                  <span className="td-red" onClick={() => !isBusy && setSaveOtpModalOpen(false)} />
                  <span className="td-yellow" />
                  <span className="td-green" />
                </div>
                <span className="terminal-title">confirm 2fa for save</span>
              </div>
              <div className="confirm-body">
                <div className="confirm-total">
                  <span>One-time confirmation needed</span>
                  <strong>2FA</strong>
                  <small>Enter authenticator code or backup code to apply settings changes.</small>
                </div>
                <label className="setting-field">
                  <span>Authenticator / Backup Code</span>
                  <input
                    value={saveOtpCode}
                    onChange={(event) => setSaveOtpCode(event.target.value)}
                    autoFocus
                    placeholder="6-digit code or backup code"
                  />
                </label>
                <div className="inline-actions">
                  <button className="ghost-btn" disabled={isBusy} onClick={() => setSaveOtpModalOpen(false)}>
                    Cancel
                  </button>
                  <button className="primary-btn" disabled={isBusy} onClick={handleConfirmSaveWithOtp}>
                    {isBusy ? 'Saving...' : 'Confirm Save'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        ) : null}
      </main>
    </div>
  );
}

export default App;
