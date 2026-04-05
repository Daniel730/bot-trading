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
import { useDashboardStream, sendTerminalCommand } from './services/api';
import type { DashboardData, Signal, TerminalMessage } from './services/api';

const App: React.FC = () => {
  const urlParams = new URLSearchParams(window.location.search);
  const token = urlParams.get('token');
  const { data, error } = useDashboardStream(token);
  
  const [isTerminalOpen, setIsTerminalOpen] = useState(false);
  const [terminalInput, setTerminalInput] = useState('');
  const terminalEndRef = useRef<HTMLDivElement>(null);

  const mood = (data?.stage?.toLowerCase().includes('analyz') ? 'analyzing' : 
               data?.stage?.toLowerCase().includes('execut') ? 'executing' : 'idle') as any;

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

  const formatCurrency = (val: number = 0) => {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val);
  };

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
            STATUS: <span style={{ color: 'var(--success)' }}>ONLINE</span>
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
          </div>
        </aside>

        {/* Center Stage: The Bot */}
        <section className="center-stage">
          <div className="bot-aura" />
          
          <div className="bot-container">
            <PixelBot mood={mood} />
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

        {/* Right Panel: Signals */}
        <aside className="panel">
          <div className="panel-header">
            <Zap size={16} />
            Live Signals Feed
          </div>
          <div className="panel-content">
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
