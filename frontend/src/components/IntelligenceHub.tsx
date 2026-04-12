import React from 'react';
import { motion } from 'framer-motion';
import { Brain, TrendingUp, TrendingDown, RefreshCw, Activity, Shield } from 'lucide-react';

interface IntelligenceHubProps {
  regime: string;
  confidence: number;
  accuracy: number;
}

const IntelligenceHub: React.FC<IntelligenceHubProps> = ({ regime, confidence, accuracy }) => {
  const getRegimeIcon = () => {
    switch (regime) {
      case 'TRENDING_UP': return <TrendingUp size={20} style={{ color: 'var(--success)' }} />;
      case 'TRENDING_DOWN': return <TrendingDown size={20} style={{ color: 'var(--secondary)' }} />;
      case 'VOLATILE': return <Activity size={20} style={{ color: 'var(--secondary)' }} />;
      case 'SIDEWAYS': return <RefreshCw size={20} style={{ color: 'var(--primary)' }} />;
      default: return <Shield size={20} style={{ color: 'var(--text-dim)' }} />;
    }
  };

  const accuracyColor = accuracy > 0.7 ? 'var(--success)' : accuracy < 0.4 ? 'var(--secondary)' : 'var(--primary)';

  return (
    <div className="intelligence-hub" style={{ marginTop: '20px' }}>
      <div className="panel-header" style={{ borderTop: '1px solid var(--border)', paddingTop: '15px' }}>
        <Brain size={16} />
        Intelligence Hub
      </div>
      
      <div className="panel-content" style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '15px' }}>
        {/* MARKET REGIME CARD */}
        <motion.div 
          className="metric-card"
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.05)' }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <div className="metric-label" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              CURRENT_REGIME
            </div>
            {getRegimeIcon()}
          </div>
          <div className="metric-value" style={{ fontSize: '1.1rem', letterSpacing: '1px' }}>
            {regime.replace('_', ' ')}
          </div>
          <div style={{ fontSize: '0.6rem', color: 'var(--text-dim)', marginTop: '5px' }}>
            CLASSIFICATION_CONFIDENCE: {(confidence * 100).toFixed(1)}%
          </div>
        </motion.div>

        {/* SELF-ESTEEM (ACCURACY) METER */}
        <motion.div 
          className="metric-card"
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.05)' }}
        >
          <div className="metric-label" style={{ marginBottom: '10px' }}>STRATEGY_SELF_ESTEEM (ACCURACY)</div>
          <div style={{ position: 'relative', height: '12px', background: 'rgba(255,255,255,0.05)', borderRadius: '6px', overflow: 'hidden' }}>
            <motion.div 
              style={{ position: 'absolute', top: 0, left: 0, height: '100%', background: accuracyColor, boxShadow: `0 0 10px ${accuracyColor}` }}
              initial={{ width: 0 }}
              animate={{ width: `${accuracy * 100}%` }}
              transition={{ duration: 1.5, ease: "easeOut" }}
            />
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '8px', fontSize: '0.9rem', fontWeight: 'bold' }}>
            <span style={{ color: accuracyColor }}>{(accuracy * 100).toFixed(1)}%</span>
            <span style={{ fontSize: '0.6rem', color: 'var(--text-dim)', alignSelf: 'center' }}>
                {accuracy > 0.6 ? 'OPTIMAL' : accuracy < 0.4 ? 'CAUTION: PENALTY ACTIVE' : 'NOMINAL'}
            </span>
          </div>
        </motion.div>
      </div>
    </div>
  );
};

export default IntelligenceHub;
