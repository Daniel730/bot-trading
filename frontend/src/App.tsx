import React, { Suspense, lazy, useCallback, useEffect, useMemo, useState } from 'react';
import {
  LogOut,
  RefreshCw,
} from 'lucide-react';
import './App.css';
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
  cancelLogin,
  completeLogin,
  controlBot,
  discoverPairs,
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
  sendTerminalCommand,
  updateConfig,
  useDashboardStream,
  verifyTwoFactor,
} from './services/api';
import {
  clearStoredDashboardSession,
  isDashboardAuthError,
  readStoredDashboardSession,
  type StoredDashboardSession,
  scrubAuthQueryParamsFromUrl,
  writeStoredDashboardSession,
} from './services/dashboardSession';
import { useTelemetry } from './hooks/useTelemetry';
import { useAutoDismiss } from './hooks/useAutoDismiss';
import { useStartupProgress } from './hooks/useStartupProgress';
import { NAV_ITEMS, isPage, type Page } from './constants/navigation';
import LoginView from './components/dashboard/LoginView';
import SidebarNav from './components/dashboard/SidebarNav';
import { PanelSkeleton } from './components/Skeleton';

// Heavy panels/pages — code-split (#133); Suspense fallback uses skeleton system (#132).
const PairsPanel = lazy(() => import('./components/PairsPanel'));
const WalletPanel = lazy(() => import('./components/WalletPanel'));
const PositionsPanel = lazy(() => import('./components/PositionsPanel'));
const BrokerPositionsPanel = lazy(() => import('./components/BrokerPositionsPanel'));
const OverviewPage = lazy(() => import('./pages/OverviewPage'));
const AnalyticsPage = lazy(() => import('./pages/AnalyticsPage'));
const TradeHistoryPage = lazy(() => import('./pages/TradeHistoryPage'));
const BotControlPage = lazy(() => import('./pages/BotControlPage'));
const SettingsPage = lazy(() => import('./pages/SettingsPage'));
const SystemHealthPage = lazy(() => import('./pages/SystemHealthPage'));
const SignalsPage = lazy(() => import('./pages/SignalsPage'));

function PageFallback({ label }: { label: string }) {
  return (
    <div className="panel" style={{ padding: 16 }}>
      <PanelSkeleton rows={5} label={label} />
    </div>
  );
}

