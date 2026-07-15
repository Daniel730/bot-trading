import React from 'react';
import type { SummaryResponse, OpenPosition } from '../services/api';
import type { TelemetryRisk, TelemetryThought } from '../hooks/useTelemetry';
import { SectionHeader } from '../components/UIHelpers';
import { formatCompact, formatCurrency, formatDateTime, formatPercent, getTrendClass } from '../utils/formatters';
import IntelligenceHub from '../components/IntelligenceHub';

interface OverviewPageProps {
  summary: SummaryResponse | null;
  positions: OpenPosition[];
  risk: TelemetryRisk | null;
  recentThoughts: TelemetryThought[];
  marketRegime?: string | null;
  marketRegimeConfidence?: number | null;
  globalAccuracy?: number | null;
}

const OverviewPage: React.FC<OverviewPageProps> = ({
  summary,
  positions,
  risk,
  recentThoughts,
  marketRegime,
  marketRegimeConfidence,
  globalAccuracy,
}) => {
  return (
    <>
      <SectionHeader title="Real-Time Overview" subtitle="Status strip and recent activity. Charts live under Analytics." />

      {(marketRegime || risk) && (
        <IntelligenceHub
          regime={marketRegime ?? 'STABLE'}
          confidence={marketRegimeConfidence}
          accuracy={globalAccuracy}
        />
      )}

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
        <div className="metric-card">
          <span>Profit Today</span>
          <strong className={getTrendClass(summary?.profit_today)}>{formatCurrency(summary?.profit_today)}</strong>
          <small>See Analytics for cumulative P&L</small>
        </div>
        <div className="metric-card">
          <span>Open Positions</span>
          <strong>{summary?.open_positions ?? positions.length}</strong>
          <small>{summary?.open_signals ?? 0} open signals</small>
        </div>
      </div>

      <div className="card-grid two-up">
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

        <section className="panel">
          <SectionHeader title="Risk Telemetry" subtitle="Live guardrails from the telemetry stream." />
          <div className="risk-grid">
            <div><span>Risk Mult.</span><strong>{formatCompact(risk?.risk_multiplier)}</strong></div>
            <div><span>Drawdown</span><strong>{formatPercent(risk?.max_drawdown_pct)}</strong></div>
            <div><span>L2 Entropy</span><strong>{formatCompact(risk?.l2_entropy)}</strong></div>
            <div><span>Volatility</span><strong>{risk?.volatility_status ?? '—'}</strong></div>
          </div>
        </section>
      </div>

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
    </>
  );
};

export default OverviewPage;
