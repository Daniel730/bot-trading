/**
 * Tests for src/hooks/useStartupProgress.ts
 *
 * Covers:
 *  - preWarmingProgress: returns null when stage is not pre-warming, parses X/Y from details,
 *    clamps pct to [0, 100]
 *  - startupReady: requires all conditions (authenticated, connected, summary, dataReady, not still-starting)
 *  - startupTargetProgress: milestone steps 0→10→28→54→72→84→90→100
 *  - startupProgress: initialises to 8, jumps to 100 when ready, resets to 8 on logout
 */

import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useStartupProgress } from './useStartupProgress';

// Minimal stub types to satisfy the hook's type imports
type Stub = Record<string, unknown>;

function baseInput(overrides: Record<string, unknown> = {}) {
  return {
    isAuthenticated: true,
    isConnected: true,
    currentStage: 'Running',
    details: undefined as string | undefined,
    dataReady: true,
    summary: { open_signals: 0, open_positions: 0 } as Stub,
    health: null,
    tradeHistory: null,
    config: null,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// preWarmingProgress
// ---------------------------------------------------------------------------

describe('preWarmingProgress', () => {
  it('returns null when stage is unrelated and details have no pair-list pattern', () => {
    const { result } = renderHook(() => useStartupProgress(baseInput({ currentStage: 'Running' })));
    expect(result.current.preWarmingProgress).toBeNull();
  });

  it('returns null when stage matches pre-warming but details have no X/Y number', () => {
    const { result } = renderHook(() =>
      useStartupProgress(baseInput({ currentStage: 'pre-warming', details: 'loading pairs' })),
    );
    expect(result.current.preWarmingProgress).toBeNull();
  });

  it('parses X/Y from details when stage is pre-warming', () => {
    const { result } = renderHook(() =>
      useStartupProgress(baseInput({ currentStage: 'pre_warming', details: 'Pair list 3/10' })),
    );
    expect(result.current.preWarmingProgress).toEqual({ current: 3, total: 10, pct: 30 });
  });

  it('parses X/Y from details when stage is initializing', () => {
    const { result } = renderHook(() =>
      useStartupProgress(baseInput({ currentStage: 'initializing', details: '5 / 20' })),
    );
    expect(result.current.preWarmingProgress).toEqual({ current: 5, total: 20, pct: 25 });
  });

  it('triggers via "pair list" in details regardless of stage', () => {
    const { result } = renderHook(() =>
      useStartupProgress(baseInput({ currentStage: 'running', details: 'Pair list 7/10' })),
    );
    expect(result.current.preWarmingProgress).toEqual({ current: 7, total: 10, pct: 70 });
  });

  it('returns null when total is zero (division by zero guard)', () => {
    const { result } = renderHook(() =>
      useStartupProgress(baseInput({ currentStage: 'pre-warming', details: 'Pair list 0/0' })),
    );
    expect(result.current.preWarmingProgress).toBeNull();
  });

  it('clamps pct to 100 for current > total', () => {
    const { result } = renderHook(() =>
      useStartupProgress(baseInput({ currentStage: 'pre-warming', details: 'Pair list 12/10' })),
    );
    expect(result.current.preWarmingProgress?.pct).toBe(100);
  });

  it('clamps pct to 0 when current is 0', () => {
    const { result } = renderHook(() =>
      useStartupProgress(baseInput({ currentStage: 'pre-warming', details: 'Pair list 0/10' })),
    );
    expect(result.current.preWarmingProgress?.pct).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// startupReady
// ---------------------------------------------------------------------------

describe('startupReady', () => {
  it('returns true when all conditions satisfied and stage is "Running"', () => {
    const { result } = renderHook(() => useStartupProgress(baseInput()));
    expect(result.current.startupReady).toBe(true);
  });

  it('returns false when not authenticated', () => {
    const { result } = renderHook(() =>
      useStartupProgress(baseInput({ isAuthenticated: false })),
    );
    expect(result.current.startupReady).toBe(false);
  });

  it('returns false when not connected', () => {
    const { result } = renderHook(() =>
      useStartupProgress(baseInput({ isConnected: false })),
    );
    expect(result.current.startupReady).toBe(false);
  });

  it('returns false when summary is null', () => {
    const { result } = renderHook(() =>
      useStartupProgress(baseInput({ summary: null })),
    );
    expect(result.current.startupReady).toBe(false);
  });

  it('returns false when dataReady is false', () => {
    const { result } = renderHook(() =>
      useStartupProgress(baseInput({ dataReady: false })),
    );
    expect(result.current.startupReady).toBe(false);
  });

  it('returns false when stage contains "boot"', () => {
    const { result } = renderHook(() =>
      useStartupProgress(baseInput({ currentStage: 'Booting up' })),
    );
    expect(result.current.startupReady).toBe(false);
  });

  it('returns false when stage contains "init"', () => {
    const { result } = renderHook(() =>
      useStartupProgress(baseInput({ currentStage: 'Initializing' })),
    );
    expect(result.current.startupReady).toBe(false);
  });

  it('returns false when stage contains "start"', () => {
    const { result } = renderHook(() =>
      useStartupProgress(baseInput({ currentStage: 'Starting' })),
    );
    expect(result.current.startupReady).toBe(false);
  });

  it('returns false when stage contains "warm"', () => {
    const { result } = renderHook(() =>
      useStartupProgress(baseInput({ currentStage: 'Pre-Warming pairs' })),
    );
    expect(result.current.startupReady).toBe(false);
  });

  it('returns false when stage contains "connect"', () => {
    const { result } = renderHook(() =>
      useStartupProgress(baseInput({ currentStage: 'Connecting to exchange' })),
    );
    expect(result.current.startupReady).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// startupProgress initial state and reset
// ---------------------------------------------------------------------------

describe('startupProgress', () => {
  it('starts at 8 (initial state)', () => {
    const { result } = renderHook(() =>
      useStartupProgress(baseInput({ isAuthenticated: false })),
    );
    expect(result.current.startupProgress).toBe(8);
  });

  it('jumps to 100 when startupReady is true', () => {
    const { result } = renderHook(() => useStartupProgress(baseInput()));
    expect(result.current.startupProgress).toBe(100);
  });

  it('resets to 8 when isAuthenticated transitions to false', () => {
    let input = baseInput();
    const { result, rerender } = renderHook(() => useStartupProgress(input));
    // Initially authenticated and ready → 100
    expect(result.current.startupProgress).toBe(100);

    // Transition to unauthenticated
    act(() => {
      input = baseInput({ isAuthenticated: false });
    });
    rerender();
    expect(result.current.startupProgress).toBe(8);
  });

  it('progress does not exceed targetProgress when not ready', () => {
    const { result } = renderHook(() =>
      useStartupProgress(
        baseInput({
          isAuthenticated: true,
          isConnected: false,
          currentStage: 'Initializing',
          dataReady: false,
          summary: null,
        }),
      ),
    );
    // targetProgress with only isAuthenticated → 10
    expect(result.current.startupProgress).toBeGreaterThanOrEqual(8);
    expect(result.current.startupProgress).toBeLessThanOrEqual(10);
  });

  it('progress advances to 28 when dataReady becomes true', () => {
    const { result } = renderHook(() =>
      useStartupProgress(
        baseInput({
          isAuthenticated: true,
          isConnected: false,
          currentStage: 'Initializing',
          dataReady: true,
          summary: null,
        }),
      ),
    );
    expect(result.current.startupProgress).toBeGreaterThanOrEqual(28);
    expect(result.current.startupProgress).toBeLessThanOrEqual(54);
  });

  it('progress advances to 84 when connected but not yet ready', () => {
    const { result } = renderHook(() =>
      useStartupProgress(
        baseInput({
          isAuthenticated: true,
          isConnected: true,
          currentStage: 'Initializing',
          dataReady: true,
          summary: { open_signals: 0 } as Stub,
          health: { status: 'ok' } as Stub,
        }),
      ),
    );
    // target should be 84 with isConnected + health/data/summary
    expect(result.current.startupProgress).toBeGreaterThanOrEqual(72);
    expect(result.current.startupProgress).toBeLessThanOrEqual(84);
  });
});

// ---------------------------------------------------------------------------
// Interval timer behaviour
// ---------------------------------------------------------------------------

describe('useStartupProgress interval animation', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('gradually increases progress toward target via interval', () => {
    const input = baseInput({
      isAuthenticated: true,
      isConnected: false,
      currentStage: 'Initializing',
      dataReady: false,
      summary: null,
    });

    const { result } = renderHook(() => useStartupProgress(input));
    const initial = result.current.startupProgress;

    // Advance multiple ticks of 350ms
    act(() => {
      vi.advanceTimersByTime(350 * 5);
    });

    // Should not exceed target (10 for only-authenticated state)
    expect(result.current.startupProgress).toBeLessThanOrEqual(10);
    expect(result.current.startupProgress).toBeGreaterThanOrEqual(initial);
  });

  it('stops advancing once startupReady is true', () => {
    // Ready state: progress immediately goes to 100 via effect, interval should not run
    const { result } = renderHook(() => useStartupProgress(baseInput()));

    act(() => {
      vi.advanceTimersByTime(350 * 10);
    });

    expect(result.current.startupProgress).toBe(100);
  });
});