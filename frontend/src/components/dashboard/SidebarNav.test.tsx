/**
 * Tests for src/components/dashboard/SidebarNav.tsx
 *
 * Covers:
 *  - Brand section: renders "Alpha Arbitrage" and "Operations Console"
 *  - Connection status: status-dot class "live" vs "warn"
 *  - Stage/mode/state display
 *  - Navigation: all NAV_CATEGORIES and NAV_ITEMS are rendered
 *  - Active page: button with 'active' class matches the current page prop
 *  - Page change: onPageChange is called with correct page key on button click
 *  - Footer stats: Signals and Positions from summary or fallback props
 */

import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import SidebarNav from './SidebarNav';
import { NAV_ITEMS } from '../../constants/navigation';

// ---------------------------------------------------------------------------
// Helper: default props
// ---------------------------------------------------------------------------

function defaultProps(overrides: Record<string, unknown> = {}) {
  return {
    isConnected: true,
    currentStage: 'Running',
    currentMode: 'live',
    currentBotState: 'RUNNING',
    page: 'overview' as const,
    onPageChange: vi.fn(),
    summary: null,
    activeSignalsCount: 0,
    positionsCount: 0,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Brand section
// ---------------------------------------------------------------------------

describe('SidebarNav brand section', () => {
  it('renders "Alpha Arbitrage" brand name', () => {
    render(<SidebarNav {...defaultProps()} />);
    expect(screen.getByText('Alpha Arbitrage')).toBeInTheDocument();
  });

  it('renders "Operations Console" subtitle', () => {
    render(<SidebarNav {...defaultProps()} />);
    expect(screen.getAllByText('Operations Console').length).toBeGreaterThanOrEqual(1);
  });
});

// ---------------------------------------------------------------------------
// Connection status
// ---------------------------------------------------------------------------

describe('SidebarNav connection status', () => {
  it('renders status-dot with "live" class when isConnected is true', () => {
    render(<SidebarNav {...defaultProps({ isConnected: true })} />);
    const dot = document.querySelector('.status-dot.live');
    expect(dot).not.toBeNull();
  });

  it('renders status-dot with "warn" class when isConnected is false', () => {
    render(<SidebarNav {...defaultProps({ isConnected: false })} />);
    const dot = document.querySelector('.status-dot.warn');
    expect(dot).not.toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Stage / mode / state display
// ---------------------------------------------------------------------------

describe('SidebarNav mode card content', () => {
  it('shows currentStage in the mode card', () => {
    render(<SidebarNav {...defaultProps({ currentStage: 'Pre-Warming' })} />);
    expect(screen.getByText('Pre-Warming')).toBeInTheDocument();
  });

  it('shows currentMode and currentBotState together', () => {
    render(<SidebarNav {...defaultProps({ currentMode: 'paper', currentBotState: 'PAUSED' })} />);
    expect(screen.getByText('paper mode · PAUSED')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Navigation items
// ---------------------------------------------------------------------------

describe('SidebarNav navigation items', () => {
  it('renders all three nav category labels', () => {
    render(<SidebarNav {...defaultProps()} />);
    expect(screen.getByText('MONITORING')).toBeInTheDocument();
    expect(screen.getByText('TRADING')).toBeInTheDocument();
    expect(screen.getByText('SYSTEM')).toBeInTheDocument();
  });

  it('renders all NAV_ITEMS as buttons', () => {
    render(<SidebarNav {...defaultProps()} />);
    for (const item of NAV_ITEMS) {
      expect(screen.getByText(item.label)).toBeInTheDocument();
    }
  });

  it('renders exactly the correct number of nav buttons', () => {
    render(<SidebarNav {...defaultProps()} />);
    const navButtons = document.querySelectorAll('nav.nav button.nav-item');
    expect(navButtons.length).toBe(NAV_ITEMS.length);
  });
});

// ---------------------------------------------------------------------------
// Active page highlighting
// ---------------------------------------------------------------------------

describe('SidebarNav active page', () => {
  it('marks the overview button as active when page is "overview"', () => {
    render(<SidebarNav {...defaultProps({ page: 'overview' })} />);
    const overviewBtn = screen.getByText('Overview').closest('button');
    expect(overviewBtn?.className).toContain('active');
  });

  it('marks the wallet button as active when page is "wallet"', () => {
    render(<SidebarNav {...defaultProps({ page: 'wallet' })} />);
    const walletBtn = screen.getByText('Wallet').closest('button');
    expect(walletBtn?.className).toContain('active');
  });

  it('does not mark overview as active when page is "wallet"', () => {
    render(<SidebarNav {...defaultProps({ page: 'wallet' })} />);
    const overviewBtn = screen.getByText('Overview').closest('button');
    expect(overviewBtn?.className).not.toContain('active');
  });

  it('marks only one button as active at a time', () => {
    render(<SidebarNav {...defaultProps({ page: 'health' })} />);
    const activeButtons = document.querySelectorAll('button.nav-item.active');
    expect(activeButtons.length).toBe(1);
    expect(activeButtons[0].textContent).toContain('System Health');
  });
});

// ---------------------------------------------------------------------------
// Page change callback
// ---------------------------------------------------------------------------

describe('SidebarNav page change', () => {
  it('calls onPageChange with the correct page key on button click', () => {
    const onPageChange = vi.fn();
    render(<SidebarNav {...defaultProps({ onPageChange })} />);
    fireEvent.click(screen.getByText('Wallet'));
    expect(onPageChange).toHaveBeenCalledWith('wallet');
  });

  it('calls onPageChange when clicking a SYSTEM category item', () => {
    const onPageChange = vi.fn();
    render(<SidebarNav {...defaultProps({ onPageChange })} />);
    fireEvent.click(screen.getByText('Bot Control'));
    expect(onPageChange).toHaveBeenCalledWith('control');
  });

  it('calls onPageChange when clicking a MONITORING category item', () => {
    const onPageChange = vi.fn();
    render(<SidebarNav {...defaultProps({ onPageChange })} />);
    fireEvent.click(screen.getByText('Analytics'));
    expect(onPageChange).toHaveBeenCalledWith('analytics');
  });
});

// ---------------------------------------------------------------------------
// Footer stats
// ---------------------------------------------------------------------------

describe('SidebarNav footer stats', () => {
  it('shows activeSignalsCount when summary is null', () => {
    render(<SidebarNav {...defaultProps({ summary: null, activeSignalsCount: 7 })} />);
    // There should be a strong element containing "7" under the Signals stat
    const signalsStat = screen.getByText('Signals').closest('.mini-stat');
    expect(signalsStat?.querySelector('strong')?.textContent).toBe('7');
  });

  it('shows positionsCount when summary is null', () => {
    render(<SidebarNav {...defaultProps({ summary: null, positionsCount: 3 })} />);
    const positionsStat = screen.getByText('Positions').closest('.mini-stat');
    expect(positionsStat?.querySelector('strong')?.textContent).toBe('3');
  });

  it('prefers summary.open_signals over activeSignalsCount', () => {
    render(
      <SidebarNav
        {...defaultProps({
          summary: { open_signals: 12, open_positions: 5 },
          activeSignalsCount: 99,
          positionsCount: 88,
        })}
      />,
    );
    const signalsStat = screen.getByText('Signals').closest('.mini-stat');
    expect(signalsStat?.querySelector('strong')?.textContent).toBe('12');
  });

  it('prefers summary.open_positions over positionsCount', () => {
    render(
      <SidebarNav
        {...defaultProps({
          summary: { open_signals: 12, open_positions: 5 },
          activeSignalsCount: 99,
          positionsCount: 88,
        })}
      />,
    );
    const positionsStat = screen.getByText('Positions').closest('.mini-stat');
    expect(positionsStat?.querySelector('strong')?.textContent).toBe('5');
  });

  it('falls back to activeSignalsCount when summary.open_signals is undefined', () => {
    render(
      <SidebarNav
        {...defaultProps({
          summary: { open_positions: 4 } as any,
          activeSignalsCount: 6,
        })}
      />,
    );
    const signalsStat = screen.getByText('Signals').closest('.mini-stat');
    expect(signalsStat?.querySelector('strong')?.textContent).toBe('6');
  });
});