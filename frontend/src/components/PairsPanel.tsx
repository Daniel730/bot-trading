import React, { useEffect, useState, useCallback } from 'react';
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
} from 'lucide-react';
import {
  fetchPairs,
  updatePairs,
  type PairInfo,
  type PairConfigEntry,
} from '../services/api';

interface PairsPanelProps {
  token: string;
}

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

const PairsPanel: React.FC<PairsPanelProps> = ({ token }) => {
  const [activePairs, setActivePairs] = useState<PairInfo[]>([]);
  const [configuredPairs, setConfiguredPairs] = useState<PairConfigEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  const [draft, setDraft] = useState<PairConfigEntry[]>([]);
  const [newA, setNewA] = useState('');
  const [newB, setNewB] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveOk, setSaveOk] = useState<string | null>(null);
  const [applyNow, setApplyNow] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchPairs(token);
      setActivePairs(data.active_pairs || []);
      setConfiguredPairs(data.configured_pairs || []);
    } catch (err) {
      console.error('Failed to fetch pairs:', err);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 15000);
    return () => clearInterval(id);
  }, [refresh]);

  const openEditor = () => {
    setDraft(configuredPairs.map((p) => ({ ...p })));
    setSaveError(null);
    setSaveOk(null);
    setEditorOpen(true);
  };

  const addPair = (e?: React.FormEvent) => {
    e?.preventDefault();
    const a = newA.trim().toUpperCase();
    const b = newB.trim().toUpperCase();
    if (!a || !b || a === b) return;
    if (draft.some((p) => p.ticker_a === a && p.ticker_b === b)) return;
    setDraft([...draft, { ticker_a: a, ticker_b: b }]);
    setNewA('');
    setNewB('');
  };

  const removePair = (idx: number) => {
    setDraft(draft.filter((_, i) => i !== idx));
  };

  const handleSave = async () => {
    setSaving(true);
    setSaveError(null);
    setSaveOk(null);
    try {
      const result = await updatePairs(token, draft, { applyNow });
      setSaveOk(
        result.reloaded
          ? `Saved ${result.saved_pairs} pairs — hot-reload applied.`
          : `Saved ${result.saved_pairs} pairs — restart required to apply.`,
      );
      await refresh();
    } catch (err) {
      const e = err as Error;
      setSaveError(e.message || 'Failed to save pairs');
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <div className="panel">
        <div className="panel-header">
          <Layers size={12} />
          Trading Pairs
          <span className="panel-count">{activePairs.length}</span>
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
          {activePairs.length === 0 ? (
            <div className="empty-state">
              <Layers size={28} style={{ opacity: 0.3 }} />
              <span>{loading ? 'Loading pairs…' : 'No active pairs'}</span>
            </div>
          ) : (
            <div className="pair-grid">
              {activePairs.map((p) => {
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
                  <div className="pair-card" key={p.id}>
                    <div className="pair-card-top">
                      <span className="pair-name">
                        {p.ticker_a} / {p.ticker_b}
                      </span>
                      <span
                        className={`badge ${
                          p.is_cointegrated ? 'badge-green' : 'badge-red'
                        }`}
                      >
                        {p.is_cointegrated ? 'COINT' : 'BROKEN'}
                      </span>
                    </div>
                    <div className="pair-meta">
                      <div className="pair-meta-cell">
                        <span className="pair-meta-label">Z</span>
                        <span
                          className="pair-meta-value"
                          style={{ color: zColor }}
                        >
                          {z === null || z === undefined ? '—' : z.toFixed(2)}
                        </span>
                      </div>
                      <div className="pair-meta-cell">
                        <span className="pair-meta-label">β</span>
                        <span className="pair-meta-value">
                          {formatNum(p.hedge_ratio, 3)}
                        </span>
                      </div>
                      <div className="pair-meta-cell">
                        <span className="pair-meta-label">σ</span>
                        <span className="pair-meta-value">
                          {formatNum(p.std, 3)}
                        </span>
                      </div>
                    </div>
                    <div className="pair-foot">
                      <span>{p.sector}</span>
                      <span>checked {formatRelative(p.last_cointegration_check)}</span>
                    </div>
                  </div>
                );
              })}
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

              <div className="editor-body">
                <div className="editor-section-title">
                  Configured pairs ({draft.length})
                </div>
                <div className="editor-list">
                  {draft.length === 0 && (
                    <div className="editor-empty">No pairs configured.</div>
                  )}
                  {draft.map((p, idx) => (
                    <div className="editor-row" key={`${p.ticker_a}_${p.ticker_b}_${idx}`}>
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
                    placeholder="Ticker A"
                    value={newA}
                    onChange={(e) => setNewA(e.target.value)}
                    autoFocus
                  />
                  <span className="editor-slash">/</span>
                  <input
                    className="editor-input"
                    placeholder="Ticker B"
                    value={newB}
                    onChange={(e) => setNewB(e.target.value)}
                  />
                  <button type="submit" className="editor-add-btn">
                    <Plus size={12} /> Add
                  </button>
                </form>

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
              </div>

              <div className="editor-footer">
                <label className="editor-toggle">
                  <input
                    type="checkbox"
                    checked={applyNow}
                    onChange={(e) => setApplyNow(e.target.checked)}
                  />
                  Apply immediately (hot-reload)
                </label>
                <div className="editor-footer-spacer" />
                <button
                  className="btn btn-default"
                  onClick={() => setEditorOpen(false)}
                  disabled={saving}
                >
                  Cancel
                </button>
                <button
                  className="btn btn-primary"
                  onClick={handleSave}
                  disabled={saving || draft.length === 0}
                >
                  <Save size={12} />
                  {saving ? 'Saving…' : 'Save'}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
};

export default PairsPanel;
