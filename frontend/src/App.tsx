import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Activity, 
  Terminal as TerminalIcon, 
  ShieldCheck, 
  Zap, 
  Radar, 
  X,
  Send
} from 'lucide-react';
import './App.css';
import PixelBot from './components/PixelBot';
import ThoughtJournal from './components/ThoughtJournal';
import IntelligenceHub from './components/IntelligenceHub';
import { useDashboardStream, sendTerminalCommand } from './services/api';
import type { DashboardData, Signal, TerminalMessage } from './services/api';
import { useTelemetry } from './hooks/useTelemetry';

const App: React.FC = () => {
  const urlParams = new URLSearchParams(window.location.search);
  const token = urlParams.get('token') || '';
  const { data, error } = useDashboardStream(token);
  const { isConnected, risk, thoughts, botState } = useTelemetry(token);
  
  const [isTerminalOpen, setIsTerminalOpen] = useState(false);
  const [terminalInput, setTerminalInput] = useState('');
  const terminalEndRef = useRef<HTMLDivElement>(null);

  // Derive mood from botState (telemetry) or stage (SSE)
  let derivedMood: 'idle' | 'analyzing' | 'executing' | 'doubt' | 'glitch' | 'happy' = 
    (botState?.toLowerCase() as any) || 'idle';

  if (derivedMood === 'idle' && data?.stage) {
    derivedMood = (data.stage.toLowerCase().includes('analyz') ? 'analyzing' : 
                   data.stage.toLowerCase().includes('execut') ? 'executing' : 'idle') as any;
  }

  // Override based on risk telemetry (Research Decision 3)
  if (risk?.volatility_status === 'HIGH_VOLATILITY' || (risk?.l2_entropy || 0) > 0.8 || data?.market_regime?.regime === 'VOLATILE') {
    derivedMood = 'glitch';
  } else if ((risk?.risk_multiplier || 1) < 0.5 || (data?.global_accuracy || 1) < 0.4) {
    derivedMood = 'doubt';
  } else if (thoughts.length > 0 && thoughts[thoughts.length - 1].verdict === 'BULLISH' && botState === 'EXECUTING') {
    derivedMood = 'happy';
  }

  useEffect(() => {
    if (terminalEndRef.current) {
      terminalEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [data?.terminal_messages, isTerminalOpen]);

  const handleSendCommand = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!terminalInput.trim()) return;
    
    try {
      await sendTerminalCommand(terminalInput, token);
      setTerminalInput('');
    } catch (err) {
      console.error('Command failed:', err);
    }
  };

  const formatCurrency = (val: number | null | undefined) => {
    if (val === null || val === undefined) {
      return <span style={{ color: '#f87171', fontWeight: 'bold' }}>ERR</span>;
    }
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val);
  };

  const metrics = data?.metrics || {
    total_invested: null,
    daily_profit: null,
    daily_budget: null,
    daily_usage_pct: null
  };

  // S-04: Deny access if no token is provided — never fall back to a default key
  if (!token) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', background: '#0a0a0f', color: '#f87171', fontFamily: 'monospace', fontSize: '1.2rem' }}>
        Access denied: no <code style={{ margin: '0 0.4em', color: '#fbbf24' }}>?token=</code> parameter provided.
      </div>
    );
  }

  return (
    <div className="dashboard-container">
      <header>
        <motion.div 
          className="logo"
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
        >
          <Activity size={24} />
          QUANTUM_ARBI_v7.0
        </motion.div>
        
        <div style={{ display: 'flex', gap: '20px', alignItems: 'center' }}>
          <motion.button 
            className="neon-button"
            onClick={() => setIsTerminalOpen(true)}
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
          >
            <TerminalIcon size={14} style={{ marginRight: '8px' }} />
            Open Terminal
          </motion.button>
          
          <div style={{ fontSize: '0.7rem', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
            DASHBOARD: <span style={{ color: 'var(--success)' }}>ONLINE</span>
          </div>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
            TELEMETRY: <span style={{ color: isConnected ? 'var(--success)' : 'var(--secondary)' }}>
              {isConnected ? 'LIVE' : 'RECONNECTING...'}
            </span>
          </div>
        </div>
      </header>

      <main className="main-layout">
        {/* Left Panel: Risk & Metrics */}
        <aside className="panel">
          <div className="panel-header">
            <ShieldCheck size={16} />
            Risk & Allocation
          </div>
          <div className="panel-content">
            <div style={{ marginBottom: '20px' }}>
              <button 
                className="neon-button" 
                style={{ width: '100%', justifyContent: 'center', borderColor: 'var(--success)', color: 'var(--success)' }}
                onClick={() => setIsTerminalOpen(true)}
              >
                <Zap size={14} style={{ marginRight: '8px' }} />
                Set Invest Goal
              </button>
            </div>

            <div className="metric-grid">
              <motion.div 
                className="metric-card"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1 }}
              >
                <div className="metric-label">Daily Budget</div>
                <div className="metric-value">{formatCurrency(data?.metrics?.daily_budget)}</div>
              </motion.div>
              
              <motion.div 
                className="metric-card"
                style={{ borderLeftColor: 'var(--secondary)' }}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2 }}
              >
                <div className="metric-label">Capital Deployed</div>
                <div className="metric-value">{formatCurrency(data?.metrics?.total_invested)}</div>
              </motion.div>

              <motion.div 
                className="metric-card"
                style={{ borderLeftColor: 'var(--success)' }}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3 }}
              >
                <div className="metric-label">Daily Profit</div>
                <div className="metric-value" style={{ color: 'var(--success)' }}>
                  {formatCurrency(data?.metrics?.daily_profit)}
                </div>
              </motion.div>
            </div>

            <div className="risk-hud" style={{ marginTop: '20px', padding: '15px', background: 'rgba(0,0,0,0.2)', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)' }}>
              <div style={{ fontSize: '0.65rem', color: 'var(--text-dim)', marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '5px' }}>
                <Radar size={12} /> RISK_TELEMETRY
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                <div>
                  <div style={{ fontSize: '0.55rem', color: 'var(--text-dim)' }}>RISK_MULT</div>
                  <div className="hud-value" style={{ fontSize: '0.9rem', color: (risk?.risk_multiplier || 1) < 0.5 ? 'var(--secondary)' : 'var(--primary)' }}>
                    {(risk?.risk_multiplier ?? 1).toFixed(2)}x
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: '0.55rem', color: 'var(--text-dim)' }}>MAX_DRAWDOWN</div>
                  <div className="hud-value" style={{ fontSize: '0.9rem', color: (risk?.max_drawdown_pct || 0) > 0.1 ? 'var(--secondary)' : 'var(--text-main)' }}>
                    {((risk?.max_drawdown_pct ?? 0) * 100).toFixed(1)}%
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: '0.55rem', color: 'var(--text-dim)' }}>L2_ENTROPY</div>
                  <div className="hud-value" style={{ fontSize: '0.9rem', color: (risk?.l2_entropy || 0) > 0.7 ? 'var(--secondary)' : 'var(--text-main)' }}>
                    {(risk?.l2_entropy ?? 0).toFixed(3)}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: '0.55rem', color: 'var(--text-dim)' }}>VOL_STATUS</div>
                  <div className="hud-value" style={{ fontSize: '0.7rem', color: risk?.volatility_status === 'HIGH_VOLATILITY' ? 'var(--secondary)' : 'var(--success)' }}>
                    {risk?.volatility_status || 'NORMAL'}
                  </div>
                </div>
              </div>
            </div>

            <div style={{ marginTop: '30px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.65rem', marginBottom: '8px', color: 'var(--text-dim)' }}>
                <span>BUDGET_UTILIZATION</span>
                <span>{data?.metrics?.daily_usage_pct?.toFixed(1)}%</span>
              </div>
              <div style={{ height: '4px', background: 'rgba(255,255,255,0.05)', borderRadius: '2px', overflow: 'hidden' }}>
                <motion.div 
                  style={{ height: '100%', background: 'var(--primary)' }}
                  animate={{ width: `${Math.min(data?.metrics?.daily_usage_pct || 0, 100)}%` }}
                />
              </div>
            </div>

            {/* INTEGRATED INTELLIGENCE HUB */}
            <IntelligenceHub 
              regime={data?.market_regime?.regime || 'STABLE'} 
              confidence={data?.market_regime?.confidence || 0.0} 
              accuracy={data?.global_accuracy || 0.5} 
            />

            {/* Intelligence Hub already contains a button if needed, but we keep the top one as primary */}
          </div>
        </aside>

        {/* Center Stage: The Bot */}
        <section className="center-stage">
          <div className="bot-aura" />
          
          <div className="bot-container">
            <PixelBot mood={derivedMood} />
          </div>


          <motion.div 
            style={{ marginTop: '20px', display: 'flex', alignItems: 'center', gap: '10px' }}
            animate={{ opacity: [0.5, 1, 0.5] }}
            transition={{ duration: 2, repeat: Infinity }}
          >
            <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--success)', boxShadow: '0 0 10px var(--success)' }} />
            <span style={{ fontSize: '0.8rem', letterSpacing: '2px', fontWeight: 'bold', color: 'var(--primary)' }}>
              {data?.stage?.toUpperCase() || 'INITIALIZING'}
            </span>
          </motion.div>
        </section>

        {/* Right Panel: Signals & Thoughts */}
        <aside className="panel">
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <div className="panel-header">
              <Zap size={16} />
              Live Signals Feed
            </div>
            <div className="panel-content" style={{ flex: '0 0 40%' }}>
              <AnimatePresence>
                {data?.active_signals && data.active_signals.length > 0 ? (
                  data.active_signals.map((sig, idx) => (
                    <motion.div 
                      key={`${sig.ticker_a}-${sig.ticker_b}-${idx}`}
                      className="signal-item"
                      initial={{ opacity: 0, x: 20 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, x: -20 }}
                      layout
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ fontWeight: '600', fontSize: '0.9rem' }}>{sig.ticker_a} / {sig.ticker_b}</span>
                        <span className="signal-status" style={{ 
                          color: sig.status.includes('EXECUTING') ? 'var(--secondary)' : 'var(--primary)',
                          border: `1px solid ${sig.status.includes('EXECUTING') ? 'var(--secondary)' : 'var(--primary)'}`
                        }}>
                          {sig.status}
                        </span>
                      </div>
                      <div style={{ marginTop: '8px', fontSize: '0.7rem', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
                        Z-SCORE: <span style={{ color: 'var(--primary)' }}>{sig.z_score.toFixed(3)}</span>
                      </div>
                    </motion.div>
                  ))
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '15px', marginTop: '50px', opacity: 0.3 }}>
                    <Radar size={40} />
                    <span style={{ fontSize: '0.7rem', letterSpacing: '2px' }}>SCANNING_MARKET...</span>
                  </div>
                )}
              </AnimatePresence>
            </div>

            <div className="panel-header" style={{ borderTop: '1px solid var(--border)' }}>
              <TerminalIcon size={16} />
              Agent Thought Journal
            </div>
            <div className="panel-content">
              <ThoughtJournal thoughts={thoughts} />
            </div>
          </div>
        </aside>
      </main>

      {/* Terminal Modal */}
      <AnimatePresence>
        {isTerminalOpen && (
          <motion.div 
            className="terminal-modal-overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <motion.div 
              className="terminal-window"
              initial={{ scale: 0.9, opacity: 0, y: 20 }}
              animate={{ scale: 1, opacity: 1, y: 0 }}
              exit={{ scale: 0.9, opacity: 0, y: 20 }}
            >
              <div className="panel-header" style={{ justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <TerminalIcon size={16} />
                  ARBI_ELITE_TERMINAL_v1.0
                </div>
                <X 
                  size={18} 
                  style={{ cursor: 'pointer' }} 
                  onClick={() => setIsTerminalOpen(false)} 
                />
              </div>
              
              <div className="terminal-messages">
                {data?.terminal_messages?.map((msg, idx) => (
                  <div key={idx} style={{ marginBottom: '12px', borderLeft: `2px solid ${msg.type === 'BOT' ? 'var(--primary)' : 'var(--secondary)'}`, paddingLeft: '12px' }}>
                    <span style={{ fontSize: '0.75rem', color: msg.type === 'BOT' ? 'var(--primary)' : 'var(--secondary)', fontWeight: 'bold', marginRight: '8px' }}>
                      [{msg.type}]
                    </span>
                    <span style={{ color: 'var(--text-main)' }}>{msg.text}</span>
                    
                    {msg.metadata?.type === 'approval' && (
                      <div style={{ marginTop: '10px' }}>
                        <button 
                          className="neon-button" 
                          style={{ borderColor: 'var(--success)', color: 'var(--success)', fontSize: '0.6rem' }}
                          onClick={() => sendTerminalCommand(`/approve ${msg.metadata.correlation_id}`, token)}
                        >
                          Approve Transaction {msg.metadata.correlation_id}
                        </button>
                      </div>
                    )}
                  </div>
                ))}
                <div ref={terminalEndRef} />
              </div>

              <form className="terminal-input-area" onSubmit={handleSendCommand}>
                <span style={{ color: 'var(--success)', fontFamily: 'var(--font-mono)' }}>{'>'}</span>
                <input 
                  type="text" 
                  className="terminal-input"
                  value={terminalInput}
                  onChange={(e) => setTerminalInput(e.target.value)}
                  placeholder="Enter command..."
                  autoFocus
                />
                <button type="submit" style={{ background: 'transparent', border: 'none', color: 'var(--text-dim)', cursor: 'pointer' }}>
                  <Send size={16} />
                </button>
              </form>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {error && (
        <motion.div 
          style={{ position: 'fixed', bottom: '20px', right: '20px', background: '#f87171', color: 'white', padding: '10px 20px', borderRadius: '8px', fontSize: '0.8rem', zIndex: 1000 }}
          initial={{ x: 100 }}
          animate={{ x: 0 }}
        >
          {error}
        </motion.div>
      )}
    </div>
  );
};

export default App;
