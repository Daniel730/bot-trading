import React, { useEffect, useState, useCallback } from 'react';
import { Briefcase, RefreshCw, ArrowUp, ArrowDown } from 'lucide-react';
import { fetchOpenPositions, type OpenPosition } from '../services/api';

interface PositionsPanelProps {
  token: string;
  sessionToken: string;
}

const fmt = (val: number | null | undefined, decimals = 2): string => {
  if (val === null || val === undefined || Number.isNaN(val)) return '—';
  return val.toFixed(decimals);
};

const PositionsPanel: React.FC<PositionsPanelProps> = ({ token, sessionToken }) => {
  const [positions, setPositions] = useState<OpenPosition[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchOpenPositions(token, sessionToken);
      setPositions(data.positions || []);
    } catch (err) {
      console.error('Failed to fetch positions:', err);
    } finally {
      setLoading(false);
    }
  }, [token, sessionToken]);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 10000);
    return () => clearInterval(id);
  }, [refresh]);

  return (
    <div className="panel">
      <div className="panel-header">
        <Briefcase size={12} />
        Open Positions
        <span className="panel-count">{positions.length}</span>
        <button
          className="panel-action-btn"
          title="Refresh"
          onClick={refresh}
          disabled={loading}
        >
          <RefreshCw size={11} className={loading ? 'spin' : ''} />
        </button>
      </div>
      <div className="panel-body">
        {positions.length === 0 ? (
          <div className="empty-state">
            <Briefcase size={28} style={{ opacity: 0.3 }} />
            <span>{loading ? 'Loading positions…' : 'No open positions'}</span>
          </div>
        ) : (
          <div className="position-list">
            {positions.map((pos) => {
              const pnlColor =
                pos.pnl > 0
                  ? 'var(--green)'
                  : pos.pnl < 0
                  ? 'var(--red)'
                  : 'var(--text-muted)';
              const direction =
                pos.side_a === 'SELL' ? 'Short / Long' : 'Long / Short';
              return (
                <div className="position-card" key={pos.signal_id}>
                  <div className="position-top">
                    <span className="signal-pair">
                      {pos.ticker_a} / {pos.ticker_b}
                    </span>
                    <span
                      className="position-pnl"
                      style={{ color: pnlColor }}
                    >
                      {pos.pnl >= 0 ? <ArrowUp size={11} /> : <ArrowDown size={11} />}
                      ${fmt(pos.pnl, 2)}
                    </span>
                  </div>
                  <div className="position-meta-row">
                    <span className="badge badge-blue">{direction}</span>
                    <span className="position-meta-text">
                      cost ${fmt(pos.cost_basis, 2)} · now ${fmt(pos.current_value, 2)}
                    </span>
                  </div>
                  <div className="position-legs">
                    <div className="position-leg">
                      <div className="position-leg-header">
                        <span className="position-leg-side" data-side={pos.side_a}>
                          {pos.side_a}
                        </span>
                        <span className="position-leg-ticker">{pos.ticker_a}</span>
                      </div>
                      <div className="position-leg-prices">
                        {fmt(pos.entry_a)} → {fmt(pos.current_a)}
                      </div>
                    </div>
                    <div className="position-leg">
                      <div className="position-leg-header">
                        <span className="position-leg-side" data-side={pos.side_b}>
                          {pos.side_b}
                        </span>
                        <span className="position-leg-ticker">{pos.ticker_b}</span>
                      </div>
                      <div className="position-leg-prices">
                        {fmt(pos.entry_b)} → {fmt(pos.current_b)}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export default PositionsPanel;
