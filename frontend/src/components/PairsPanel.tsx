import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Layers,
  Plus,
  Trash2,
  Save,
  X,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  Settings,
  Bitcoin,
  TrendingUp,
  ChevronDown,
  Wallet,
  ShoppingCart,
} from 'lucide-react';
import {
  fetchPairs,
  syncWallet,
  updatePairs,
  type PairInfo,
  type PairConfigEntry,
} from '../services/api';

interface PairsPanelProps {
  token: string;
  sessionToken: string;
}

type EditorTab = 'stocks' | 'crypto';
type ListFilter = 'all' | 'stocks' | 'crypto' | 'coint' | 'broken';
const ACTIVE_PAIRS_PAGE_SIZE = 12;

const formatNum = (val: number | null | undefined, decimals = 3): string => {
  if (val === null || val === undefined || Number.isNaN(val)) return '—';
  return val.toFixed(decimals);
};

const formatRelative = (iso: string | null | undefined): string => {
  if (!iso) return 'never';
  try {
    const d = new Date(iso);
    const diffH = (Date.now() - d.getTime()) / 36e5;
    if (diffH < 1) return `${Math.max(0, Math.round(diffH * 60))}m ago`;
    if (diffH < 24) return `${Math.round(diffH)}h ago`;
    return `${Math.round(diffH / 24)}d ago`;
  } catch {
    return iso;
  }
};

const isCryptoTicker = (t: string) => /-USD$/i.test(t);

// ─── PairRow ─────────────────────────────────────────────────────────────────

interface PairRowProps {
  p: PairInfo;
}

const PairRow: React.FC<PairRowProps> = ({ p }) => {
  const [expanded, setExpanded] = useState(false);

  const z = p.last_z_score;
  const zColor =
    z === null || z === undefined
      ? 'var(--text-muted)'
      : Math.abs(z) > 2
      ? 'var(--yellow)'
      : Math.abs(z) > 1
      ? 'var(--accent)'
      : 'var(--text-muted)';

  return (
    <div className={`pair-row ${p.is_crypto ? 'pair-crypto' : ''}`}>
      <div
        className="pair-row-main"
        onClick={() => setExpanded((v) => !v)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === 'Enter' && setExpanded((v) => !v)}
      >
        <span className="pair-row-name">
          {p.is_crypto ? (
            <Bitcoin size={11} style={{ opacity: 0.6, flexShrink: 0 }} />
          ) : null}
          {p.ticker_a}
          <span className="pair-row-slash"> / </span>
          {p.ticker_b}
        </span>

        <span className="pair-col-z" style={{ color: zColor }}>
          {z === null || z === undefined ? '—' : z.toFixed(2)}
        </span>

        <div className="pair-col-badge">
          <span
            className={`badge ${
              p.is_cointegrated ? 'badge-green' : 'badge-red'
            }`}
          >
            {p.is_cointegrated ? 'COINT' : 'BROKEN'}
          </span>
        </div>

        <ChevronDown
          size={13}
          className={`pair-expand-icon ${expanded ? 'expanded' : ''}`}
        />
      </div>

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            className="pair-row-details"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18, ease: 'easeInOut' }}
            style={{ overflow: 'hidden' }}
          >
            <div className="pair-detail-inner">
              <div className="pair-detail-cell">
                <span className="pair-detail-label">Hedge Ratio (β)</span>
                <span className="pair-detail-value">
                  {formatNum(p.hedge_ratio, 3)}
                </span>
              </div>
              <div className="pair-detail-cell">
                <span className="pair-detail-label">Std Dev (σ)</span>
                <span className="pair-detail-value">
                  {formatNum(p.std, 3)}
                </span>
              </div>
              <div className="pair-detail-cell">
                <span className="pair-detail-label">Sector</span>
                <span className="pair-detail-value">{p.sector || '—'}</span>
              </div>
              <div className="pair-detail-cell">
                <span className="pair-detail-label">Last Check</span>
                <span className="pair-detail-value">
                  {formatRelative(p.last_cointegration_check)}
                </span>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

