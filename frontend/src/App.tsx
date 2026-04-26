import React, { useState, useEffect, useRef, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Activity,
  Terminal as TerminalIcon,
  Shield,
  Zap,
  Radio,
  X,
  Send,
  TrendingUp,
  TrendingDown,
  RefreshCw,
  Brain,
  AlertTriangle,
  CheckCircle,
  Clock,
  Filter,
} from 'lucide-react';
import './App.css';
import { useDashboardStream, sendTerminalCommand } from './services/api';
import { useTelemetry } from './hooks/useTelemetry';
import PairsPanel from './components/PairsPanel';
import PositionsPanel from './components/PositionsPanel';

// ─── Helpers ────────────────────────────────────────────────────────────────

function fmtCurrency(val: number | null | undefined): string {
  if (val === null || val === undefined) return '—';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(val);
}

function fmtPct(val: number | null | undefined, decimals = 1): string {
  if (val === null || val === undefined) return '—';
  return `${(val * 100).toFixed(decimals)}%`;
}

function getRegimeStyle(regime: string): { color: string; bg: string } {
  switch (regime) {
    case 'TRENDING_UP':   return { color: 'var(--green)',  bg: 'var(--green-muted)' };
    case 'TRENDING_DOWN': return { color: 'var(--red)',    bg: 'var(--red-muted)'   };
    case 'VOLATILE':      return { color: 'var(--yellow)', bg: 'var(--yellow-muted)' };
    default:              return { color: 'var(--accent)', bg: 'var(--accent-muted)' };
  }
}

function getRegimeIcon(regime: string) {
  switch (regime) {
    case 'TRENDING_UP':   return <TrendingUp size={16} />;
    case 'TRENDING_DOWN': return <TrendingDown size={16} />;
    case 'VOLATILE':      return <AlertTriangle size={16} />;
    default:              return <RefreshCw size={16} />;
  }
}

function getVerdictColor(verdict: string): string {
  switch (verdict) {
    case 'BULLISH': return 'var(--green)';
    case 'BEARISH': return 'var(--red)';
    case 'VETO':    return 'var(--yellow)';
    default:        return 'var(--accent)';
  }
}

function getSignalBadge(status: string): string {
  const s = status.toUpperCase();
  if (s.includes('EXECUTING'))           return 'badge-yellow';
  if (s.includes('APPROVED') || s.includes('FILLED')) return 'badge-green';
  if (s.includes('VETO') || s.includes('REJECTED'))   return 'badge-red';
  return 'badge-blue';
}

function getStageDotColor(stage: string | undefined): string {
  if (!stage) return 'blue';
  const s = stage.toLowerCase();
  if (s.includes('execut')) return 'yellow';
  if (s.includes('error') || s.includes('fail')) return 'red';
  return 'green';
}

