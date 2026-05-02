/**
 * Tests for the PR changes to frontend/src/pages/BotControlPage.tsx:
 *
 * - Removed pendingAction state (buttons no longer show "Starting...", etc.)
 * - Removed handleDiscoverPairs prop
 * - Buttons are disabled only by isBusy (not by currentBotState or pendingAction)
 * - "Search & Update Eligibles" button was removed
 * - Start, Stop, Restart buttons call handleBotAction directly
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import BotControlPage from '../pages/BotControlPage';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeLogs() {
  return { lines: ['log line 1', 'log line 2'] };
}

function renderPage(overrides: Partial<React.ComponentProps<typeof BotControlPage>> = {}) {
  const defaults = {
    currentBotState: 'RUNNING',
    currentStage: 'Monitoring',
    currentMode: 'PAPER',
    isConnected: true,
    isBusy: false,
    handleBotAction: vi.fn(),
    terminalMessages: [],
    logs: null,
  };
  return render(<BotControlPage {...defaults} {...overrides} />);
}

// ---------------------------------------------------------------------------
// Removed prop: handleDiscoverPairs
// ---------------------------------------------------------------------------

describe('BotControlPage – removed handleDiscoverPairs prop', () => {
  it('does NOT render a "Search & Update Eligibles" button', () => {
    renderPage();
    expect(screen.queryByText(/search.*update.*eligibles/i)).not.toBeInTheDocument();
  });

  it('component renders without handleDiscoverPairs in props', () => {
    // TypeScript ensures this at compile time; this test ensures runtime renders correctly.
    expect(() => renderPage()).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// Removed state: pendingAction
// ---------------------------------------------------------------------------

describe('BotControlPage – no pendingAction state', () => {
  it('Start button label is always "Start" (never "Starting...")', () => {
    renderPage({ isBusy: false, currentBotState: 'STOPPED' });
    const startBtn = screen.getByRole('button', { name: /start/i });
    expect(startBtn).toHaveTextContent('Start');
    expect(startBtn).not.toHaveTextContent('Starting');
  });

  it('Stop button label is always "Stop" (never "Stopping...")', () => {
    renderPage({ isBusy: false, currentBotState: 'RUNNING' });
    const stopBtn = screen.getByRole('button', { name: /^stop$/i });
    expect(stopBtn).toHaveTextContent('Stop');
    expect(stopBtn).not.toHaveTextContent('Stopping');
  });

  it('Restart button label is always "Restart" (never "Restarting...")', () => {
    renderPage({ isBusy: false });
    const restartBtn = screen.getByRole('button', { name: /restart/i });
    expect(restartBtn).toHaveTextContent('Restart');
    expect(restartBtn).not.toHaveTextContent('Restarting');
  });
});

// ---------------------------------------------------------------------------
// Button enabled/disabled logic: now only driven by isBusy
// ---------------------------------------------------------------------------

describe('BotControlPage – buttons disabled only by isBusy', () => {
  it('all action buttons are disabled when isBusy is true', () => {
    renderPage({ isBusy: true });
    expect(screen.getByRole('button', { name: /start/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /^stop$/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /restart/i })).toBeDisabled();
  });

  it('all action buttons are enabled when isBusy is false', () => {
    renderPage({ isBusy: false });
    expect(screen.getByRole('button', { name: /start/i })).not.toBeDisabled();
    expect(screen.getByRole('button', { name: /^stop$/i })).not.toBeDisabled();
    expect(screen.getByRole('button', { name: /restart/i })).not.toBeDisabled();
  });

  it('Start is enabled even when currentBotState is "RUNNING" (old behaviour was disabled)', () => {
    // After the PR, currentBotState no longer gates the Start button.
    renderPage({ isBusy: false, currentBotState: 'RUNNING' });
    expect(screen.getByRole('button', { name: /start/i })).not.toBeDisabled();
  });

  it('Stop is enabled even when currentBotState is "STOPPED" (old behaviour was disabled)', () => {
    renderPage({ isBusy: false, currentBotState: 'STOPPED' });
    expect(screen.getByRole('button', { name: /^stop$/i })).not.toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// Click handlers call handleBotAction directly
// ---------------------------------------------------------------------------

describe('BotControlPage – button click handlers', () => {
  it('clicking Start calls handleBotAction("start")', () => {
    const handleBotAction = vi.fn();
    renderPage({ handleBotAction, isBusy: false });
    fireEvent.click(screen.getByRole('button', { name: /start/i }));
    expect(handleBotAction).toHaveBeenCalledOnce();
    expect(handleBotAction).toHaveBeenCalledWith('start');
  });

  it('clicking Stop calls handleBotAction("stop")', () => {
    const handleBotAction = vi.fn();
    renderPage({ handleBotAction, isBusy: false });
    fireEvent.click(screen.getByRole('button', { name: /^stop$/i }));
    expect(handleBotAction).toHaveBeenCalledOnce();
    expect(handleBotAction).toHaveBeenCalledWith('stop');
  });

  it('clicking Restart calls handleBotAction("restart")', () => {
    const handleBotAction = vi.fn();
    renderPage({ handleBotAction, isBusy: false });
    fireEvent.click(screen.getByRole('button', { name: /restart/i }));
    expect(handleBotAction).toHaveBeenCalledOnce();
    expect(handleBotAction).toHaveBeenCalledWith('restart');
  });

  it('buttons do not call handleBotAction when isBusy is true', () => {
    const handleBotAction = vi.fn();
    renderPage({ handleBotAction, isBusy: true });
    fireEvent.click(screen.getByRole('button', { name: /start/i }));
    fireEvent.click(screen.getByRole('button', { name: /^stop$/i }));
    fireEvent.click(screen.getByRole('button', { name: /restart/i }));
    expect(handleBotAction).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Status metrics render correctly
// ---------------------------------------------------------------------------

describe('BotControlPage – status metrics display', () => {
  it('renders bot status from currentBotState prop', () => {
    renderPage({ currentBotState: 'STOPPED' });
    expect(screen.getByText('STOPPED')).toBeInTheDocument();
  });

  it('renders runtime stage from currentStage prop', () => {
    renderPage({ currentStage: 'Pre-Warming' });
    expect(screen.getByText('Pre-Warming')).toBeInTheDocument();
  });

  it('renders mode from currentMode prop', () => {
    renderPage({ currentMode: 'LIVE' });
    expect(screen.getByText('LIVE')).toBeInTheDocument();
  });

  it('shows "Live" when isConnected is true', () => {
    renderPage({ isConnected: true });
    expect(screen.getByText('Live')).toBeInTheDocument();
  });

  it('shows "Reconnecting" when isConnected is false', () => {
    renderPage({ isConnected: false });
    expect(screen.getByText('Reconnecting')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Terminal feed and logs panels
// ---------------------------------------------------------------------------

describe('BotControlPage – terminal feed and logs', () => {
  it('shows "No terminal activity yet." when terminalMessages is empty', () => {
    renderPage({ terminalMessages: [] });
    expect(screen.getByText('No terminal activity yet.')).toBeInTheDocument();
  });

  it('renders terminal messages when provided', () => {
    const messages = [
      { type: 'INFO', text: 'Bot started.', timestamp: '2026-01-01T00:00:00Z' },
    ];
    renderPage({ terminalMessages: messages });
    expect(screen.getByText('Bot started.')).toBeInTheDocument();
  });

  it('shows "No recent log lines." when logs is null', () => {
    renderPage({ logs: null });
    expect(screen.getByText('No recent log lines.')).toBeInTheDocument();
  });

  it('renders log lines when logs are provided', () => {
    renderPage({ logs: makeLogs() });
    expect(screen.getByText('log line 1')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Regression: only 3 action buttons (Start, Stop, Restart) — no 4th button
// ---------------------------------------------------------------------------

describe('BotControlPage – control strip has exactly 3 buttons', () => {
  it('renders exactly three action buttons in the control strip', () => {
    const { container } = renderPage();
    const controlStrip = container.querySelector('.control-strip');
    const buttons = controlStrip?.querySelectorAll('button');
    expect(buttons).toHaveLength(3);
  });
});