// ─── PairsPanel ───────────────────────────────────────────────────────────────

const PairsPanel: React.FC<PairsPanelProps> = ({ token, sessionToken }) => {
  const [activePairs, setActivePairs] = useState<PairInfo[]>([]);
  const [configuredStocks, setConfiguredStocks] = useState<PairConfigEntry[]>([]);
  const [configuredCrypto, setConfiguredCrypto] = useState<PairConfigEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<ListFilter>('all');
  const [activePairsPage, setActivePairsPage] = useState(1);

  const [editorOpen, setEditorOpen] = useState(false);
  const [editorTab, setEditorTab] = useState<EditorTab>('stocks');
  const [draftStocks, setDraftStocks] = useState<PairConfigEntry[]>([]);
  const [draftCrypto, setDraftCrypto] = useState<PairConfigEntry[]>([]);
  const [newA, setNewA] = useState('');
  const [newB, setNewB] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveOk, setSaveOk] = useState<string | null>(null);
  const [applyNow, setApplyNow] = useState(true);
  const [walletBudget, setWalletBudget] = useState('100');
  const [walletSyncing, setWalletSyncing] = useState(false);
  const [walletError, setWalletError] = useState<string | null>(null);
  const [walletOk, setWalletOk] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchPairs(token, sessionToken);
      setActivePairs(data.active_pairs || []);
      setConfiguredStocks(data.configured_pairs || []);
      setConfiguredCrypto(data.crypto_test_pairs || []);
    } catch (err) {
      console.error('Failed to fetch pairs:', err);
    } finally {
      setLoading(false);
    }
  }, [token, sessionToken]);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 15000);
    return () => clearInterval(id);
  }, [refresh]);

  const filteredActive = useMemo(() => {
    let list = activePairs;
    if (filter === 'crypto') list = list.filter((p) => p.is_crypto);
    else if (filter === 'stocks') list = list.filter((p) => !p.is_crypto);
    else if (filter === 'coint') list = list.filter((p) => p.is_cointegrated === true);
    else if (filter === 'broken') list = list.filter((p) => p.is_cointegrated !== true);
    // Sort: cointegrated pairs first, then by |z-score| descending so the
    // most actionable signals bubble to the top. Pairs without a z-score
    // (Kalman still warming up) sort to the bottom of their group.
    return [...list].sort((a, b) => {
      const cointDelta = (b.is_cointegrated ? 1 : 0) - (a.is_cointegrated ? 1 : 0);
      if (cointDelta !== 0) return cointDelta;
      const za = a.last_z_score == null ? -Infinity : Math.abs(a.last_z_score);
      const zb = b.last_z_score == null ? -Infinity : Math.abs(b.last_z_score);
      if (zb !== za) return zb - za;
      return a.id.localeCompare(b.id);
    });
  }, [activePairs, filter]);
  const totalActivePairPages = Math.max(1, Math.ceil(filteredActive.length / ACTIVE_PAIRS_PAGE_SIZE));
  const pagedActivePairs = useMemo(() => {
    const start = (activePairsPage - 1) * ACTIVE_PAIRS_PAGE_SIZE;
    return filteredActive.slice(start, start + ACTIVE_PAIRS_PAGE_SIZE);
  }, [activePairsPage, filteredActive]);

  useEffect(() => {
    setActivePairsPage(1);
  }, [filter]);

  useEffect(() => {
    if (activePairsPage > totalActivePairPages) {
      setActivePairsPage(totalActivePairPages);
    }
  }, [activePairsPage, totalActivePairPages]);

  const stockCount = activePairs.filter((p) => !p.is_crypto).length;
  const cryptoCount = activePairs.filter((p) => p.is_crypto).length;
  const cointCount = activePairs.filter((p) => p.is_cointegrated === true).length;
  const brokenCount = activePairs.filter((p) => p.is_cointegrated !== true).length;
  const allEquityTickers = useMemo(() => {
    const tickers: string[] = [];
    for (const pair of activePairs.filter(p => !p.is_crypto)) {
      if (!tickers.includes(pair.ticker_a)) tickers.push(pair.ticker_a);
      if (!tickers.includes(pair.ticker_b)) tickers.push(pair.ticker_b);
    }
    return tickers;
  }, [activePairs]);

  const openEditor = () => {
    setDraftStocks(configuredStocks.map((p) => ({ ...p })));
    setDraftCrypto(configuredCrypto.map((p) => ({ ...p })));
    setSaveError(null);
    setSaveOk(null);
    setEditorOpen(true);
  };

  const currentDraft = editorTab === 'stocks' ? draftStocks : draftCrypto;
  const setCurrentDraft = editorTab === 'stocks' ? setDraftStocks : setDraftCrypto;

  const addPair = (e?: React.FormEvent) => {
    e?.preventDefault();
    const a = newA.trim().toUpperCase();
    const b = newB.trim().toUpperCase();
    if (!a || !b || a === b) return;
    if (currentDraft.some((p) => p.ticker_a === a && p.ticker_b === b)) return;
    setCurrentDraft([...currentDraft, { ticker_a: a, ticker_b: b }]);
    setNewA('');
    setNewB('');
  };

  const removePair = (idx: number) => {
    setCurrentDraft(currentDraft.filter((_, i) => i !== idx));
  };

  const handleSave = async () => {
    setSaving(true);
    setSaveError(null);
    setSaveOk(null);
    try {
      const result = await updatePairs(token, draftStocks, {
        applyNow,
        cryptoPairs: draftCrypto,
      }, sessionToken);
      const total = draftStocks.length + draftCrypto.length;
      setSaveOk(
        result.reloaded
          ? `Saved ${draftStocks.length} stocks + ${draftCrypto.length} crypto = ${total} pairs — hot-reload applied.`
          : `Saved ${total} pairs — restart required to apply.`,
      );
      await refresh();
    } catch (err) {
      const e = err as Error;
      setSaveError(e.message || 'Failed to save pairs');
    } finally {
      setSaving(false);
    }
  };

  const handleWalletSync = async () => {
    const budget = Number(walletBudget);
    setWalletError(null);
    setWalletOk(null);

    if (!Number.isFinite(budget) || budget <= 0) {
      setWalletError('Enter a positive budget.');
      return;
    }

    if (allEquityTickers.length === 0) {
      setWalletError('No equity tickers are active.');
      return;
    }

    const confirmed = window.confirm(
      `Place broker BUY orders for missing stock tickers with a ${budget.toFixed(2)} budget?`,
    );
    if (!confirmed) return;

    setWalletSyncing(true);
    try {
      const result = await syncWallet(token, sessionToken, budget);
      const okOrders = result.orders.filter((order) => order.status === 'ok').length;
      setWalletOk(
        `${result.message} ${okOrders} orders, ${result.skipped.length} skipped.`,
      );
      await refresh();
    } catch (err) {
      const e = err as Error;
      setWalletError(e.message || 'Failed to sync broker wallet');
    } finally {
      setWalletSyncing(false);
    }
  };

  const placeholderA = editorTab === 'crypto' ? 'BTC-USD' : 'KO';
  const placeholderB = editorTab === 'crypto' ? 'ETH-USD' : 'PEP';

  return (
    <>
      <div className="panel">
        <div className="panel-header">
          <Layers size={12} />
          Trading Pairs
          <span className="panel-count">{activePairs.length}</span>
          <div className="pair-filter">
            <button
              data-kind="all"
              className={`pair-filter-chip ${filter === 'all' ? 'active' : ''}`}
              onClick={() => setFilter('all')}
            >
              All ({activePairs.length})
            </button>
            <button
              data-kind="stocks"
              className={`pair-filter-chip ${filter === 'stocks' ? 'active' : ''}`}
              onClick={() => setFilter('stocks')}
            >
              <TrendingUp size={10} /> Stocks ({stockCount})
            </button>
            <button
              data-kind="crypto"
              className={`pair-filter-chip ${filter === 'crypto' ? 'active' : ''}`}
              onClick={() => setFilter('crypto')}
            >
              <Bitcoin size={10} /> Crypto ({cryptoCount})
            </button>
            <button
              data-kind="coint"
              className={`pair-filter-chip ${filter === 'coint' ? 'active' : ''}`}
              onClick={() => setFilter('coint')}
            >
              COINT ({cointCount})
            </button>
            <button
              data-kind="broken"
              className={`pair-filter-chip ${filter === 'broken' ? 'active' : ''}`}
              onClick={() => setFilter('broken')}
            >
              BROKEN ({brokenCount})
            </button>
          </div>
          <button
            className="panel-action-btn"
            title="Refresh"
            onClick={refresh}
            disabled={loading}
          >
            <RefreshCw size={11} className={loading ? 'spin' : ''} />
          </button>
          <button
            className="panel-action-btn"
            title="Edit pairs"
            onClick={openEditor}
          >
            <Settings size={11} />
          </button>
        </div>
        <div className="panel-body">
          <div className="wallet-sync-strip">
            <div className="wallet-sync-meta">
              <Wallet size={16} />
              <div>
                <strong>Broker Wallet</strong>
                <span>{activePairs.filter(p => !p.is_crypto).length} pairs / {allEquityTickers.length} tickers</span>
              </div>
            </div>
            <div className="wallet-sync-controls">
              <label className="wallet-budget-field">
                <span>Budget</span>
                <input
                  type="number"
                  min="1"
                  step="1"
                  value={walletBudget}
                  onChange={(e) => setWalletBudget(e.target.value)}
                />
              </label>
              <button
                className="wallet-sync-btn"
                disabled={walletSyncing || allEquityTickers.length === 0}
                onClick={handleWalletSync}
                title="Buy missing broker tickers"
              >
                <ShoppingCart size={13} />
                {walletSyncing ? 'Buying...' : 'Buy All'}
              </button>
            </div>
          </div>

          {walletError && (
            <div className="editor-msg error">
              <AlertTriangle size={12} /> {walletError}
            </div>
          )}
          {walletOk && (
            <div className="editor-msg ok">
              <CheckCircle2 size={12} /> {walletOk}
            </div>
          )}

          {filteredActive.length === 0 ? (
            <div className="empty-state">
              <Layers size={28} style={{ opacity: 0.3 }} />
              <span>{loading ? 'Loading pairs…' : 'No pairs in this view'}</span>
            </div>
          ) : (
            <div className="pair-table">
              <div className="pair-table-header">
                <span>Pair</span>
                <span>Z-score</span>
                <span>Status</span>
                <span />
              </div>
              {pagedActivePairs.map((p) => (
                <PairRow key={p.id} p={p} />
              ))}
            </div>
          )}
          {filteredActive.length > ACTIVE_PAIRS_PAGE_SIZE && (
            <div className="list-pagination">
              <button
                className="panel-action-btn"
                disabled={activePairsPage <= 1}
                onClick={() => setActivePairsPage((current) => Math.max(1, current - 1))}
                title="Previous page"
              >
                Prev
              </button>
              <span className="list-pagination-label">
                Page {activePairsPage} / {totalActivePairPages}
              </span>
              <button
                className="panel-action-btn"
                disabled={activePairsPage >= totalActivePairPages}
                onClick={() => setActivePairsPage((current) => Math.min(totalActivePairPages, current + 1))}
                title="Next page"
              >
                Next
              </button>
            </div>
          )}
        </div>
      </div>

      <AnimatePresence>
        {editorOpen && (
          <motion.div
            className="overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={(e) => e.target === e.currentTarget && setEditorOpen(false)}
          >
            <motion.div
              className="editor-window"
              initial={{ scale: 0.96, opacity: 0, y: 10 }}
              animate={{ scale: 1, opacity: 1, y: 0 }}
              exit={{ scale: 0.96, opacity: 0, y: 10 }}
              transition={{ type: 'spring', stiffness: 320, damping: 32 }}
            >
              <div className="terminal-header">
                <div className="terminal-dots">
                  <span className="td-red" onClick={() => setEditorOpen(false)} />
                  <span className="td-yellow" />
                  <span className="td-green" />
                </div>
                <span className="terminal-title">edit pair universe</span>
                <button
                  className="terminal-close-btn"
                  onClick={() => setEditorOpen(false)}
                >
                  <X size={14} />
                </button>
              </div>

              <div className="editor-tabs">
                <button
                  className={`editor-tab ${editorTab === 'stocks' ? 'active' : ''}`}
                  onClick={() => setEditorTab('stocks')}
                >
                  <TrendingUp size={11} />
                  Stocks
                  <span className="editor-tab-count">{draftStocks.length}</span>
                </button>
                <button
                  className={`editor-tab ${editorTab === 'crypto' ? 'active' : ''}`}
                  onClick={() => setEditorTab('crypto')}
                >
                  <Bitcoin size={11} />
                  Crypto (24/7)
                  <span className="editor-tab-count">{draftCrypto.length}</span>
                </button>
              </div>

              <div className="editor-body">
                <div className="editor-section-title">
                  {editorTab === 'stocks'
                    ? 'Equity pairs (NYSE hours only)'
                    : 'Crypto pairs (run 24/7, including weekends)'}
                </div>
                <div className="editor-list">
                  {currentDraft.length === 0 && (
                    <div className="editor-empty">
                      No {editorTab} pairs configured.
                    </div>
                  )}
                  {currentDraft.map((p, idx) => (
                    <div
                      className="editor-row"
                      key={`${p.ticker_a}_${p.ticker_b}_${idx}`}
                    >
                      <span className="editor-row-pair">
                        {p.ticker_a} / {p.ticker_b}
                      </span>
                      <button
                        className="editor-remove-btn"
                        title="Remove pair"
                        onClick={() => removePair(idx)}
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  ))}
                </div>

                <form className="editor-add-row" onSubmit={addPair}>
                  <input
                    className="editor-input"
                    placeholder={placeholderA}
                    value={newA}
                    onChange={(e) => setNewA(e.target.value)}
                    autoFocus
                  />
                  <span className="editor-slash">/</span>
                  <input
                    className="editor-input"
                    placeholder={placeholderB}
                    value={newB}
                    onChange={(e) => setNewB(e.target.value)}
                  />
                  <button type="submit" className="editor-add-btn">
                    <Plus size={12} /> Add
                  </button>
                </form>

                {editorTab === 'crypto' && (newA || newB) && (
                  <div className="editor-hint">
                    Tip: crypto tickers usually end in <code>-USD</code> (e.g.{' '}
                    <code>BTC-USD</code>, <code>ETH-USD</code>).
                    {(newA && !isCryptoTicker(newA)) ||
                    (newB && !isCryptoTicker(newB))
                      ? ' One of your tickers is missing the suffix.'
                      : ''}
                  </div>
                )}

                {saveError && (
                  <div className="editor-msg error">
                    <AlertTriangle size={12} /> {saveError}
                  </div>
                )}
                {saveOk && (
                  <div className="editor-msg ok">
                    <CheckCircle2 size={12} /> {saveOk}
                  </div>
                )}
                <div className="editor-footer">
                  <label className="editor-apply-label">
                    <input
                      type="checkbox"
                      checked={applyNow}
                      onChange={(e) => setApplyNow(e.target.checked)}
                    />
                    Apply immediately
                  </label>
                  <button
                    className="editor-save-btn"
                    onClick={handleSave}
                    disabled={saving}
                  >
                    <Save size={12} />
                    {saving ? 'Saving…' : 'Save'}
                  </button>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
};

export default PairsPanel;