function formatUptime(startIso: string | undefined): string {
  if (!startIso) return '—';
  const start = new Date(startIso).getTime();
  if (Number.isNaN(start)) return '—';
  const seconds = Math.max(0, Math.floor((Date.now() - start) / 1000));
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function getModeBadgeClass(mode: string | undefined): string {
  switch (mode) {
    case 'LIVE':  return 'mode-badge mode-live';
    case 'PAPER': return 'mode-badge mode-paper';
    case 'DEV':   return 'mode-badge mode-dev';
    default:      return 'mode-badge';
  }
}

type VerdictFilter = 'ALL' | 'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'VETO';
const VERDICT_FILTERS: VerdictFilter[] = ['ALL', 'BULLISH', 'BEARISH', 'NEUTRAL', 'VETO'];

// ─── App ─────────────────────────────────────────────────────────────────────

const App: React.FC = () => {
  const urlParams = new URLSearchParams(window.location.search);
  const token = urlParams.get('token') ?? '';

  const { data, error } = useDashboardStream(token);
  const { isConnected, risk, thoughts, botState } = useTelemetry(token);

  const [terminalOpen, setTerminalOpen] = useState(false);
  const [terminalInput, setTerminalInput] = useState('');
  const [verdictFilter, setVerdictFilter] = useState<VerdictFilter>('ALL');
  const [, setNowTick] = useState(0); // forces uptime re-render every 30s
  const terminalEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll terminal
  useEffect(() => {
    if (terminalEndRef.current && terminalOpen) {
      terminalEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [data?.terminal_messages, terminalOpen]);

  // Re-render uptime every 30s
  useEffect(() => {
    const id = setInterval(() => setNowTick((n) => n + 1), 30000);
    return () => clearInterval(id);
  }, []);

  const filteredThoughts = useMemo(() => {
    if (verdictFilter === 'ALL') return thoughts;
    return thoughts.filter((t) => t.verdict === verdictFilter);
  }, [thoughts, verdictFilter]);

  const handleSend = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!terminalInput.trim()) return;
    try {
      await sendTerminalCommand(terminalInput, token);
      setTerminalInput('');
    } catch (err) {
      console.error('Command failed:', err);
    }
  };

  // ── Guards ────────────────────────────────────────────────────────────────
  if (!token) {
    return (
      <div className="access-denied">
        <Shield size={32} style={{ color: 'var(--text-subtle)' }} />
        <span>Access denied — no <code>?token=</code> parameter provided.</span>
      </div>
    );
  }

  // ── Derived values ────────────────────────────────────────────────────────
  const stage           = data?.stage ?? botState ?? 'Initializing';
  const usagePct        = data?.metrics?.daily_usage_pct ?? 0;
  const dailyProfit     = data?.metrics?.daily_profit;
  const accuracy        = data?.global_accuracy ?? 0;
  const regime          = data?.market_regime?.regime ?? 'STABLE';
  const regimeConf      = data?.market_regime?.confidence ?? 0;
  const regimeStyle     = getRegimeStyle(regime);
  const accuracyColor   = accuracy > 0.6 ? 'var(--green)' : accuracy < 0.4 ? 'var(--red)' : 'var(--yellow)';
  const mode            = data?.runtime?.mode;
  const botStartTime    = data?.runtime?.bot_start_time ?? data?.bot_start_time;
  const uptime          = formatUptime(botStartTime);

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="app">

      {/* ── HEADER ──────────────────────────────────────────────────────── */}
      <header className="header">
        <div className="header-left">
          <div className="logo">
            <div className="logo-mark">
              <Activity size={14} color="white" />
            </div>
            Alpha Arbitrage Elite
          </div>

          <div className="stage-badge">
            <span className={`pulse-dot ${getStageDotColor(stage)}`} />
            {stage.toUpperCase()}
          </div>

          {mode && (
            <span
              className={getModeBadgeClass(mode)}
              title={
                data?.runtime?.live_capital_danger
                  ? 'LIVE CAPITAL DANGER is enabled'
                  : `${mode} mode`
              }
            >
              {mode}
            </span>
          )}
        </div>

        <div className="header-right">
          <div className="status-pill" title={botStartTime ?? ''}>
            <Clock size={11} />
            {uptime}
          </div>

          <div className="divider" />

          <div className="status-pill">
            <span className={`pulse-dot ${isConnected ? 'green' : 'yellow'}`} />
            {isConnected ? 'Live' : 'Reconnecting'}
          </div>

          <div className="divider" />

          <button className="btn btn-default" onClick={() => setTerminalOpen(true)}>
            <TerminalIcon size={12} />
            Terminal
          </button>
        </div>
      </header>

      {/* ── KPI STRIP ───────────────────────────────────────────────────── */}
      <div className="kpi-strip">
        <div className="kpi-item">
          <div className="kpi-label">Daily Budget</div>
          <div className="kpi-value">{fmtCurrency(data?.metrics?.daily_budget)}</div>
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{
                width: `${Math.min(usagePct, 100)}%`,
                background: usagePct > 90 ? 'var(--red)' : usagePct > 70 ? 'var(--yellow)' : 'var(--accent)',
              }}
            />
          </div>
          <div className="kpi-sub">{usagePct.toFixed(1)}% utilized</div>
        </div>

        <div className="kpi-item">
          <div className="kpi-label">Capital Deployed</div>
          <div className="kpi-value">{fmtCurrency(data?.metrics?.total_invested)}</div>
        </div>

        <div className="kpi-item">
          <div className="kpi-label">Daily P&L</div>
          <div
            className={`kpi-value ${
              dailyProfit == null ? 'muted' : dailyProfit >= 0 ? 'positive' : 'negative'
            }`}
          >
            {fmtCurrency(dailyProfit)}
          </div>
        </div>

        <div className="kpi-item">
          <div className="kpi-label">Strategy Accuracy</div>
          <div
            className={`kpi-value ${
              accuracy > 0.6 ? 'positive' : accuracy < 0.4 ? 'negative' : ''
            }`}
          >
            {(accuracy * 100).toFixed(1)}%
          </div>
          <div className="kpi-sub">
            {accuracy > 0.6 ? 'Optimal' : accuracy < 0.4 ? 'Caution active' : 'Nominal'}
          </div>
        </div>
      </div>

      {/* ── MAIN ────────────────────────────────────────────────────────── */}
      <div className="main">

        {/* ── SIDEBAR ─────────────────────────────────────────────────── */}
        <aside className="sidebar">

          {/* Risk Telemetry */}
          <div className="section">
            <div className="section-title">
              <Shield size={12} />
              Risk Telemetry
            </div>
            <div className="risk-grid">
              <div className="risk-item">
                <div className="risk-label">Risk Mult.</div>
                <div
                  className="risk-value"
                  style={{ color: (risk?.risk_multiplier ?? 1) < 0.5 ? 'var(--yellow)' : 'var(--text)' }}
                >
                  {(risk?.risk_multiplier ?? 1).toFixed(2)}×
                </div>
              </div>
              <div className="risk-item">
                <div className="risk-label">Max Drawdown</div>
                <div
                  className="risk-value"
                  style={{ color: (risk?.max_drawdown_pct ?? 0) > 0.1 ? 'var(--red)' : 'var(--text)' }}
                >
                  {((risk?.max_drawdown_pct ?? 0) * 100).toFixed(1)}%
                </div>
              </div>
              <div className="risk-item">
                <div className="risk-label">L2 Entropy</div>
                <div
                  className="risk-value"
                  style={{ color: (risk?.l2_entropy ?? 0) > 0.7 ? 'var(--yellow)' : 'var(--text)' }}
                >
                  {(risk?.l2_entropy ?? 0).toFixed(3)}
                </div>
              </div>
              <div className="risk-item">
                <div className="risk-label">Volatility</div>
                <div
                  className="risk-value"
                  style={{
                    fontSize: '13px',
                    color: risk?.volatility_status === 'HIGH_VOLATILITY' ? 'var(--red)' : 'var(--green)',
                  }}
                >
                  {risk?.volatility_status === 'HIGH_VOLATILITY' ? 'High' : 'Normal'}
                </div>
              </div>
            </div>
          </div>

          {/* Market Regime */}
          <div className="section">
            <div className="section-title">
              <Radio size={12} />
              Market Regime
            </div>
            <div className="regime-card">
              <div
                className="regime-icon"
                style={{ background: regimeStyle.bg, color: regimeStyle.color }}
              >
                {getRegimeIcon(regime)}
              </div>
              <div>
                <div className="regime-name">
                  {regime.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, c => c.toUpperCase())}
                </div>
                <div className="regime-confidence">
                  Confidence: {(regimeConf * 100).toFixed(1)}%
                </div>
              </div>
            </div>
          </div>

          {/* Model Intelligence */}
          <div className="section">
            <div className="section-title">
              <Brain size={12} />
              Model Intelligence
            </div>
            <div className="accuracy-row">
              <span>Historical accuracy</span>
              <span className="accuracy-value" style={{ color: accuracyColor }}>
                {(accuracy * 100).toFixed(1)}%
              </span>
            </div>
            <div className="progress-bar" style={{ height: '6px' }}>
              <div
                className="progress-fill"
                style={{ width: `${accuracy * 100}%`, background: accuracyColor }}
              />
            </div>
            <div className="kpi-sub" style={{ marginTop: '8px' }}>
              {accuracy > 0.6
                ? '✓ Optimal — full Kelly sizing active'
                : accuracy < 0.4
                ? '⚠ Caution — penalty multiplier engaged'
                : 'Nominal operating range'}
            </div>
          </div>

        </aside>

        {/* ── CONTENT ─────────────────────────────────────────────────── */}
        <div className="content">
          <div className="content-grid">

            {/* Top-left: Active Signals */}
            <div className="panel">
              <div className="panel-header">
                <Zap size={12} />
                Active Signals
                <span className="panel-count">{data?.active_signals?.length ?? 0}</span>
              </div>
              <div className="panel-body">
                <AnimatePresence>
                  {data?.active_signals && data.active_signals.length > 0 ? (
                    data.active_signals.map((sig, idx) => (
                      <motion.div
                        key={`${sig.ticker_a}-${sig.ticker_b}-${idx}`}
                        className="signal-card"
                        initial={{ opacity: 0, y: -6 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0 }}
                        layout
                      >
                        <div className="signal-top">
                          <span className="signal-pair">
                            {sig.ticker_a} / {sig.ticker_b}
                          </span>
                          <span className={`badge ${getSignalBadge(sig.status)}`}>
                            {sig.status}
                          </span>
                        </div>
                        <div className="signal-meta">
                          <span>
                            Z-score:{' '}
                            <span className="z-score-value">{sig.z_score.toFixed(3)}</span>
                          </span>
                        </div>
                      </motion.div>
                    ))
                  ) : (
                    <div className="empty-state">
                      <Radio size={28} style={{ opacity: 0.3 }} />
                      <span>Scanning market for signals…</span>
                    </div>
                  )}
                </AnimatePresence>
              </div>
            </div>

            {/* Top-right: Open Positions */}
            <PositionsPanel token={token} />

            {/* Bottom (full width): Agent Reasoning Log */}
            <div className="panel grid-span-2">
              <div className="panel-header">
                <Brain size={12} />
                Agent Reasoning Log
                <span className="panel-count">{filteredThoughts.length}</span>
                <div className="verdict-filter">
                  <Filter size={11} />
                  {VERDICT_FILTERS.map((v) => (
                    <button
                      key={v}
                      className={`verdict-chip ${verdictFilter === v ? 'active' : ''}`}
                      style={
                        verdictFilter === v && v !== 'ALL'
                          ? {
                              color: getVerdictColor(v),
                              borderColor: getVerdictColor(v),
                            }
                          : undefined
                      }
                      onClick={() => setVerdictFilter(v)}
                    >
                      {v}
                    </button>
                  ))}
                </div>
              </div>
              <div className="panel-body">
                <AnimatePresence initial={false}>
                  {filteredThoughts.length > 0 ? (
                    [...filteredThoughts]
                      .reverse()
                      .slice(0, 60)
                      .map((t, idx) => (
                        <motion.div
                          key={`${t.signal_id ?? 'x'}-${idx}`}
                          className="thought-item"
                          style={{ borderLeftColor: getVerdictColor(t.verdict) }}
                          initial={{ opacity: 0, x: -6 }}
                          animate={{ opacity: 1, x: 0 }}
                          exit={{ opacity: 0 }}
                        >
                          <div className="thought-header">
                            <span
                              className="thought-agent"
                              style={{ color: getVerdictColor(t.verdict) }}
                            >
                              {t.agent_name}
                            </span>
                            <span
                              className="thought-verdict"
                              style={{
                                background: `${getVerdictColor(t.verdict)}20`,
                                color: getVerdictColor(t.verdict),
                              }}
                            >
                              {t.verdict}
                            </span>
                            {t.signal_id && (
                              <span className="thought-id">
                                {t.signal_id.slice(0, 8)}
                              </span>
                            )}
                          </div>
                          <div className="thought-text">{t.thought}</div>
                        </motion.div>
                      ))
                  ) : (
                    <div className="empty-state">
                      <Brain size={28} style={{ opacity: 0.3 }} />
                      <span>
                        {thoughts.length > 0
                          ? `No thoughts match filter "${verdictFilter}"`
                          : 'No agent activity yet'}
                      </span>
                    </div>
                  )}
                </AnimatePresence>
              </div>
            </div>

          </div>
        </div>

        {/* ── PAIRS RAIL (right) ──────────────────────────────────────── */}
        <aside className="pairs-rail">
          <PairsPanel token={token} />
        </aside>
      </div>

      {/* Terminal Modal */}
      <AnimatePresence>
        {terminalOpen && (
          <motion.div
            className="overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={(e) => e.target === e.currentTarget && setTerminalOpen(false)}
          >
            <motion.div
              className="terminal-window"
              initial={{ scale: 0.96, opacity: 0, y: 10 }}
              animate={{ scale: 1, opacity: 1, y: 0 }}
              exit={{ scale: 0.96, opacity: 0, y: 10 }}
              transition={{ type: 'spring', stiffness: 320, damping: 32 }}
            >
              <div className="terminal-header">
                <div className="terminal-dots">
                  <span className="td-red" onClick={() => setTerminalOpen(false)} />
                  <span className="td-yellow" />
                  <span className="td-green" />
                </div>
                <span className="terminal-title">arbi_elite — terminal</span>
                <button className="terminal-close-btn" onClick={() => setTerminalOpen(false)}>
                  <X size={14} />
                </button>
              </div>

              <div className="terminal-body">
                {data?.terminal_messages?.map((msg, idx) => (
                  <React.Fragment key={idx}>
                    <div className="terminal-line">
                      <span
                        className="terminal-line-type"
                        style={{
                          color:
                            msg.type === 'BOT'
                              ? 'var(--accent)'
                              : msg.type === 'USER'
                              ? 'var(--green)'
                              : 'var(--text-muted)',
                        }}
                      >
                        [{msg.type}]
                      </span>
                      <span className="terminal-line-text">{msg.text}</span>
                    </div>
                    {msg.metadata?.type === 'approval' && (
                      <button
                        className="approval-btn"
                        onClick={() =>
                          sendTerminalCommand(`/approve ${msg.metadata.correlation_id}`, token)
                        }
                      >
                        <CheckCircle size={12} />
                        Approve {msg.metadata.correlation_id}
                      </button>
                    )}
                  </React.Fragment>
                ))}
                <div ref={terminalEndRef} />
              </div>

              <form className="terminal-footer" onSubmit={handleSend}>
                <span className="terminal-prompt">$</span>
                <input
                  className="terminal-input"
                  value={terminalInput}
                  onChange={(e) => setTerminalInput(e.target.value)}
                  placeholder="Enter command..."
                  autoFocus
                />
                <button type="submit" className="terminal-send-btn">
                  <Send size={14} />
                </button>
              </form>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Error Toast */}
      <AnimatePresence>
        {error && (
          <motion.div
            className="toast-error"
            initial={{ x: 80, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 80, opacity: 0 }}
          >
            <AlertTriangle size={14} />
            {error}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default App;
