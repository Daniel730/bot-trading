import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type { ThoughtTelemetry } from '../services/api';

interface ThoughtJournalProps {
  thoughts: ThoughtTelemetry[];
}

const ThoughtJournal: React.FC<ThoughtJournalProps> = ({ thoughts }) => {
  // T015: Enforce strict 100-entry ring-buffer for rendering performance
  const displayThoughts = thoughts.slice(-100);

  const getVerdictColor = (verdict: string) => {
    switch (verdict) {
      case 'BULLISH': return 'var(--success)';
      case 'BEARISH': return 'var(--secondary)';
      case 'VETO': return '#ff4444';
      default: return 'var(--primary)';
    }
  };

  return (
    <div className="thought-journal" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <AnimatePresence initial={false}>
        {[...displayThoughts].reverse().map((thought, idx) => (
          <motion.div
            key={`${thought.signal_id}-${idx}`}
            className="thought-journal-item"
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0 }}
            style={{ 
              padding: '10px', 
              borderLeft: `2px solid ${getVerdictColor(thought.verdict)}`,
              background: 'rgba(255,255,255,0.02)',
              marginBottom: '8px',
              borderRadius: '0 4px 4px 0',
              fontSize: '0.75rem',
              willChange: 'transform, opacity',
              transform: 'translate3d(0,0,0)'
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
              <span style={{ fontWeight: 'bold', color: getVerdictColor(thought.verdict) }}>
                {thought.agent_name}
              </span>
              <span style={{ fontSize: '0.6rem', color: 'var(--text-dim)' }}>
                {thought.signal_id?.slice(0, 8)}
              </span>
            </div>
            <div style={{ color: 'var(--text-main)', lineHeight: '1.4' }}>
              {thought.thought}
            </div>
          </motion.div>
        ))}
      </AnimatePresence>
      {thoughts.length === 0 && (
        <div style={{ textAlign: 'center', marginTop: '40px', color: 'var(--text-dim)', fontSize: '0.7rem' }}>
          NO_THOUGHTS_CAPTURED
        </div>
      )}
    </div>
  );
};

export default ThoughtJournal;