/**
 * Root React component that provides the authenticated Alpha Arbitrage dashboard and its login flow.
 *
 * Manages session persistence and authentication (including approval polling), periodic data refreshes (summary, charts, positions, trade history, health, config), startup progress state, bot control actions (start/stop/restart and pair discovery), configuration editing with optional 2FA confirmation, and 2FA setup/verification. Renders a login view when unauthenticated and the full operations console when authenticated.
 *
 * @returns The dashboard UI element: the login view when not authenticated, otherwise the main operations console.
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
  const { data, error, authError: streamAuthError } = useDashboardStream(
    isAuthenticated ? authToken : null,
    isAuthenticated ? sessionToken : null,
  );
  const { isConnected, risk, thoughts, botState, authError: telemetryAuthError } = useTelemetry(
    isAuthenticated ? authToken : null,
    isAuthenticated ? sessionToken : null,
  );

  const [page, setPageState] = useState<Page>(() => {
    const hash = window.location.hash.replace(/^#\/?/, '');
    return isPage(hash) ? hash : 'overview';
  });

  const setPage = useCallback((next: Page) => {
    setPageState(next);
    const nextHash = `#/${next}`;
    if (window.location.hash !== nextHash) {
      window.history.replaceState({}, document.title, `${window.location.pathname}${window.location.search}${nextHash}`);
    }
  }, []);
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
  const [pendingBotAction, setPendingBotAction] = useState<'start' | 'stop' | 'restart' | null>(null);
  const [pendingTwoFactorRotate, setPendingTwoFactorRotate] = useState(false);
  const [twoFactorSetup, setTwoFactorSetup] = useState<TwoFactorInitiateResponse | null>(null);
  const [twoFactorCode, setTwoFactorCode] = useState('');
  const [systemMessage, setSystemMessage] = useState<string | null>(null);
  const [systemError, setSystemError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  useAutoDismiss(systemMessage, setSystemMessage);
  useAutoDismiss(systemError, setSystemError, 10000);

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
    // LoginView only renders loginError — keep expiry/auth messages visible after logout.
    setLoginError(message ?? null);
    setSystemMessage(null);
    setSystemError(null);
  }, []);

  const handleAuthFailure = useCallback((err: unknown) => {
    if (!isDashboardAuthError(err)) return false;
    const message = err instanceof Error ? err.message : 'Dashboard session expired. Please log in again.';
    clearAuthenticatedSession(message);
    return true;
  }, [clearAuthenticatedSession]);

  useEffect(() => {
    if (streamAuthError) handleAuthFailure(streamAuthError);
  }, [streamAuthError, handleAuthFailure]);

  useEffect(() => {
    if (telemetryAuthError) handleAuthFailure(telemetryAuthError);
  }, [telemetryAuthError, handleAuthFailure]);

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
    // Defense in depth — also scrubbed synchronously in main.tsx before first paint.
    scrubAuthQueryParamsFromUrl();
  }, []);

  useEffect(() => {
    const onHashChange = () => {
      const hash = window.location.hash.replace(/^#\/?/, '');
      if (isPage(hash)) setPageState(hash);
    };
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
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
  const currentBotState = summary?.bot_status ?? data?.runtime?.desired_bot_state ?? 'RUNNING';
  const paperTradingConfigValue = config?.items.find((item) => item.key === 'PAPER_TRADING')?.value;
  const paperTrading =
    data?.runtime?.paper_trading ??
    (typeof paperTradingConfigValue === 'boolean'
      ? paperTradingConfigValue
      : String(paperTradingConfigValue).toLowerCase() === 'true');
  const { startupProgress, startupReady, preWarmingProgress } = useStartupProgress({
    isAuthenticated,
    isConnected,
    currentStage,
    details: data?.details,
    dataReady: Boolean(data),
    summary,
    health,
    tradeHistory,
    config,
  });

  const handleBotAction = async (action: 'start' | 'stop' | 'restart', otpToken?: string) => {
    setIsBusy(true);
    setSystemError(null);
    setSystemMessage(null);
    try {
      const result = await controlBot(securityToken, sessionToken, action, 'dashboard', otpToken);
      setPendingBotAction(null);
      setSaveOtpModalOpen(false);
      setSaveOtpCode('');
      setSystemMessage(`Bot ${result.action} request accepted.`);
      await refreshDashboard();
    } catch (err: any) {
      if (handleAuthFailure(err)) return;
      const errMsg = err?.message || `Failed to ${action} bot.`;
      const requiresOtp = err instanceof ApiError && err.status === 403 && /2fa|token/i.test(errMsg);
      if (requiresOtp && !otpToken) {
        setPendingBotAction(action);
        setPendingConfigUpdates(null);
        setPendingTwoFactorRotate(false);
        setSaveOtpCode('');
        setSaveOtpModalOpen(true);
        setSystemMessage('2FA confirmation required for bot control.');
      } else {
        setSystemError(errMsg);
      }
    } finally {
      setIsBusy(false);
    }
  };

  const handleDiscoverPairs = async () => {
    setIsBusy(true);
    setSystemError(null);
    setSystemMessage(null);
    try {
      let result;
      try {
        result = await discoverPairs(securityToken, sessionToken);
      } catch (firstErr: any) {
        const errMsg = firstErr?.message || '';
        const needsOtp =
          firstErr instanceof ApiError && firstErr.status === 403 && /2fa|token/i.test(errMsg);
        if (needsOtp) {
          const otp = window.prompt(
            'Step-up 2FA required to start pair discovery.\nEnter authenticator or backup code:',
          );
          if (!otp?.trim()) throw firstErr;
          result = await discoverPairs(securityToken, sessionToken, otp.trim());
        } else {
          throw firstErr;
        }
      }
      setSystemMessage(result.message || 'Pair discovery started. Completion will appear in the terminal feed.');
    } catch (err: any) {
      if (handleAuthFailure(err)) return;
      setSystemError(err.message || 'Failed to start pair discovery.');
    } finally {
      setIsBusy(false);
    }
  };

  const handleTerminalCommand = async (command: string, otpToken?: string) => {
    setSystemError(null);
    setSystemMessage(null);
    try {
      const run = (otp?: string) =>
        sendTerminalCommand(command, securityToken, sessionToken, undefined, otp);
      try {
        const result = await run(otpToken);
        setSystemMessage(result.message || `Command sent: ${command}`);
      } catch (firstErr: any) {
        const errMsg = firstErr?.message || '';
        const needsOtp =
          firstErr instanceof ApiError && firstErr.status === 403 && /2fa|token/i.test(errMsg);
        if (needsOtp && !otpToken) {
          const otp = window.prompt(
            'Enter authenticator or backup code for this terminal command:',
          );
          if (!otp?.trim()) throw firstErr;
          const result = await run(otp.trim());
          setSystemMessage(result.message || `Command sent: ${command}`);
        } else {
          throw firstErr;
        }
      }
    } catch (err: any) {
      if (handleAuthFailure(err)) return;
      setSystemError(err.message || 'Failed to send terminal command.');
      throw err;
    }
  };

  const handleCancelLoginApproval = async () => {
    if (!loginChallengeId) return;
    setIsBusy(true);
    try {
      await cancelLogin(loginChallengeId);
    } catch {
      // Local cancel still clears pending UI state.
    } finally {
      setLoginChallengeId(null);
      setLoginNotice(null);
      setLoginError(null);
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
        setPendingBotAction(null);
        setPendingTwoFactorRotate(false);
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
    if (!saveOtpCode.trim()) {
      setSystemError('Enter your authenticator or backup code.');
      return;
    }
    if (pendingBotAction) {
      await handleBotAction(pendingBotAction, saveOtpCode.trim());
      return;
    }
    if (pendingTwoFactorRotate) {
      await handleInitiate2FA(saveOtpCode.trim());
      return;
    }
    if (!pendingConfigUpdates) {
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
      await refreshConfig();
      setSystemMessage('Configuration updated successfully!');
    } catch (err: any) {
      if (handleAuthFailure(err)) return;
      setSystemError(err?.message || 'Failed to verify 2FA for configuration save.');
    } finally {
      setIsBusy(false);
    }
  };

  const handleInitiate2FA = async (otpToken?: string) => {
    setIsBusy(true);
    setSystemError(null);
    setSystemMessage(null);
    try {
      const result = await initiateTwoFactor(securityToken, sessionToken, otpToken);
      setTwoFactorSetup(result);
      setPendingTwoFactorRotate(false);
      setSaveOtpModalOpen(false);
      setSaveOtpCode('');
      setSystemMessage('2FA setup secret generated. Verify with your authenticator code to enable it.');
    } catch (err: any) {
      if (handleAuthFailure(err)) return;
      const errMsg = err.message || 'Failed to initiate 2FA.';
      const requiresOtp = err instanceof ApiError && err.status === 403 && /2fa|token|rotate/i.test(errMsg);
      if (requiresOtp && !otpToken) {
        setPendingTwoFactorRotate(true);
        setPendingBotAction(null);
        setPendingConfigUpdates(null);
        setSaveOtpCode('');
        setSaveOtpModalOpen(true);
        setSystemMessage('Current 2FA code required to rotate authenticator setup.');
      } else {
        setSystemError(errMsg);
      }
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
    return <LoginView
      loginToken={loginToken}
      setLoginToken={setLoginToken}
      loginOtp={loginOtp}
      setLoginOtp={setLoginOtp}
      loginNotice={loginNotice}
      loginError={loginError}
      isBusy={isBusy}
      loginChallengeId={loginChallengeId}
      onSubmit={handleLogin}
      onCancelApproval={handleCancelLoginApproval}
    />;
  }

  return (
    <div className="dashboard-shell">
      <SidebarNav
        isConnected={isConnected}
        currentStage={currentStage}
        currentMode={currentMode}
        currentBotState={currentBotState}
        page={page}
        onPageChange={setPage}
        summary={summary}
        activeSignalsCount={data?.active_signals?.length ?? 0}
        positionsCount={positions.length}
      />

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

        <Suspense fallback={<PageFallback label={`Loading ${page} panel`} />}>
        {page === 'overview' && (
          <OverviewPage
            summary={summary}
            positions={positions}
            risk={risk}
            recentThoughts={recentThoughts}
            marketRegime={data?.market_regime?.regime ?? null}
            marketRegimeConfidence={data?.market_regime?.confidence}
            globalAccuracy={data?.global_accuracy ?? null}
          />
        )}

        {page === 'pairs' && (
          <>
            <PairsPanel token={securityToken} sessionToken={sessionToken} paperTrading={paperTrading} />
          </>
        )}

        {page === 'wallet' && (
          <>
            <WalletPanel token={securityToken} sessionToken={sessionToken} paperTrading={paperTrading} />
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
          <div className="card-grid two-up">
            <PositionsPanel token={securityToken} sessionToken={sessionToken} />
            <BrokerPositionsPanel token={securityToken} sessionToken={sessionToken} />
          </div>
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
            handleDiscoverPairs={handleDiscoverPairs}
            terminalMessages={terminalMessages}
            logs={logs}
            token={securityToken}
            sessionToken={sessionToken}
            onSendTerminalCommand={handleTerminalCommand}
            onAuthFailure={handleAuthFailure}
            onMessage={setSystemMessage}
            onError={setSystemError}
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
        </Suspense>
        {saveOtpModalOpen ? (
          <div className="overlay" onClick={(event) => event.target === event.currentTarget && !isBusy && setSaveOtpModalOpen(false)}>
            <div className="confirm-window">
              <div className="terminal-header">
                <div className="terminal-dots">
                  <span className="td-red" onClick={() => !isBusy && setSaveOtpModalOpen(false)} />
                  <span className="td-yellow" />
                  <span className="td-green" />
                </div>
                <span className="terminal-title">
                  {pendingBotAction
                    ? `confirm 2fa for bot ${pendingBotAction}`
                    : pendingTwoFactorRotate
                      ? 'confirm 2fa to rotate'
                      : 'confirm 2fa for save'}
                </span>
              </div>
              <div className="confirm-body">
                <div className="confirm-total">
                  <span>One-time confirmation needed</span>
                  <strong>2FA</strong>
                  <small>
                    {pendingBotAction
                      ? 'Enter authenticator or backup code to control the bot.'
                      : pendingTwoFactorRotate
                        ? 'Enter current authenticator or backup code to rotate 2FA setup.'
                        : 'Enter authenticator code or backup code to apply settings changes.'}
                  </small>
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
                  <button
                    className="ghost-btn"
                    disabled={isBusy}
                    onClick={() => {
                      setSaveOtpModalOpen(false);
                      setPendingBotAction(null);
                      setPendingTwoFactorRotate(false);
                    }}
                  >
                    Cancel
                  </button>
                  <button className="primary-btn" disabled={isBusy} onClick={handleConfirmSaveWithOtp}>
                    {isBusy ? 'Confirming...' : 'Confirm'}
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
