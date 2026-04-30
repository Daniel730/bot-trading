import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  RefreshCw,
  ShoppingCart,
  SlidersHorizontal,
  Wallet,
  X,
} from 'lucide-react';
import {
  buyWalletRecommendations,
  fetchWalletRecommendations,
  type T212WalletRecommendation,
  type T212WalletRecommendationResponse,
  type T212WalletRecommendationBuyResponse,
} from '../services/api';

interface WalletPanelProps {
  token: string;
  sessionToken: string;
}

const formatCurrency = (value: number | null | undefined) => {
  if (value === null || value === undefined) return '--';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
  }).format(value);
};

const formatPercent = (value: number | null | undefined) => {
  if (value === null || value === undefined) return '--';
  return `${(value * 100).toFixed(2)}%`;
};

const formatZ = (value: number | null | undefined) => {
  if (value === null || value === undefined) return '--';
  return value.toFixed(2);
};

const categoryLabel = (category: T212WalletRecommendation['category']) => {
  if (category === 'coint') return 'COINT';
  if (category === 'manual_override') return 'Manual override';
  return 'BROKEN eligible';
};

const WalletPanel: React.FC<WalletPanelProps> = ({ token, sessionToken }) => {
  const [budget, setBudget] = useState('100');
  const [includeBroken, setIncludeBroken] = useState(false);
  const [skipOwned, setSkipOwned] = useState(true);
  const [skipPending, setSkipPending] = useState(true);
  const [plan, setPlan] = useState<T212WalletRecommendationResponse | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [buying, setBuying] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [buyResult, setBuyResult] = useState<T212WalletRecommendationBuyResponse | null>(null);

  const budgetValue = Number(budget);

  const refresh = useCallback(async () => {
    setError(null);
    setOk(null);
    setBuyResult(null);
    if (!Number.isFinite(budgetValue) || budgetValue <= 0) {
      setError('Enter a positive budget.');
      return;
    }
    setLoading(true);
    try {
      const data = await fetchWalletRecommendations(token, sessionToken, {
        budget: budgetValue,
        includeBroken,
        skipOwned,
        skipPending,
      });
      setPlan(data);
      setSelected(new Set(data.recommendations.map((item) => item.ticker)));
    } catch (err) {
      const e = err as Error;
      setError(e.message || 'Failed to calculate wallet recommendations.');
      setPlan(null);
      setSelected(new Set<string>());
    } finally {
      setLoading(false);
    }
  }, [budgetValue, includeBroken, sessionToken, skipOwned, skipPending, token]);

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, 30000);
    return () => window.clearInterval(id);
  }, [refresh]);

  const selectedRecommendations = useMemo(
    () => (plan?.recommendations || []).filter((item) => selected.has(item.ticker)),
    [plan?.recommendations, selected],
  );

  const selectedSuggestedTotal = useMemo(
    () => selectedRecommendations.reduce((sum, item) => sum + (item.suggested_amount || 0), 0),
    [selectedRecommendations],
  );

  const toggleTicker = (ticker: string) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(ticker)) next.delete(ticker);
      else next.add(ticker);
      return next;
    });
  };

  const toggleAll = () => {
    if (!plan?.recommendations.length) return;
    setSelected((current) => (
      current.size === plan.recommendations.length
        ? new Set<string>()
        : new Set(plan.recommendations.map((item) => item.ticker))
    ));
  };

  const confirmBuy = async () => {
    setBuying(true);
    setError(null);
    setOk(null);
    setBuyResult(null);
    try {
      const result = await buyWalletRecommendations(token, sessionToken, {
        budget: budgetValue,
        includeBroken,
        tickers: selectedRecommendations.map((item) => item.ticker),
        skipOwned,
        skipPending,
      });
      setBuyResult(result);
      setOk(`${result.message} ${result.orders.filter((order) => order.status === 'ok').length} orders accepted.`);
      setConfirmOpen(false);
      await refresh();
    } catch (err) {
      const e = err as Error;
      setError(e.message || 'Failed to buy wallet recommendations.');
    } finally {
      setBuying(false);
    }
  };

  const buyDisabled = buying;

  return (
    <div className="wallet-page">
      <section className="panel wallet-control-panel">
        <div className="wallet-control-main">
          <div className="wallet-title">
            <Wallet size={18} />
            <div>
              <strong>Today&apos;s Stock Plan</strong>
              <span>{plan ? `${plan.recommended_tickers.length} recommended / ${plan.skipped.length} skipped` : 'Waiting for wallet state'}</span>
            </div>
          </div>

          <label className="wallet-budget-field wallet-budget-wide">
            <span>Budget</span>
            <input
              type="number"
              min="1"
              step="1"
              value={budget}
              onChange={(event) => setBudget(event.target.value)}
            />
          </label>
        </div>

        <div className="wallet-toggle-grid">
          <label className="wallet-toggle">
            <input
              type="checkbox"
              checked={includeBroken}
              onChange={(event) => setIncludeBroken(event.target.checked)}
            />
            <span>Flag BROKEN-eligible mode</span>
          </label>
          <label className="wallet-toggle">
            <input
              type="checkbox"
              checked={skipOwned}
              onChange={(event) => setSkipOwned(event.target.checked)}
            />
            <span>Skip owned</span>
          </label>
          <label className="wallet-toggle">
            <input
              type="checkbox"
              checked={skipPending}
              onChange={(event) => setSkipPending(event.target.checked)}
            />
            <span>Skip pending</span>
          </label>
        </div>

        <div className="wallet-action-row">
          <button className="ghost-btn" disabled={loading} onClick={refresh}>
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
            Refresh Plan
          </button>
          <button className="primary-btn" disabled={buyDisabled} onClick={() => setConfirmOpen(true)}>
            <ShoppingCart size={14} />
            Buy Selected
          </button>
        </div>
      </section>

      {error ? (
        <div className="banner error">
          <AlertTriangle size={14} /> {error}
        </div>
      ) : null}
      {ok ? (
        <div className="banner success">
          <CheckCircle2 size={14} /> {ok}
        </div>
      ) : null}
      {plan?.warning ? (
        <div className="banner warning">
          <AlertTriangle size={14} />
          {plan.warning}
        </div>
      ) : null}
      {plan?.cash_limited ? (
        <div className="banner warning">
          <AlertTriangle size={14} />
          Budget exceeds bot-calculated spendable T212 cash. Orders will still be attempted.
        </div>
      ) : null}

      <div className="card-grid metrics wallet-metrics">
        <div className="metric-card">
          <span>Usable Budget</span>
          <strong>{formatCurrency(plan?.usable_budget)}</strong>
          <small>{plan?.mode ? `${plan.mode.toUpperCase()} T212` : 'T212'}</small>
        </div>
        <div className="metric-card">
          <span>Spendable Cash</span>
          <strong>{formatCurrency(plan?.spendable_cash)}</strong>
          <small>After pending BUY orders</small>
        </div>
        <div className="metric-card">
          <span>COINT Pairs</span>
          <strong>{plan?.coint_pairs ?? '--'}</strong>
          <small>Included by default</small>
        </div>
        <div className="metric-card">
          <span>BROKEN Eligible</span>
          <strong>{plan?.broken_eligible_pairs ?? '--'}</strong>
          <small>{includeBroken ? 'Flagged' : 'Included'}</small>
        </div>
      </div>

      <section className="panel">
        <div className="panel-header">
          <SlidersHorizontal size={13} />
          Recommended Buys
          <span className="panel-count">{plan?.recommendations.length ?? 0}</span>
          <button className="panel-action-btn wallet-select-all" title="Toggle selection" onClick={toggleAll}>
            {selectedRecommendations.length}/{plan?.recommendations.length ?? 0}
          </button>
        </div>

        {!plan || loading ? (
          <div className="empty-state">
            <RefreshCw size={28} className={loading ? 'spin' : ''} style={{ opacity: 0.35 }} />
            <span>{loading ? 'Calculating recommendations...' : 'No wallet plan loaded'}</span>
          </div>
        ) : plan.recommendations.length === 0 ? (
          <div className="empty-state">
            <Wallet size={28} style={{ opacity: 0.35 }} />
            <span>{plan.message}</span>
          </div>
        ) : (
          <div className="table-wrap">
            <table className="wallet-table">
              <thead>
                <tr>
                  <th />
                  <th>Ticker</th>
                  <th>Signal</th>
                  <th>Pairs</th>
                  <th>Score</th>
                  <th>Allocation</th>
                </tr>
              </thead>
              <tbody>
                {plan.recommendations.map((item) => (
                  <tr key={item.ticker}>
                    <td>
                      <input
                        type="checkbox"
                        checked={selected.has(item.ticker)}
                        onChange={() => toggleTicker(item.ticker)}
                        aria-label={`Select ${item.ticker}`}
                      />
                    </td>
                    <td>
                      <strong>{item.ticker}</strong>
                      <div className="muted">{item.t212_ticker}</div>
                    </td>
                    <td>
                      <span className={`badge ${item.category === 'coint' ? 'badge-green' : 'badge-blue'}`}>
                        {categoryLabel(item.category)}
                      </span>
                      <div className="muted">z {formatZ(item.max_abs_z_score)} · cost {formatPercent(item.estimated_cost_pct)}</div>
                    </td>
                    <td>
                      <div className="wallet-pair-list">
                        {item.pairs.slice(0, 3).map((pair) => (
                          <span key={pair.id}>{pair.ticker_a}/{pair.ticker_b}</span>
                        ))}
                        {item.pairs.length > 3 ? <em>+{item.pairs.length - 3}</em> : null}
                      </div>
                    </td>
                    <td>{item.score.toFixed(1)}</td>
                    <td>
                      <strong>{formatCurrency(item.suggested_amount)}</strong>
                      <div className="muted">rank {item.rank ?? '--'}</div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {plan?.skipped.length ? (
        <section className="panel">
          <div className="panel-header">
            <AlertTriangle size={13} />
            Skipped
            <span className="panel-count">{plan.skipped.length}</span>
          </div>
          <div className="wallet-skip-list">
            {plan.skipped.slice(0, 8).map((item) => (
              <div className="wallet-skip-row" key={`${item.ticker}-${item.reason}`}>
                <strong>{item.ticker}</strong>
                <span>{item.reason.replace('_', ' ')}</span>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {buyResult ? (
        <section className="panel">
          <div className="panel-header">
            <CheckCircle2 size={13} />
            Latest Orders
            <span className="panel-count">{buyResult.orders.length}</span>
          </div>
          <div className="wallet-order-grid">
            {buyResult.orders.map((order) => (
              <div className="wallet-order-row" key={`${order.ticker}-${order.order_id ?? order.message ?? order.amount}`}>
                <strong>{order.ticker}</strong>
                <span>{formatCurrency(order.amount)}</span>
                <em data-status={order.status}>{order.status}</em>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {confirmOpen ? (
        <div className="overlay" onClick={(event) => event.target === event.currentTarget && setConfirmOpen(false)}>
          <div className="confirm-window">
            <div className="terminal-header">
              <div className="terminal-dots">
                <span className="td-red" onClick={() => setConfirmOpen(false)} />
                <span className="td-yellow" />
                <span className="td-green" />
              </div>
              <span className="terminal-title">confirm t212 buy</span>
              <button className="terminal-close-btn" onClick={() => setConfirmOpen(false)}>
                <X size={14} />
              </button>
            </div>
            <div className="confirm-body">
              <div className="confirm-total">
                <span>{selectedRecommendations.length} tickers</span>
                <strong>{formatCurrency(budgetValue)}</strong>
                <small>Current selected allocation preview: {formatCurrency(selectedSuggestedTotal)}</small>
              </div>
              <div className="wallet-chip-list">
                {selectedRecommendations.map((item) => (
                  <span key={item.ticker}>{item.ticker}</span>
                ))}
              </div>
              <div className="inline-actions">
                <button className="ghost-btn" disabled={buying} onClick={() => setConfirmOpen(false)}>
                  Cancel
                </button>
                <button className="primary-btn" disabled={buying} onClick={confirmBuy}>
                  <ShoppingCart size={14} />
                  {buying ? 'Buying...' : 'Confirm Buy'}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
};

export default WalletPanel;
