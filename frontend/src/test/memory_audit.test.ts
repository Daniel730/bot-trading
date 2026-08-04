import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { useTelemetry } from '../hooks/useTelemetry';

class MockWebSocket {
  onopen: ((ev?: unknown) => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: ((ev: { code: number }) => void) | null = null;
  onerror: ((ev?: unknown) => void) | null = null;
  send = vi.fn();
  close = vi.fn();
  url: string;
  static instances: MockWebSocket[] = [];

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
    setTimeout(() => this.onopen?.(), 0);
  }
}

describe('Telemetry Memory Stability', () => {
  beforeEach(() => {
    MockWebSocket.instances = [];
    (globalThis as any).WebSocket = MockWebSocket;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('authenticates with the approved session when the dashboard token is not retained', async () => {
    const { result } = renderHook(() => useTelemetry(null, 'persisted-session'));

    await new Promise((r) => setTimeout(r, 10));

    const wsInstance = result.current.ws?.current as unknown as MockWebSocket;
    expect(wsInstance.send).toHaveBeenCalledWith(
      JSON.stringify({
        type: 'auth',
        session: 'persisted-session',
      }),
    );
    expect(String(wsInstance.url)).not.toContain('session=');
    expect(String(wsInstance.url)).not.toContain('token=');
  });

  it('stops reconnecting and surfaces authError when the socket is closed with 4003', async () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useTelemetry(null, 'revoked-session'));

    await act(async () => {
      await Promise.resolve();
    });

    const first = MockWebSocket.instances[0];
    expect(first).toBeTruthy();

    await act(async () => {
      first.onclose?.({ code: 4003 });
    });

    expect(result.current.authError?.status).toBe(401);
    expect(result.current.authError?.message).toMatch(/session expired/i);

    await act(async () => {
      vi.advanceTimersByTime(60_000);
    });
    expect(MockWebSocket.instances.length).toBe(1);
    vi.useRealTimers();
  });

  it('strictly enforces 100-entry limit under extreme burst', async () => {
    const { result } = renderHook(() => useTelemetry('fake-token', 'fake-session'));

    await new Promise((r) => setTimeout(r, 10));

    const wsInstance = result.current.ws?.current as unknown as MockWebSocket;

    act(() => {
      for (let i = 0; i < 5000; i++) {
        wsInstance.onmessage?.({
          data: JSON.stringify({
            type: 'thought',
            data: { agent_name: 'TEST', thought: `Msg ${i}`, verdict: 'NEUTRAL' },
            timestamp: new Date().toISOString(),
          }),
        });
      }
    });

    expect(result.current.thoughts.length).toBe(100);
    expect(result.current.thoughts.at(-1)?.thought).toBe('Msg 4999');
  });
});
