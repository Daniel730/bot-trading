import { Activity } from 'lucide-react';
import React from 'react';
import { NAV_CATEGORIES, NAV_ITEMS, type Page } from '../../constants/navigation';
import type { SummaryResponse } from '../../services/api';

interface SidebarNavProps {
  isConnected: boolean;
  currentStage: string;
  currentMode: string;
  currentBotState: string;
  page: Page;
  onPageChange: (page: Page) => void;
  summary: SummaryResponse | null;
  activeSignalsCount: number;
  positionsCount: number;
}

export default function SidebarNav({
  isConnected,
  currentStage,
  currentMode,
  currentBotState,
  page,
  onPageChange,
  summary,
  activeSignalsCount,
  positionsCount,
}: SidebarNavProps) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">
          <Activity size={16} />
        </div>
        <div>
          <strong>Alpha Arbitrage</strong>
          <span>Operations Console</span>
        </div>
      </div>

      <div className="mode-card">
        <span className={`status-dot ${isConnected ? 'live' : 'warn'}`} />
        <div>
          <strong>{currentStage}</strong>
          <span>{currentMode} mode · {currentBotState}</span>
        </div>
      </div>

      <nav className="nav">
        {NAV_CATEGORIES.map((category) => (
          <div key={category} className="nav-group">
            <div className="nav-group-label">{category}</div>
            {NAV_ITEMS.filter((item) => item.category === category).map((item) => (
              <button
                key={item.key}
                className={`nav-item ${page === item.key ? 'active' : ''}`}
                onClick={() => onPageChange(item.key)}
              >
                {item.icon}
                {item.label}
              </button>
            ))}
          </div>
        ))}
      </nav>

      <div className="sidebar-footer">
        <div className="mini-stat">
          <span>Signals</span>
          <strong>{summary?.open_signals ?? activeSignalsCount}</strong>
        </div>
        <div className="mini-stat">
          <span>Positions</span>
          <strong>{summary?.open_positions ?? positionsCount}</strong>
        </div>
      </div>
    </aside>
  );
}
