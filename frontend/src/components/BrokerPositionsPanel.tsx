import React, { useEffect, useState, useCallback } from 'react';
import { Wallet, RefreshCw, ArrowUp, ArrowDown } from 'lucide-react';
import { fetchBrokerPositions, type BrokerPosition } from '../services/api';
import { formatCurrency } from '../utils/formatters';

interface BrokerPositionsPanelProps {
  token: string;
  sessionToken: string;
}

const qtyFmt = (v: number | null): string => {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  // Crypto quantities can be tiny; show enough precision without noise.
  return Math.abs(v) >= 1 ? v.toFixed(4) : v.toPrecision(4);
};

const pctFmt = (v: number | null): string => {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return `${(v * 100).toFixed(2)}%`;
};

const BrokerPositionsPanel: React.FC<BrokerPositionsPanelProps> = ({ token, sessionToken }) => {
  const [positions, setPositions] = useState<BrokerPosition[]>([]);
  const [provider, setProvider] = useState<string>('');
  const [totalValue, setTotalValue] = useState<number>(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchBrokerPositions(token, sessionToken);
      setPositions(data.positions || []);
      setProvider(data.provider || '');
      setTotalValue(data.total_market_value || 0);
      setError(data.error ?? null);
    } catch (err) {
      console.error('Failed to fetch broker positions:', err);
      setError(err instanceof Error ? err.message : 'Failed to load broker positions');
    } finally {
      setLoading(false);
    }
  }, [token, sessionToken]);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 15000);
    return () => clearInterval(id);
  }, [refresh]);

  return (
    <div className="panel">
      <div className="panel-header">
        <Wallet size={12} />
        Broker Account Holdings{provider ? ` · ${provider}` : ''}
        <span className="panel-count">{positions.length}</span>
        {totalValue > 0 && (
          <span className="position-meta-text" style={{ marginLeft: 'auto', marginRight: 8 }}>
            {formatCurrency(totalValue)} total
          </span>
        )}
        <button className="panel-action-btn" title="Refresh" onClick={refresh} disabled={loading}>
          <RefreshCw size={11} className={loading ? 'spin' : ''} />
        </button>
      </div>
      <div className="panel-body">
        {error ? (
          <div className="empty-state">
            <Wallet size={28} style={{ opacity: 0.3 }} />
            <span style={{ color: 'var(--red)' }}>Could not load broker holdings: {error}</span>
          </div>
        ) : positions.length === 0 ? (
          <div className="empty-state">
            <Wallet size={28} style={{ opacity: 0.3 }} />
            <span>{loading ? 'Loading holdings…' : 'No broker holdings'}</span>
          </div>
        ) : (
          <div className="position-list">
            {positions.map((pos) => {
              const upl = pos.unrealized_pl ?? 0;
              const pnlColor = upl > 0 ? 'var(--green)' : upl < 0 ? 'var(--red)' : 'var(--text-muted)';
              return (
                <div className="position-card" key={pos.ticker ?? Math.random()}>
                  <div className="position-top">
                    <span className="signal-pair">{pos.ticker ?? '—'}</span>
                    <span className="position-pnl" style={{ color: pnlColor }}>
                      {upl >= 0 ? <ArrowUp size={11} /> : <ArrowDown size={11} />}
                      {formatCurrency(pos.unrealized_pl)} ({pctFmt(pos.unrealized_pl_pct)})
                    </span>
                  </div>
                  <div className="position-meta-row">
                    <span className="badge badge-blue">{qtyFmt(pos.quantity)} units</span>
                    <span className="position-meta-text">
                      avg {formatCurrency(pos.avg_price)} · now {formatCurrency(pos.current_price)} · mkt {formatCurrency(pos.market_value)}
                    </span>
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

export default BrokerPositionsPanel;
